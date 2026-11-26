"""
stt.py — Reconocimiento de voz sobre Wyoming (faster-whisper).

Ruta nueva:  PCM 16 kHz -> wyoming-faster-whisper -> texto
Ruta vieja:  WhisperModel('small') dentro del propio proceso de Dark

Ventajas:
  * el modelo vive en su proceso: no compite por el GIL con Ollama, VLC ni el
    overlay, y ya no hay que liberarlo ni recargarlo cuando falta RAM,
  * siempre esta caliente (la ruta vieja lo descargaba y recargaba),
  * el cliente no espera 0,8 s de `pause_threshold` antes de empezar.

El filtrado del texto (alucinaciones, eco del TTS, correcciones) se queda donde
estaba, en el nucleo: aqui solo se devuelve el texto crudo.
"""

import asyncio
import io
import wave

from . import cliente, config


def wav_a_pcm(wav_bytes):
    """(pcm, rate, width, channels) de un WAV en memoria."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        params = wf.getparams()
        pcm = wf.readframes(params.nframes)
    return pcm, params.framerate, params.sampwidth, params.nchannels


class SttWyoming:
    """Transcripcion contra el servidor Wyoming."""

    def __init__(self, uri=None, language=None, log=print):
        self.uri = uri or config.WHISPER_URI
        self.language = language or config.WHISPER_LANGUAGE
        self._log = log
        self.usos = 0
        self.fallos = 0
        self.ultimo_error = None
        self.ultimos_segundos = None

    # -- estado ------------------------------------------------------------

    @property
    def disponible(self):
        return cliente.sondear(self.uri) is not None

    def estado(self):
        return {
            "uri": self.uri,
            "idioma": self.language,
            "disponible": self.disponible,
            "usos": self.usos,
            "fallos": self.fallos,
            "ultimo_error": self.ultimo_error,
            "ultimos_segundos": self.ultimos_segundos,
        }

    # -- API principal -----------------------------------------------------

    def transcribir_pcm(self, pcm, rate, width=2, channels=1, language=None,
                        timeout=None):
        """Devuelve {'ok', 'texto', 'segundos', 'error'}."""
        if not pcm:
            return {"ok": True, "texto": "", "segundos": 0.0}

        try:
            texto, segundos = cliente.correr_async(
                lambda: cliente.transcribir(
                    self.uri, pcm, rate, width, channels,
                    language or self.language,
                    timeout=timeout,
                )
            )
        except Exception as e:
            self.fallos += 1
            self.ultimo_error = str(e)
            self._log(f"[voz] ASR Wyoming fallo: {e}")
            return {"ok": False, "texto": "", "segundos": 0.0, "error": str(e)}

        self.usos += 1
        self.ultimo_error = None
        self.ultimos_segundos = segundos
        return {
            "ok": True,
            "texto": (texto or "").strip(),
            "segundos": segundos,
        }

    def transcribir_audio_data(self, audio, language=None, timeout=None):
        """Compatibilidad con `speech_recognition.AudioData`, como antes.

        Convierte a 16 kHz/mono/16 bits y delega. No normaliza: la
        normalizacion del nucleo (`_normalizar_audio`) se aplica antes, sobre
        el WAV, para no cambiar el comportamiento que ya funcionaba.
        """
        wav = audio.get_wav_data(
            convert_rate=config.AUDIO_RATE, convert_width=config.AUDIO_WIDTH
        )
        pcm, rate, width, channels = wav_a_pcm(wav)
        return self.transcribir_pcm(pcm, rate, width, channels, language=language,
                                    timeout=timeout)

    def transcribir_wav(self, wav_bytes, language=None, timeout=None):
        """Igual, pero partiendo de un WAV en memoria."""
        pcm, rate, width, channels = wav_a_pcm(wav_bytes)
        return self.transcribir_pcm(pcm, rate, width, channels, language=language,
                                    timeout=timeout)

    def cerrar(self):
        """Nada que liberar: el modelo vive en el servidor."""
        return None
