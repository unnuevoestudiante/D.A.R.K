"""tts_edge.py — Adaptador PuertoTTS sobre edge-tts (ruta online → MP3).

Extrae el código que hoy vive dentro de nucleo/dark_nucleo.py
(_generar_audio_edge :1689, _tts_respaldo :1700-1752, _reproducir_mp3,
_dividir_frases :1778) para que el núcleo deje de conocer el motor.

Comportamiento preservado: mismas constantes de voz (VOICE_NAME
"es-EC-LuisNeural", rate "+10%", pitch "+1Hz"), misma división en frases
(máx. 140 chars), mismo MP3 temporal por frase, mismo bucle de reproducción
con VLC y cancelación por evento.

Diferencias conscientes respecto al monolito:
  * Los motores (edge_tts, vlc) se importan PEREZOSAMENTE, dentro de los
    métodos: sin red o sin edge-tts instalado, el módulo importa igual.
  * `al_pcm`/`solo_pcm` se aceptan y se ignoran (edge-tts no hace streaming;
    lo documenta el contrato PuertoTTS).
  * `cortar()` funciona vía un evento interno; el llamador también puede
    pasar su propio Event en `parar` (como hace el núcleo hoy).

Solo stdlib + edge-tts + vlc, ambos perezosos.
"""
import asyncio
import os
import re
import tempfile
import threading
import time
import uuid


def _dividir_frases(texto, max_len=140):
    """Copia exacta de DarkNucleo._dividir_frases (dark_nucleo.py:1778)."""
    texto = (texto or "").strip()
    if not texto:
        return []
    partes = re.split(r"(?<=[.!?])\s+", texto)
    resultado = []
    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        if len(parte) <= max_len:
            resultado.append(parte)
            continue
        sub = re.split(r"(?<=,)\s+", parte)
        buffer = ""
        for s in sub:
            if len(buffer) + len(s) + 1 <= max_len:
                buffer = (buffer + " " + s).strip()
            else:
                if buffer:
                    resultado.append(buffer)
                buffer = s
        if buffer:
            resultado.append(buffer)
    return resultado


class TtsEdge:
    """PuertoTTS: edge-tts (Microsoft, red) → MP3 → VLC."""

    def __init__(self, voz_nombre=None, rate=None, pitch=None,
                 carpeta_temp=None, reproductor_mp3=None, log=print):
        # Config por entorno (mismos valores que las constantes del núcleo):
        self.voz_nombre = (voz_nombre
                           or os.environ.get("DARK_TTS_EDGE_VOICE",
                                             "es-EC-LuisNeural"))
        self.rate = rate or os.environ.get("DARK_TTS_EDGE_RATE", "+10%")
        self.pitch = pitch or os.environ.get("DARK_TTS_EDGE_PITCH", "+1Hz")
        self.carpeta_temp = carpeta_temp or os.path.join(
            tempfile.gettempdir(), "dark_tts_mp3")
        # Inyección del reproductor: el núcleo puede pasar su _reproducir_mp3
        # (misma firma (ruta, cancel_event)) durante la migración.
        self._reproductor_mp3 = reproductor_mp3
        self._log = log
        self._cortado = threading.Event()
        self._sonando = threading.Event()

    # -- contrato: estado --------------------------------------------------

    @property
    def disponible(self):
        try:
            import edge_tts  # noqa: F401  (perezoso)
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
        """Sin PCM medible: el MP3 sale por VLC, no por un stream nuestro.

        0.0 es lo que espera `DetectorBargeIn.observar` para entender que no
        hay salida que cancelar (voz/micro.py:594).
        """
        return 0.0

    # -- contrato: síntesis ------------------------------------------------

    def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
        """Sintetiza frase a frase y reproduce. Devuelve True si sonó algo.

        `al_pcm`/`solo_pcm` se ignoran (sin streaming); ver contrato.
        """
        if al_pcm is not None or solo_pcm:
            self._log("[TTS-edge] sin streaming PCM: pide la ruta Wyoming")
        frases = _dividir_frases(texto)
        if not frases:
            return False
        self._cortado.clear()
        os.makedirs(self.carpeta_temp, exist_ok=True)
        sono = False
        try:
            for frase in frases:
                if self._cortado.is_set() or (parar is not None and parar.is_set()):
                    break
                ruta = os.path.join(self.carpeta_temp, f"{uuid.uuid4().hex}.mp3")
                try:
                    asyncio.run(self._generar_audio(frase, ruta))
                except Exception as e:
                    self._log(f"[TTS-edge] síntesis falló ({e}); frase perdida")
                    continue
                if self._reproducir(ruta, parar):
                    sono = True
                try:
                    os.remove(ruta)
                except OSError:
                    pass
        finally:
            self._sonando.clear()
        return sono

    def cortar(self):
        """Corta la síntesis/reproducción en curso (y las frases restantes)."""
        self._cortado.set()

    def calentar(self, frase="Listo."):
        """No-op: edge-tts no tiene arranque en frío local."""

    def precachear(self, frases, en_hilo=True):
        """No-op: sin caché de PCM en esta ruta (frases repetidas se
        re-sintetizan; usa la ruta Wyoming si te importa la latencia)."""

    # -- internos ------------------------------------------------------------

    async def _generar_audio(self, texto, ruta_salida):
        """Igual a DarkNucleo._generar_audio_edge (dark_nucleo.py:1689)."""
        import edge_tts  # perezoso
        communicate = edge_tts.Communicate(
            texto, voice=self.voz_nombre, rate=self.rate, pitch=self.pitch,
        )
        await communicate.save(ruta_salida)

    def _reproducir(self, ruta, parar=None):
        """Reproduce el MP3 cancelando por evento. Copia del bucle de
        DarkNucleo._reproducir_mp3, con VLC perezoso."""
        if self._reproductor_mp3 is not None:
            self._sonando.set()
            try:
                self._reproductor_mp3(ruta, parar)
            finally:
                self._sonando.clear()
            return True
        from utils.vlc_seguro import cargar_vlc

        vlc = cargar_vlc()  # perezoso; python-vlc no lanza ImportError si falta libvlc
        if vlc is None:
            self._log("[TTS-edge] VLC no disponible; no puedo reproducir")
            return False
        try:
            instancia = vlc.Instance()
        except Exception as e:
            self._log(f"[TTS-edge] VLC no arrancó: {e}")
            return False
        media = instancia.media_new(ruta)
        player = instancia.media_player_new()
        player.set_media(media)
        player.play()
        self._sonando.set()
        try:
            for _ in range(30):
                if player.is_playing():
                    break
                if self._cortado.is_set() or (parar is not None and parar.is_set()):
                    player.stop()
                    return False
                time.sleep(0.05)
            while player.is_playing():
                if self._cortado.is_set() or (parar is not None and parar.is_set()):
                    player.stop()
                    break
                time.sleep(0.05)
        finally:
            player.stop()
            player.release()
            media.release()
            self._sonando.clear()
        return True
