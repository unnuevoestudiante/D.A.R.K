"""
intenciones/cache_patrones.py
=============================
V2.4 Parte B — Caché de patrones aprendidos.

Cuando el conversacional resuelve una frase que las reglas del intérprete
no matcheaban (vía `_llm_elegir_tool`), guarda la frase normalizada y la
action elegida. Próximas frases similares se resuelven sin llamar al LLM.

Ejemplo motivador:
    Usuario: "reprodice musica relajante"   (typo de "reproduce")
    Intérprete: no matchea -> cae al LLM
    LLM: {"tool": "reproducir_musica", "args": {"query": "musica relajante"}}
    Caché: guarda "reprodice musica relajante" -> reproducir_musica

    Próximas veces "reprodice musica relajante" matchea la caché y no
    necesita al LLM.

Limitación conocida: si el usuario varía los argumentos ("reprodice musica
tranquila"), la similitud puede bajar del cutoff y no matchear. Es
aceptable para V2.4; se puede mejorar con variantes o embeddings después.

Persistencia: JSON local con escritura atómica (mismo patrón que
entidades.py). TTL de 30 días, máx 100 entradas.
"""
from __future__ import annotations

import difflib
import json
import os
import threading
import time
from typing import Dict, List, Optional
from utils.rutas_estado import resolver_ruta_estado

from contratos.herramienta import ALIAS_DE_NOMBRES

from nucleo.intenciones.normalizador import normalizar


RUTA_CACHE_PATRONES = resolver_ruta_estado(
    "nucleo/intenciones", "dark_cache_patrones.json",
    "intenciones/dark_cache_patrones.json", "dark_cache_patrones.json")

TTL_DIAS = 30
MAX_ENTRADAS = 100
CUTOFF_SIMILITUD = 0.85
CUTOFF_REFUERZO = 0.95    # si ya existe una entrada casi igual, se refuerza


class CachePatrones:
    """Caché de frases aprendidas. Se consulta cuando el intérprete no
    matcheó, antes de caer al LLM."""

    def __init__(self, ruta_persistencia: Optional[str] = None):
        self._lock = threading.RLock()
        self._ruta = ruta_persistencia
        self._entradas: List[dict] = []
        if self._ruta:
            self.cargar()

    # ---------------------------------------------------------------
    # API pública
    # ---------------------------------------------------------------
    # --- Filtro de confirmaciones (parche P1) ---
    _PALABRAS_CONFIRMACION = {
        'si', 'sí', 'claro', 'dale', 'hazlo', 'ok', 'vale', 'confirmo',
        'no', 'cancela', 'para', 'detente', 'adelante', 'ejecuta',
        'correcto', 'exacto', 'por', 'supuesto', 'entendido', 'listo',
    }

    def _es_confirmacion(self, texto):
        """True si la frase es una confirmacion/negacion corta, no una orden."""
        palabras = set((texto or '').lower().split())
        return bool(palabras & self._PALABRAS_CONFIRMACION) and len(palabras) <= 4

    def registrar(self, frase: str, action: str,
                  params: Optional[dict] = None) -> bool:
        """Guarda o refuerza una entrada. Devuelve True si se guardó algo."""
        # Parche P1: no guardar confirmaciones cortas como acciones.
        # 'si, abrelo' no es una orden: es la respuesta a una pregunta.
        # Si se cachea, en el siguiente turno abre cualquier app random.
        if self._es_confirmacion(frase):
            return
        frase_norm = normalizar(frase or "").strip().lower()
        if not frase_norm or not action:
            return False
        with self._lock:
            existente = self._mejor_match(frase_norm, CUTOFF_REFUERZO)
            ahora = time.time()
            if existente is not None:
                existente["veces"] = existente.get("veces", 1) + 1
                existente["ts_ultimo_uso"] = ahora
                existente["action"] = action
                existente["params"] = dict(params or {})
            else:
                self._entradas.append({
                    "frase": frase_norm,
                    "action": action,
                    "params": dict(params or {}),
                    "veces": 1,
                    "ts_creacion": ahora,
                    "ts_ultimo_uso": ahora,
                })
            self._aplicar_limites()
            self.persistir()
            return True

    def buscar(self, frase: str) -> Optional[dict]:
        """Devuelve {"action", "params", "similitud"} si la frase matchea
        una entrada con similitud >= CUTOFF_SIMILITUD. None si no."""
        frase_norm = normalizar(frase or "").strip().lower()
        if not frase_norm:
            return None
        with self._lock:
            hit = self._mejor_match(frase_norm, CUTOFF_SIMILITUD)
            if hit is None:
                return None
            hit["veces"] = hit.get("veces", 1) + 1
            hit["ts_ultimo_uso"] = time.time()
            self.persistir()
            return {
                "action": hit["action"],
                "params": dict(hit.get("params") or {}),
                "similitud": round(hit.get("_sim", 0.0), 3),
            }

    def olvidar(self, frase: str, cutoff: float = CUTOFF_SIMILITUD) -> int:
        """Elimina las entradas que matcheen la frase. Devuelve cuántas
        eliminó. Se usará cuando el hook de corrección esté conectado."""
        frase_norm = normalizar(frase or "").strip().lower()
        if not frase_norm:
            return 0
        with self._lock:
            antes = len(self._entradas)
            self._entradas = [
                e for e in self._entradas
                if difflib.SequenceMatcher(
                    None, frase_norm, e.get("frase", "")
                ).ratio() < cutoff
            ]
            eliminadas = antes - len(self._entradas)
            if eliminadas:
                self.persistir()
            return eliminadas

    def describir(self) -> str:
        with self._lock:
            n = len(self._entradas)
            if not n:
                return "(caché vacía)"
            top = sorted(self._entradas,
                         key=lambda e: e.get("veces", 0), reverse=True)[:5]
            lineas = [f"{n} entradas:"]
            for e in top:
                lineas.append(
                    f"  [{e.get('veces', 0)}x] {e.get('frase', '')!r}"
                    f" -> {e.get('action')}"
                )
            return "\n".join(lineas)

    def limpiar(self) -> None:
        with self._lock:
            self._entradas = []
            self.persistir()

    # ---------------------------------------------------------------
    # Persistencia
    # ---------------------------------------------------------------
    def persistir(self) -> bool:
        if not self._ruta:
            return False
        try:
            with self._lock:
                limpias = [
                    {k: v for k, v in e.items() if not k.startswith("_")}
                    for e in self._entradas
                ]
                tmp = self._ruta + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"version": 1, "entradas": limpias}, f,
                              ensure_ascii=False, indent=2)
                os.replace(tmp, self._ruta)
            return True
        except Exception as e:
            print(f"[Cache] no pude persistir: {e}")
            return False

    def cargar(self) -> bool:
        if not self._ruta or not os.path.isfile(self._ruta):
            return False
        try:
            with open(self._ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                self._entradas = list(data.get("entradas") or [])
                migradas = self._migrar_nombres()
                self._aplicar_limites()
                if migradas:
                    # El fichero era estado escrito con nombres viejos; se queda
                    # reescrito para que la migración no se pague en cada carga.
                    self.persistir()
            return True
        except Exception as e:
            print(f"[Cache] estado previo corrupto, se ignora: {e}")
            return False

    def _migrar_nombres(self) -> int:
        """Reescribe el nombre de herramienta antiguo por el nuevo.

        La caché guarda el `action` que eligió el LLM. Cuando una herramienta
        cambia de sitio —`buscar_web` pasó a `investigar`— las entradas viejas
        apuntarían a una herramienta que ya no existe y la frase aprendería de
        cero. La única fuente del rename es `ALIAS_DE_NOMBRES`.
        """
        migradas = 0
        for entrada in self._entradas:
            viejo = entrada.get("action")
            nuevo = ALIAS_DE_NOMBRES.get(viejo)
            if nuevo:
                entrada["action"] = nuevo
                migradas += 1
        return migradas

    # ---------------------------------------------------------------
    # Internos
    # ---------------------------------------------------------------
    def _mejor_match(self, frase_norm: str, cutoff: float) -> Optional[dict]:
        mejor = None
        mejor_sim = 0.0
        for e in self._entradas:
            frase_e = e.get("frase", "")
            if not frase_e:
                continue
            sim = difflib.SequenceMatcher(None, frase_norm, frase_e).ratio()
            if sim >= cutoff and sim > mejor_sim:
                mejor = e
                mejor_sim = sim
        if mejor is not None:
            mejor["_sim"] = mejor_sim
        return mejor

    def _aplicar_limites(self) -> None:
        ahora = time.time()
        ttl_seg = TTL_DIAS * 86400
        self._entradas = [
            e for e in self._entradas
            if ahora - e.get("ts_ultimo_uso", 0) < ttl_seg
        ]
        if len(self._entradas) > MAX_ENTRADAS:
            self._entradas.sort(
                key=lambda e: e.get("ts_ultimo_uso", 0), reverse=True
            )
            self._entradas = self._entradas[:MAX_ENTRADAS]
