"""
voz — Subsistema de voz de Dark sobre el protocolo Wyoming.

Reemplaza el STT (faster-whisper en proceso) y el TTS (edge-tts + VLC) por dos
servidores Wyoming residentes:

    * wyoming-faster-whisper  -> ASR en tcp://127.0.0.1:10300
    * wyoming-piper           -> TTS en tcp://127.0.0.1:10200

Ventajas frente al esquema anterior:

    * El modelo de voz vive en su propio proceso: no compite por el GIL con
      Ollama, VLC ni el overlay, y no hay que recargarlo.
    * El ASR hace endpointing con Silero VAD en el servidor, asi que devuelve
      la transcripcion en cuanto detecta silencio, sin esperar al cliente.
    * El TTS entrega PCM en streaming, que se reproduce mientras se genera:
      el primer sonido llega antes y desaparece la dependencia de la red.

Uso:
    from voz import supervisor, TtsWyoming, SttWyoming

    supervisor.asegurar()          # arranca/monitorea los dos servidores
    tts = TtsWyoming()
    tts.hablar("Hola, senor.")
"""

from . import config  # noqa: F401

__all__ = ["config"]
