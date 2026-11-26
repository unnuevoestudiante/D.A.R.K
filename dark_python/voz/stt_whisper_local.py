"""Adaptador local de faster-whisper, cargado bajo demanda.

Traduce los campos de quality de CTranslate2 al vocabulario del contrato y deja
que la política decida; él no decide. Elegir motor es asunto de `fabrica_stt.py`.
"""
from __future__ import annotations

import gc
import io
import time
from typing import Callable

from voz.politica_calidad import UMBRALES_LOCALES, decidir, senales_de_segmento


class WhisperLocal:
    def __init__(self, modelo="small", dispositivo="cpu", tipo_calculo="int8",
                 hilos=4, model_factory: Callable | None = None, log=print):
        self.modelo = modelo
        self.dispositivo = dispositivo
        self.tipo_calculo = tipo_calculo
        self.hilos = hilos
        self._model_factory = model_factory
        self._model = None
        self._log = log

    @property
    def cargado(self):
        return self._model is not None

    def asegurar(self):
        if self._model is not None:
            return True
        factory = self._model_factory
        if factory is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as error:
                self._log(f"[voz] faster-whisper no está instalado: {error}")
                return False
            factory = WhisperModel
        try:
            self._model = factory(
                self.modelo,
                device=self.dispositivo,
                compute_type=self.tipo_calculo,
                cpu_threads=self.hilos,
            )
            return True
        except Exception as error:
            self._log(f"[voz] no pude cargar el STT local: {error}")
            return False

    def transcribir_wav(self, wav_bytes, language="es", prompt="", timeout=None):
        """Transcribe WAV y aplica los filtros de confianza de la ruta local."""
        if not self.asegurar():
            return {"ok": False, "texto": "", "error": "proveedor STT local no disponible"}
        inicio = time.perf_counter()
        try:
            segments, _info = self._model.transcribe(
                io.BytesIO(wav_bytes), language=language, beam_size=1,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500, threshold=0.6,
                                    speech_pad_ms=150),
                condition_on_previous_text=False, initial_prompt=prompt or None,
                no_speech_threshold=0.85, log_prob_threshold=-0.6,
                temperature=0.0, compression_ratio_threshold=1.8,
            )
            partes, senales = [], []
            for segment in segments:
                partes.append(segment.text)
                senales.append(senales_de_segmento(segment))
            decision = decidir(partes, senales, UMBRALES_LOCALES)
            if decision.rechazada:
                self._log(f"DEBUG - whisper: rechazo por {decision.motivo()}")
            return {
                "ok": True,
                "texto": decision.texto,
                "segundos": time.perf_counter() - inicio,
            }
        except Exception as error:
            return {"ok": False, "texto": "", "error": str(error),
                    "segundos": time.perf_counter() - inicio}

    def liberar(self):
        self._model = None
        gc.collect()
