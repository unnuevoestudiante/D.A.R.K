"""
intenciones/entidades.py
========================
V2.2.a — Memoria de entidades conversacionales.

Guarda las últimas entidades que el usuario mencionó en una acción
("abre Photoshop", "reproduce Billie Jean", "busca config.py") para
poder resolver referencias posteriores del tipo:

  "abre el juego que te dije"     -> abrir {última app}
  "ábrelo"                        -> abrir {última app}
  "busca el archivo que te dije"  -> buscar {último archivo}
  "pon la canción que te dije"    -> reproducir {última música}

Convive con `_ultima_musica_query` de gestor.py: este módulo
generaliza esa misma idea a más tipos.

NO sustituye a dark_temas (contexto conversacional) ni a dark_contexto
(contexto de sesión). Es una capa propia, pequeña y con vida corta.

Persistencia: JSON local con escritura atómica (mismo patrón que
dark_contexto.Memoria y dark_intencion.GestorIntenciones).

Privacidad: se guardan cadenas cortas (nombres de app, archivos, queries
de música). Nada de contenido conversacional completo.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Dict, List, Optional
from utils.rutas_estado import resolver_ruta_estado


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
RUTA_ENTIDADES = resolver_ruta_estado(
    "nucleo/intenciones", "dark_entidades.json",
    "intenciones/dark_entidades.json", "dark_entidades.json")

TTL_TURNOS_DEFECTO = 40
MAX_POR_TIPO_DEFECTO = 20
MAX_VALOR_CHARS = 120     # recorte defensivo: una entidad nunca es un párrafo

# Tipos reconocidos. Ampliar aquí cuando aparezcan más en el futuro.
TIPOS = ("app", "archivo", "musica", "modulo")


# ---------------------------------------------------------------------------
# Gestor
# ---------------------------------------------------------------------------
class GestorEntidades:
    """Memoria corta de entidades mencionadas. Se consulta por tipo."""

    def __init__(self, ruta_persistencia: Optional[str] = None,
                 ttl_turnos: int = TTL_TURNOS_DEFECTO,
                 max_por_tipo: int = MAX_POR_TIPO_DEFECTO):
        self._lock = threading.RLock()
        self._ruta = ruta_persistencia
        self._ttl = max(1, int(ttl_turnos))
        self._max = max(1, int(max_por_tipo))
        # tipo -> lista ordenada por antigüedad (última al final)
        self._datos: Dict[str, List[dict]] = {t: [] for t in TIPOS}
        if self._ruta:
            self.cargar(self._ruta)

    # ----- API pública ----------------------------------------------------
    def registrar(self, valor, tipo: str, turno: int) -> None:
        """Guarda/actualiza una entidad. Si ya existía, se mueve al final."""
        if not valor or not isinstance(valor, str) or tipo not in self._datos:
            return
        v = valor.strip()[:MAX_VALOR_CHARS]
        if not v:
            return
        with self._lock:
            lista = self._datos[tipo]
            # Eliminar duplicado (case-insensitive) y reinsertar al final.
            v_lower = v.lower()
            lista[:] = [e for e in lista if e.get("valor", "").lower() != v_lower]
            lista.append({"valor": v, "turno": int(turno)})
            # Truncar los más viejos si excede el tope.
            if len(lista) > self._max:
                del lista[:len(lista) - self._max]
            self.persistir()

    def ultima(self, tipo: str, turno_actual: Optional[int] = None) -> Optional[str]:
        """Última entidad del tipo, o None si no hay o ya expiró."""
        with self._lock:
            lista = self._datos.get(tipo) or []
            if not lista:
                return None
            ent = lista[-1]
            if turno_actual is not None:
                if turno_actual - int(ent.get("turno", 0)) > self._ttl:
                    return None
            return ent.get("valor")

    def descripcion(self) -> str:
        """Volcado corto para depurar."""
        with self._lock:
            partes = []
            for tipo, lista in self._datos.items():
                if not lista:
                    continue
                ult = lista[-1]
                partes.append(f"{tipo}={ult.get('valor')!r}@{ult.get('turno')}")
            return " | ".join(partes) or "(sin entidades)"

    def limpiar(self, tipo: Optional[str] = None) -> None:
        with self._lock:
            if tipo is None:
                self._datos = {t: [] for t in TIPOS}
            elif tipo in self._datos:
                self._datos[tipo] = []
            self.persistir()

    # ----- Persistencia ---------------------------------------------------
    def persistir(self) -> bool:
        if not self._ruta:
            return False
        try:
            with self._lock:
                data = {"version": 1, "entidades": self._datos}
                tmp = self._ruta + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self._ruta)
            return True
        except Exception as e:
            print(f"[Entidades] no pude persistir: {e}")
            return False

    def cargar(self, ruta: Optional[str] = None) -> bool:
        ruta = ruta or self._ruta
        if not ruta or not os.path.isfile(ruta):
            return False
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                data = json.load(f)
            ent = data.get("entidades") or {}
            with self._lock:
                for tipo in TIPOS:
                    lista = ent.get(tipo) or []
                    # Solo conservar dicts con 'valor' y 'turno'.
                    limpia = [e for e in lista
                              if isinstance(e, dict) and e.get("valor")]
                    self._datos[tipo] = limpia[-self._max:]
            return True
        except Exception as e:
            print(f"[Entidades] estado previo corrupto, se ignora: {e}")
            return False
