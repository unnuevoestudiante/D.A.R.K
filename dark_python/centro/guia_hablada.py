"""La guía hablada: D.A.R.K. dice en voz alta lo que explica cada pantalla del Centro.

Habla **con lo que haya**, empezando por lo que Windows ya trae:
  * si la persona eligió una voz en el Centro (cadena de voces), usa esa;
  * si no, la voz de Windows en español (sin descargar nada, sin red, sin ninguna instalación);
  * si no hay ninguna, calla y la guía queda escrita: nunca rompe la pantalla.

Una sola frase suena a la vez: al pasar a otra pantalla corta la anterior. Las frases de la guía se
generan por adelantado en segundo plano (`precachear`) para que al pulsar «Siguiente» la siguiente
explicación suene sin esperar a que Windows la prepare.
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from voz.proveedores_voz import ErrorVoz, VocesDeWindows
from voz.salida_nativa import SalidaNativa
from voz.tts_nube import TtsSintetizado

#: Las frases de la guía son más largas que las de una confirmación: se guardan enteras.
MAX_TEXTO_GUIA = 600


class GuiaHablada:
    def __init__(self, tts_elegido: Callable[[], Any] = lambda: None, windows: VocesDeWindows | None = None,
                 salida: SalidaNativa | None = None, al_estado: Callable[[bool], None] = lambda hablando: None,
                 log: Callable[..., None] = print) -> None:
        self._tts_elegido = tts_elegido
        self._windows = windows or VocesDeWindows()
        self._salida = salida or SalidaNativa()
        self._al_estado, self._log = al_estado, log
        self._lock = threading.Lock()
        self._parar: threading.Event | None = None
        self._voz_windows: TtsSintetizado | None = None
        self._nombre_voz = ""

    # ------------------------------------------------------------------ voz de Windows
    def _elegir_voz_windows(self) -> str | None:
        """Una voz en español si hay; si no, la primera. None si Windows no tiene ninguna."""
        voces = self._windows.listar()
        if not voces:
            return None
        return next((n for n, cultura in voces if cultura.lower().startswith("es")), voces[0][0])

    def _tts_windows(self) -> TtsSintetizado | None:
        if self._voz_windows is None:
            nombre = self._elegir_voz_windows()
            if nombre is None:
                return None
            self._nombre_voz = nombre
            self._voz_windows = TtsSintetizado(f"Windows/{nombre}", lambda texto: self._windows.sintetizar(texto[:MAX_TEXTO_GUIA], nombre),
                                               self._salida, self._log)
            self._voz_windows.max_texto_cache = MAX_TEXTO_GUIA
        return self._voz_windows

    # ------------------------------------------------------------------------- hablar
    def decir(self, texto: str) -> None:
        """Corta lo que esté sonando y dice `texto` en segundo plano."""
        texto = (texto or "").strip()
        if not texto:
            return
        with self._lock:
            if self._parar is not None:
                self._parar.set()
            self._salida.cortar()
            parar = threading.Event()
            self._parar = parar
        threading.Thread(target=self._decir, args=(texto, parar), daemon=True, name="guia-hablada").start()

    def _decir(self, texto: str, parar: threading.Event) -> None:
        self._al_estado(True)
        try:
            elegido = None
            try:
                elegido = self._tts_elegido()
            except Exception:
                elegido = None
            if elegido is not None:
                resultado = elegido.hablar(texto, parar=parar)
                if isinstance(resultado, dict) and resultado.get("ok"):
                    return
            tts = self._tts_windows()
            if tts is None:
                self._log("[guia] sin voz disponible: la guía queda escrita")
                return
            tts.hablar(texto, parar=parar)
        except ErrorVoz as error:
            self._log(f"[guia] no pude hablar: {error}")
        except Exception as error:  # nunca debe romper la pantalla
            self._log(f"[guia] no pude hablar ({type(error).__name__})")
        finally:
            if not parar.is_set():
                self._al_estado(False)

    def cortar(self) -> None:
        with self._lock:
            if self._parar is not None:
                self._parar.set()
        self._salida.cortar()
        self._al_estado(False)

    def precachear(self, textos: list[str]) -> None:
        """Genera por adelantado, en segundo plano, las frases que se van a decir."""
        def trabajo() -> None:
            try:
                tts = self._tts_windows()
                if tts is None:
                    return
                for texto in textos:
                    tts.sintetizar(texto.strip())
            except Exception:
                pass
        threading.Thread(target=trabajo, daemon=True, name="guia-precache").start()
