"""PuertoTTS sobre un proveedor que devuelve audio PCM (nube o voces de Windows).

`TtsSintetizado` junta tres cosas: un `sintetizar(texto) -> AudioPcm`, la salida nativa y
una caché pequeña de frases cortas (las confirmaciones y avisos se repiten: no se pagan ni
se esperan dos veces). Devuelve el mismo dict que `TtsWyoming.hablar` (`ok`, `pcm`, `rate`,
`width`, `channels`, `primer_ms`, `total_ms`, `cache`) porque `speak()` lo lee tal cual.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable

from .proveedores_voz import AudioPcm, ErrorVoz
from .salida_nativa import SalidaNativa

MAX_CACHE = 64
MAX_TEXTO_CACHE = 80


class TtsSintetizado:
    def __init__(self, nombre: str, sintetizar: Callable[[str], AudioPcm], salida: SalidaNativa,
                 log: Callable[..., None] = print) -> None:
        self.nombre, self._sintetizar, self._salida, self._log = nombre, sintetizar, salida, log
        self._cache: OrderedDict[str, AudioPcm] = OrderedDict()
        self._lock = threading.Lock()
        self._hablando = threading.Event()
        self.usos = self.fallos = self.cache_aciertos = 0
        #: Las confirmaciones cortas se cachean siempre; quien necesite cachear frases largas lo sube.
        self.max_texto_cache = MAX_TEXTO_CACHE

    # ------------------------------------------------------------ contrato: estado
    @property
    def disponible(self) -> bool:
        return self._salida.disponible

    @property
    def hablando(self) -> bool:
        return self._hablando.is_set()

    @property
    def sonando(self) -> bool:
        return self._salida.sonando

    @property
    def estado(self) -> Any:
        return {"motor": self.nombre, "usos": self.usos, "fallos": self.fallos,
                "cache": len(self._cache), "cache_aciertos": self.cache_aciertos}

    @property
    def nivel_salida(self) -> float:
        return self._salida.nivel_salida

    # ------------------------------------------------------------------- caché
    def _de_cache(self, texto: str) -> AudioPcm | None:
        with self._lock:
            audio = self._cache.get(texto)
            if audio is not None:
                self._cache.move_to_end(texto)
            return audio

    def _a_cache(self, texto: str, audio: AudioPcm) -> None:
        if len(texto) > self.max_texto_cache:
            return
        with self._lock:
            self._cache[texto] = audio
            while len(self._cache) > MAX_CACHE:
                self._cache.popitem(last=False)

    def sintetizar(self, texto: str) -> tuple[AudioPcm, bool]:
        """(audio, vino_de_cache). Lanza ErrorVoz."""
        texto = (texto or "").strip()
        audio = self._de_cache(texto)
        if audio is not None:
            self.cache_aciertos += 1
            return audio, True
        audio = self._sintetizar(texto)
        self._a_cache(texto, audio)
        return audio, False

    # ------------------------------------------------------------ contrato: hablar
    def hablar(self, texto: str, parar: Any = None, al_pcm: Any = None, solo_pcm: bool = False) -> dict:
        texto = (texto or "").strip()
        if not texto:
            return {"ok": True, "vacio": True}
        if parar is not None and parar.is_set():
            return {"ok": True, "cortado": True}
        inicio = time.perf_counter()
        self.usos += 1
        try:
            audio, de_cache = self.sintetizar(texto)
        except ErrorVoz as error:
            self.fallos += 1
            return {"ok": False, "error": str(error), "motor": self.nombre}
        except Exception as error:  # un adaptador roto no debe tumbar el turno
            self.fallos += 1
            return {"ok": False, "error": f"{type(error).__name__} en {self.nombre}", "motor": self.nombre}
        if parar is not None and parar.is_set():
            return {"ok": True, "cortado": True}
        resultado = {"ok": True, "pcm": audio.pcm, "rate": audio.rate, "width": audio.ancho,
                     "channels": audio.canales, "cache": de_cache, "motor": self.nombre,
                     "primer_ms": (time.perf_counter() - inicio) * 1000.0}
        if al_pcm is not None:
            try:
                al_pcm(audio.pcm, audio.rate, audio.ancho, audio.canales)
            except Exception as error:
                self._log(f"[voz] al_pcm: {error}")
        if not solo_pcm:
            self._hablando.set()
            try:
                if not self._salida.reproducir(audio.pcm, audio.rate, audio.canales, audio.ancho, parar):
                    resultado["ok"] = False
                    resultado["error"] = "No se pudo reproducir el audio por los altavoces."
            finally:
                self._hablando.clear()
        resultado["total_ms"] = (time.perf_counter() - inicio) * 1000.0
        return resultado

    def cortar(self) -> None:
        self._salida.cortar()

    def calentar(self, frase: str = "Listo.") -> None:
        """Sin arranque en frío: una llamada de calentamiento solo costaría dinero."""

    def precachear(self, frases: Any, en_hilo: bool = True) -> None:
        """No se sintetiza por adelantado: en una voz de pago cada frase cuesta."""
