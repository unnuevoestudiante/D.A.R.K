"""Contratos del subsistema de VOZ: puertos STT y TTS.

Las firmas NO son inventadas: reproducen exactamente lo que los
consumidores usan hoy (evidencia del audit del 24-oct-2026):

  PuertoSTT (el transcriptor LOCAL que se puede reemplazar: faster-whisper en
  proceso o el `server` de whisper.cpp, elegidos por DARK_STT_LOCAL_PROVIDER):
      * nucleo/dark_nucleo.py:3982  self._stt_local.transcribir_wav(
            wav_data, language="es", prompt=WHISPER_PROMPT, timeout=timeout)
      * nucleo/dark_nucleo.py:4027  self._stt_local.liberar()
      * nucleo/dark_nucleo.py:4032  return self._stt_local.asegurar()
      * voz/stt_whisper_local.py    cargado / asegurar() / liberar() /
            transcribir_wav(...) → {"ok", "texto", "segundos", "error"}
      (igual al Protocol TranscriptorLocal que ya vivía en voz/contratos.py)

  PuertoTTS (implementación de referencia: voz/tts.py TtsWyoming):
      * nucleo/dark_nucleo.py:1672-1677  self._tts_voz.hablar(
            frase, parar=self._filler_cancel, solo_pcm=...)
      * voz/tts.py:107  hablar(texto, parar=None, al_pcm=None, solo_pcm=False)
      * voz/tts.py:477  cortar() · :509  calentar(frase="Listo.")
      * voz/tts.py:527  precachear(frases, en_hilo=True)
      * voz/tts.py:67/71/75/94  disponible / hablando / sonando / estado

Un contrato nunca importa un motor concreto: faster-whisper, whisper.cpp,
edge-tts, pyttsx3, piper o lo que venga viven detrás de las fábricas
(voz/fabrica_stt.py, voz/fabrica_tts.py).

Las señales de calidad que un adaptador sabe medir tienen nombres de contrato
(`SENAL_CONFIANZA`, `SENAL_SIN_VOZ`, `SENAL_REPETICION`) y son opcionales: lo que
decide si un texto se acepta o se descarta vive en `voz/politica_calidad.py`, no
en el adaptador.

Solo stdlib.
"""
from typing import Any, Protocol, TypedDict, runtime_checkable  # noqa: F401


class ResultadoTranscripcion(TypedDict, total=False):
    """Dict que devuelve transcribir_wav (contrato por filesystem hoy:
    los consumidores ya leen 'ok'/'texto'/'error'; 'segundos' lo añade
    el adaptador local cuando mide). total=False por los campos opcionales."""
    ok: bool
    texto: str
    segundos: float
    error: str


# ---------- Vocabulario de calidad, independiente del motor ----------
#
# Un transcriptor no entrega solo texto: entrega cuántos números tiene para
# sostener ese texto. Estos tres nombres son del contrato, no de faster-whisper;
# el adaptador traduce desde los suyos (`avg_logprob`, `no_speech_prob`,
# `compression_ratio`) y la política de rechazo vive en `voz/politica_calidad.py`.
#
# La regla es la misma que en las métricas del chat: **una señal que el motor no
# mide no se manda**. whisper.cpp, por ejemplo, no calcula `repeticion`, así que
# esa pata de la política simplemente no se aplica en vez de rechazar todo.
SENAL_CONFIANZA = "confianza"    # log-prob medio por token (negativo): más cerca de 0, más seguro
SENAL_SIN_VOZ = "sin_voz"        # probabilidad de que el tramo no sea voz (0..1)
SENAL_REPETICION = "repeticion"  # factor de compresión: texto repetitivo lo infla
SEÑALES_CALIDAD = (SENAL_CONFIANZA, SENAL_SIN_VOZ, SENAL_REPETICION)


@runtime_checkable
class PuertoSTT(Protocol):
    """Puerto del transcriptor de voz a texto.

    Implementaciones: voz/stt_whisper_local.py (WhisperLocal, faster-whisper en
    proceso) y voz/stt_whispercpp.py (WhisperCppTranscriptor, el `server` de
    whisper.cpp por HTTP). Un motor nuevo (Vosk, ...) implementa esto y se
    enchufa en voz/fabrica_stt.py sin tocar a ningún consumidor.
    """

    @property
    def cargado(self) -> bool:
        """True si el modelo ya está residente (la carga es perezosa)."""
        ...

    def asegurar(self) -> bool:
        """Carga el modelo si aún no está. True si quedó listo para usar."""
        ...

    def liberar(self) -> None:
        """Descarga el modelo y libera memoria. No-op si no estaba cargado."""
        ...

    def transcribir_wav(
        self,
        wav_bytes: bytes,
        language: str = "es",
        prompt: str = "",
        timeout: float | None = None,
    ) -> ResultadoTranscripcion:
        """Transcribe WAV (PCM 16 kHz mono) → {'ok','texto','segundos','error'}.

        `prompt` es la guía de vocabulario del whisper local; las
        implementaciones que no lo soporten deben aceptarlo e ignorarlo.
        `timeout=None` = sin límite (el llamador decide su política).
        """
        ...


@runtime_checkable
class PuertoTTS(Protocol):
    """Puerto de síntesis y reproducción de voz.

    Implementaciones actuales: voz/tts.py (TtsWyoming sobre Piper),
    voz/tts_edge.py (edge-tts → MP3) y voz/tts_pyttsx3.py (SAPI offline de
    Windows). Un motor nuevo (Coqui, Piper directo, ...) implementa esto y
    se enchufa en voz/fabrica_tts.py sin tocar a ningún consumidor.
    """

    @property
    def disponible(self) -> bool:
        """True si el motor puede sintetizar ahora mismo."""
        ...

    @property
    def hablando(self) -> bool:
        """True si hay una síntesis/reproducción en curso."""
        ...

    @property
    def sonando(self) -> bool:
        """True si hay audio SALIENDO por los altavoces ahora mismo
        (guía del barge-in: puede haber síntesis sin sonido aún)."""
        ...

    @property
    def estado(self) -> Any:
        """Estado interno del motor (diagnóstico; forma libre)."""
        ...

    @property
    def nivel_salida(self) -> float:
        """RMS de lo que suena AHORA por el altavoz (0.0 si no se puede medir).

        Lo consume la guía del barge-in:
          * nucleo/dark_nucleo.py:7325  barge.observar(nivel, True,
                self._tts_voz.nivel_salida)
          * voz/tts.py:85-92  mide el stream de PCM de ReproductorPCM.
        Los motores que reproducen fuera del stream medible (MP3 por VLC, SAPI)
        devuelven 0.0: el detector entiende que no hay salida que cancelar.
        """
        ...

    def hablar(
        self,
        texto: str,
        parar: Any = None,
        al_pcm: Any = None,
        solo_pcm: bool = False,
    ) -> Any:
        """Sintetiza y reproduce `texto`.

        `parar`: threading.Event que cancela la cola de frases.
        `al_pcm` / `solo_pcm`: contrato Wyoming (streaming de PCM); los
        motores sin streaming deben aceptarlos e ignorarlos.
        Devuelve algo truthy si llegó a sonar algo (convención del núcleo).
        """
        ...

    def cortar(self) -> None:
        """Corta el audio en curso (barge-in). No-op si no hay nada."""
        ...

    def calentar(self, frase: str = "Listo.") -> None:
        """Precarga el motor (modelos, caché) para que la primera frase
        real no tarde. No-op en motores sin arranque en frío."""
        ...

    def precachear(self, frases, en_hilo: bool = True) -> None:
        """Sintetiza por adelantado una lista de frases cortas. No-op en
        motores sin caché."""
        ...
