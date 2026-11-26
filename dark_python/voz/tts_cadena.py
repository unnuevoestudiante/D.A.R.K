"""TTS por cadena: la voz que la persona eligió en el Centro, con respaldo.

Envuelve al TTS que ya hubiera (Piper/Wyoming, o ninguno) y, en cada frase, lee las
preferencias vivas del Centro (`asignaciones.vozSalida.principal` + `bibliotecas.voces`).
Con cadena, prueba las voces en el orden que dicta la política (misma lógica que el chat:
`proveedores.llm.cadena.ordenar`) y solo si todas fallan cae al TTS de base, salvo
«solo nube», que es una promesa de la persona y nunca cae a nada local.

Sin cadena delega todo en la base, así que quien no configuró voces no nota nada. El Núcleo
lo instala solo mientras haya cadena (`TtsPorCadena.hay_cadena`) y lo retira cuando no.
"""
from __future__ import annotations

import hashlib
import threading
from typing import Any, Callable

from proveedores.llm.cadena import ordenar

from .pronunciacion import para_voz
from .proveedores_voz import PROVEEDORES_NUBE, ErrorVoz, VocesDeWindows
from .salida_nativa import SalidaNativa
from .tts_nube import TtsSintetizado


class _VozBase:
    """La voz local de Piper dentro de la cadena: es el TTS de base, que habla con su propia voz."""

    nombre = "Voz local (Piper)"

    def __init__(self, cadena: "TtsPorCadena") -> None:
        self._cadena = cadena

    def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
        base = self._cadena.base
        if base is None:
            return {"ok": False, "error": "La voz local no está activa.", "motor": self.nombre}
        resultado = base.hablar(texto, parar=parar, al_pcm=al_pcm, solo_pcm=solo_pcm)
        return resultado if isinstance(resultado, dict) else {"ok": bool(resultado), "motor": self.nombre}


class TtsPorCadena:
    def __init__(self, base: Any, preferencias: Callable[[], Any], clave_de: Callable[[str], str],
                 sesion: Callable[[], Any], salida: SalidaNativa | None = None,
                 windows: VocesDeWindows | None = None, log: Callable[..., None] = print,
                 piper_local: Any = None) -> None:
        self.base = base
        self._piper_local = piper_local
        self._prefs, self._clave_de, self._sesion = preferencias, clave_de, sesion
        self._salida = salida or SalidaNativa()
        self._windows = windows or VocesDeWindows()
        self._log = log
        self._cache: tuple[str, list[TtsSintetizado]] = ("", [])
        self._lock = threading.Lock()
        self._ultimo_error = ""

    # --------------------------------------------------------------- resolución
    def _asignacion(self) -> dict:
        try:
            prefs = self._prefs()
            return (prefs.obtener("asignaciones.vozSalida.principal") or {}) if prefs is not None else {}
        except Exception:  # una configuración rota no debe romper una frase
            return {}

    def hay_cadena(self) -> bool:
        try:
            return bool(self._candidatos())
        except Exception:
            return False

    def _crear(self, recurso: dict) -> TtsSintetizado | None:
        if recurso.get("origen") == "nube":
            proveedor = PROVEEDORES_NUBE.get(str(recurso.get("proveedor")))
            clave = self._clave_de(str(recurso.get("proveedor"))) if proveedor else ""
            voz_id = str(recurso.get("voz_id") or "")
            if not (proveedor and clave and voz_id):
                return None
            return TtsSintetizado(
                f"{proveedor.nombre}/{voz_id}",
                lambda texto, p=proveedor, v=voz_id, k=clave: p.sintetizar(texto, v, k, self._sesion()),
                self._salida, self._log)
        if recurso.get("origen") == "piper":
            if self.base is None:
                return None  # sin servidor de voz local no hay voz de Piper que usar
            return _VozBase(self)
        if recurso.get("origen") == "piper_local":
            if self._piper_local is None:
                return None
            from centro.piper_catalogo import ruta_onnx

            onnx = str(ruta_onnx(str(recurso.get("voz") or "")))
            return TtsSintetizado(f"Piper/{recurso.get('voz')}", lambda texto, o=onnx: self._piper_local.sintetizar(texto, o),
                                  self._salida, self._log)
        if recurso.get("origen") == "sistema":
            voz = str(recurso.get("voz") or "")
            return TtsSintetizado(f"Windows/{voz}", lambda texto, v=voz: self._windows.sintetizar(texto, v),
                                  self._salida, self._log)
        return None

    def _candidatos(self) -> list[TtsSintetizado]:
        prefs = self._prefs()
        if prefs is None:
            return []
        asignacion = self._asignacion()
        ids = [i for i in asignacion.get("cadena", []) if isinstance(i, str)]
        if not ids:
            return []
        recursos = {r["id"]: r for r in prefs.obtener("bibliotecas.voces", []) or []}
        elegidos = ordenar(asignacion.get("politica", ""), [recursos[i] for i in ids if i in recursos])
        cuentas = sorted({str(r.get("proveedor")) for r in elegidos if r.get("origen") == "nube"})
        # La huella de las claves hace que cambiar una clave en Claves valga en la siguiente frase.
        huellas = [hashlib.sha256(self._clave_de(c).encode("utf-8")).hexdigest()[:6] for c in cuentas]
        firma = repr((elegidos, huellas))
        with self._lock:
            if self._cache[0] != firma:
                self._cache = (firma, [t for t in (self._crear(r) for r in elegidos) if t is not None])
            return self._cache[1]

    # ------------------------------------------------------------------- hablar
    def hablar(self, texto: str, parar: Any = None, al_pcm: Any = None, solo_pcm: bool = False) -> Any:
        texto = para_voz(texto)  # «D.A.R.K.» se lee «Dark», no se deletrea (también con la voz de respaldo)
        try:
            candidatos = self._candidatos()
        except Exception as error:  # la configuración nunca debe dejar un turno mudo
            self._log(f"[voz] se ignora la cadena de voces: {type(error).__name__}")
            candidatos = []
        ultimo: Any = None
        for tts in candidatos:
            resultado = tts.hablar(texto, parar=parar, al_pcm=al_pcm, solo_pcm=solo_pcm)
            if resultado.get("ok"):
                return resultado
            ultimo = resultado
            self._ultimo_error = str(resultado.get("error", ""))
            self._log(f"[voz] {tts.nombre} no pudo hablar ({self._ultimo_error}); sigo con la siguiente")
        solo_nube = self._asignacion().get("politica") == "solo_nube"
        if self.base is not None and not solo_nube:
            return self.base.hablar(texto, parar=parar, al_pcm=al_pcm, solo_pcm=solo_pcm)
        return ultimo or {"ok": False, "error": "No hay una voz disponible."}

    # --------------------------------------------------- el resto del contrato
    def _base(self, nombre: str, defecto: Any) -> Any:
        return getattr(self.base, nombre, defecto) if self.base is not None else defecto

    @property
    def disponible(self) -> bool:
        return self.hay_cadena() or bool(self._base("disponible", False))

    @property
    def hablando(self) -> bool:
        return bool(self._base("hablando", False)) or self._salida.sonando

    @property
    def sonando(self) -> bool:
        return bool(self._base("sonando", False)) or self._salida.sonando

    @property
    def estado(self) -> Any:
        return {"cadena": self.hay_cadena(), "ultimoError": self._ultimo_error, "base": self._base("estado", None)}

    @property
    def nivel_salida(self) -> float:
        return max(float(self._base("nivel_salida", 0.0) or 0.0), self._salida.nivel_salida)

    def cortar(self) -> None:
        self._salida.cortar()
        if self.base is not None:
            self.base.cortar()

    def calentar(self, frase: str = "Listo.") -> None:
        if self.base is not None:
            self.base.calentar(frase)

    def precachear(self, frases: Any, en_hilo: bool = True) -> None:
        if self.base is not None:
            self.base.precachear(frases, en_hilo=en_hilo)

    def __getattr__(self, nombre: str) -> Any:
        # `uri` y otros detalles de diagnóstico que el Núcleo lee de la base.
        if nombre.startswith("_") or nombre == "base":
            raise AttributeError(nombre)
        return getattr(self.base, nombre)
