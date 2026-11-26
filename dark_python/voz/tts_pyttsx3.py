"""tts_pyttsx3.py — Adaptador PuertoTTS sobre pyttsx3 (SAPI offline, Windows).

Extrae el código que hoy vive en DarkNucleo._hablar_offline
(nucleo/dark_nucleo.py:1755-1776) para que el núcleo deje de conocer el motor.

Comportamiento preservado: pyttsx3 perezoso, selección de voz española
(nombre o id que contenga "spanish"/"es-"/"es_"/"espanol"), rate 180,
habla síncrona (runAndWait).

Limitaciones honestas (documentadas en el contrato PuertoTTS):
  * `cortar()` es no-op: SAPI no permite interrumpir un runAndWait en
    marcha; la cancelación real exige la ruta Wyoming o edge.
  * `parar` solo se consulta ANTES de empezar: si llega a mitad de frase,
    se termina la frase actual.
  * `al_pcm`/`solo_pcm` se aceptan y se ignoran (sin streaming).

Solo stdlib + pyttsx3, perezoso: sin pyttsx3 instalado el módulo importa
igual y `hablar` devuelve False con un log.
"""
import threading


class TtsPyttsx3:
    """PuertoTTS: la voz offline de Windows (SAPI), sin red."""

    def __init__(self, rate=180, log=print):
        self.rate = rate
        self._log = log
        self._sonando = threading.Event()

    # -- contrato: estado --------------------------------------------------

    @property
    def disponible(self):
        try:
            import pyttsx3  # noqa: F401  (perezoso)
            return True
        except ImportError:
            return False

    @property
    def hablando(self):
        return self._sonando.is_set()

    @property
    def sonando(self):
        return self._sonando.is_set()

    @property
    def estado(self):
        return "hablando" if self._sonando.is_set() else "idle"

    @property
    def nivel_salida(self):
        """SAPI reproduce por su cuenta: no hay PCM que medir (contratos/voz.py)."""
        return 0.0

    # -- contrato: síntesis ------------------------------------------------

    def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
        """Habla el texto completo de una vez. Devuelve True si sonó."""
        if not (texto or "").strip():
            return False
        if parar is not None and parar.is_set():
            return False
        if al_pcm is not None or solo_pcm:
            self._log("[TTS-sapi] sin streaming PCM: pide la ruta Wyoming")
        try:
            import pyttsx3  # perezoso
        except ImportError as e:
            self._log(f"[TTS-sapi] pyttsx3 no está instalado: {e}")
            return False
        try:
            engine = pyttsx3.init()
        except Exception as e:
            self._log(f"[TTS-sapi] no pude iniciar SAPI: {e}")
            return False
        self._sonando.set()
        try:
            try:
                for v in engine.getProperty("voices"):
                    nombre = (v.name or "").lower()
                    vid = (v.id or "").lower()
                    if ("spanish" in nombre or "es-" in vid
                            or "es_" in vid or "espanol" in nombre):
                        engine.setProperty("voice", v.id)
                        break
            except Exception:
                pass  # sin voz española declarada: la que haya
            engine.setProperty("rate", self.rate)
            engine.say(texto)
            engine.runAndWait()
            return True
        except Exception as e:
            self._log(f"[TTS-sapi] falló hablando: {e}")
            return False
        finally:
            self._sonando.clear()
            try:
                engine.stop()
            except Exception:
                pass

    def cortar(self):
        """No-op: SAPI no permite interrumpir runAndWait (ver docstring)."""

    def calentar(self, frase="Listo."):
        """No-op: SAPI no tiene arranque en frío."""

    def precachear(self, frases, en_hilo=True):
        """No-op: sin caché en esta ruta."""
