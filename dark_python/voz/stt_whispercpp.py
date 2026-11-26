"""Adaptador de whisper.cpp: el mismo puerto, contra un servidor residente.

whisper.cpp no es una librería de Python: su `server` es un binario que levanta
un HTTP con `/health` y `/inference`. Este módulo habla ese HTTP y traduce el
JSON al vocabulario del contrato. Lo que se acepta y lo que se tira lo decide
`voz/politica_calidad.py`, igual que en la ruta de faster-whisper.

Dos asimetrías frente a `WhisperLocal`, ambas del motor y no ocultables:

  * `repeticion` no existe. El `verbose_json` de whisper.cpp trae `avg_logprob`
    y `no_speech_prob` por segmento pero no calcula `compression_ratio`, así que
    esa pata de la política simplemente no se aplica. Es el caso que motivó que
    las señales fueran opcionales en el contrato.
  * `liberar()` es un no-op. El modelo vive en el proceso del servidor y ese
    servidor no tiene endpoint para descargarlo: la RAM se libera matando el
    proceso, cosa que decide el supervisor, no este adaptador.

El puerto `asegurar()` tampoco puede cargar nada: el `.ggml` se elige con
`--model` al arrancar el servicio. Aquí `asegurar()` consulta `/health` y dice
si está listo, que es lo que el llamador necesita saber.
"""
from __future__ import annotations

import os
import time
from typing import Callable, Optional

from contratos.voz import SENAL_CONFIANZA, SENAL_SIN_VOZ
from config_runtime import get_runtime_value
from voz.politica_calidad import UMBRALES_LOCALES, decidir, senales_de_segmento

# whisper.cpp no llama a compression_ratio: las dos señales que sí mide.
ALIASES_WHISPER_CPP = {
    "avg_logprob": SENAL_CONFIANZA,
    "no_speech_prob": SENAL_SIN_VOZ,
}

# 9080 y no el 8080 que trae `whisper-server` por defecto: el 8080 ya lo ocupa
# el llama-server (ver proveedores/llm/llamacpp.py), y los dos motores pueden
# estar vivos a la vez. Al arrancar el servicio hay que pasar --port 9080.
_URL_POR_DEFECTO = get_runtime_value("services.whisperCpp.url")

# Parámetros del motor para la decodificación de este turno. No son la política
# de rechazo (esa está en `politica_calidad.py`): son los números que el server
# usa mientras decodifica, y se copian de los que ya usa la ruta local.
_PARAMETROS_DECODE = {
    "temperature": "0.0",
    "beam_size": "1",
    "no_speech_thold": "0.85",
    "logprob_thold": "-0.6",
}

# La ruta local pide `vad_filter=True` y faster-whisper trae Silero dentro del
# paquete. El `server` de whisper.cpp no: si se le pide VAD sin haberle pasado
# `--vad-model` al arrancar, la inferencia falla con HTTP 500 (medido). Por eso
# el VAD viene apagado y solo se manda con DARK_WHISPERCPP_VAD encendido, cuando
# el señor arranque el servicio con su modelo Silero. Los umbrales son los de la
# ruta local para que la comparación sea justa.
_PARAMETROS_VAD = {
    "vad": "true",
    "vad_threshold": "0.6",
    "vad_min_silence_duration_ms": "500",
    "vad_speech_pad_ms": "150",
}

_ACTIVOS = ("1", "true", "si", "yes", "on")


class WhisperCppTranscriptor:
    """Cumple `PuertoSTT` contra un `server` de whisper.cpp ya en marcha."""

    def __init__(self, modelo="small", hilos=4, base_url: Optional[str] = None,
                 session: Optional[object] = None, log: Callable = print):
        self.modelo = modelo
        self.hilos = hilos
        self.base_url = (base_url or os.environ.get("DARK_WHISPERCPP_URL")
                         or _URL_POR_DEFECTO).rstrip("/")
        self._session = session
        self._log = log
        self._residente: Optional[bool] = None
        self.usar_vad = (os.environ.get("DARK_WHISPERCPP_VAD", "")
                         .strip().lower() in _ACTIVOS)

    @property
    def cargado(self) -> bool:
        """Lo que dijo el último `/health`. No hay carga perezosa que vigilar."""
        return bool(self._residente)

    @property
    def sesion(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
        return self._session

    def asegurar(self, timeout: Optional[float] = 5.0) -> bool:
        """True si el servidor tiene el modelo listo para inferir.

        `/health` responde `{"status": "ok"}` o `{"status": "loading model"}`.
        """
        try:
            respuesta = self.sesion.get(f"{self.base_url}/health", timeout=timeout)
            estado = respuesta.json().get("status")
        except Exception as error:
            self._residente = None
            self._log(f"[voz] whisper.cpp no respondió en /health: {error}")
            return False
        self._residente = estado == "ok"
        if not self._residente:
            self._log(f"[voz] whisper.cpp aún no está listo: {estado!r}")
        return self._residente

    def transcribir_wav(self, wav_bytes, language="es", prompt="", timeout=None):
        """POST multipart a `/inference` y política de rechazo sobre los segmentos."""
        if not self.asegurar():
            return {"ok": False, "texto": "",
                    "error": "el servidor whisper.cpp no tiene el modelo residente"}
        inicio = time.perf_counter()
        datos = dict(_PARAMETROS_DECODE, language=language,
                     response_format="verbose_json")
        if self.usar_vad:
            datos.update(_PARAMETROS_VAD)
        if prompt:
            datos["prompt"] = prompt
        try:
            respuesta = self.sesion.post(
                f"{self.base_url}/inference",
                data=datos,
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                timeout=timeout,
            )
            respuesta.raise_for_status()
            segmentos = respuesta.json().get("segments") or []
        except Exception as error:
            return {"ok": False, "texto": "", "error": str(error),
                    "segundos": time.perf_counter() - inicio}

        partes = [str(s.get("text", "")) for s in segmentos]
        senales = [senales_de_segmento(s, ALIASES_WHISPER_CPP) for s in segmentos]
        decision = decidir(partes, senales, UMBRALES_LOCALES)
        if decision.rechazada:
            self._log(f"DEBUG - whisper.cpp: rechazo por {decision.motivo()}")
        return {
            "ok": True,
            "texto": decision.texto,
            "segundos": time.perf_counter() - inicio,
        }

    def liberar(self) -> None:
        """No-op documentado: el modelo vive en otro proceso, sin endpoint de descarga."""
        self._log("[voz] whisper.cpp: el modelo es residente del servidor; "
                  "liberar memoria es asunto del supervisor del proceso.")
