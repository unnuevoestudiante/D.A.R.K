"""
reproductor.py — Salida de audio PCM persistente.

Sustituye a la ruta anterior de TTS (edge-tts -> archivo MP3 -> VLC abre el
archivo y lo reproduce). Aqui el dispositivo de salida se abre **una vez** y se
mantiene abierto: se le van escribiendo los trozos PCM segun llegan por el
socket, y la propia tarjeta de sonido marca el ritmo.

Eso elimina dos costes fijos por frase: abrir el dispositivo y que VLC abra y
descodifique un archivo. Y sobre todo permite **cortar** la reproduccion al
instante, que es lo que hace posible interrumpir a Dark mientras habla.

Sobre `sonando`
---------------
`Stream.write()` **bloquea** mientras la tarjeta consume el audio, asi que
mientras se escribe es cuando suena: al volver de `escribir`, ese audio ya sono
y solo queda en el buffer del dispositivo el ultimo tramo. Por eso "esta
sonando" se calcula como "hace muy poco que escribi audio", con un margen que
cubre ese buffer.

La distincion importa para el barge-in: sintetizar una frase larga tarda
segundos en producir el primer trozo, y medir el eco durante ese silencio daria
un umbral falsamente bajo, con lo que el detector se dispararia solo en cuanto
empezaran a sonar los altavoces.
"""

import threading
import time
from collections import deque

import pyaudio

from . import config
from .cliente import rms

# Margen que se sigue considerando "sonando" despues de la ultima escritura.
# Cubre el buffer del dispositivo y el hueco entre trozos consecutivos.
_MARGEN_SONANDO = 0.20


class ReproductorPCM:
    """Escribe PCM int16 en la salida por defecto, reutilizando el stream."""

    def __init__(self, rate=None, width=None, channels=None, device=None):
        self.rate = rate or 22050  # Piper usa 22 050 Hz en las voces 'high'
        self.width = width or config.AUDIO_WIDTH
        self.channels = channels or config.AUDIO_CHANNELS
        self.device = device

        self._pa = None
        self._stream = None
        self._lock = threading.RLock()
        self._nivel = 0.0
        # Nivel suavizado (~200 ms). El RMS de un bloque de 23 ms salta
        # muchisimo entre segmentos sonoros y huecos; para compararlo con el
        # micro hace falta una escala de tiempo parecida.
        self._nivel_suave = 0.0
        # Historial de lo que fue sonando, para poder decir que estaba saliendo
        # hace ~150 ms. El eco llega al microfono con retardo (altavoz -> aire ->
        # micro), asi que comparar el nivel del micro con el audio que se
        # escribe AHORA mismo desalinea las dos senales justo cuando el habla
        # cambia rapido: en una pausa entre silabas el nivel de salida cae al
        # instante mientras el micro sigue oyendo la silaba anterior, el umbral
        # se desploma y el detector se dispara solo.
        self._historial = deque()
        self._reproduciendo = False
        self._t_ultimo_audio = 0.0
        # Bloques de ~23 ms: lo bastante finos para cortar rapido y lo bastante
        # grandes para no trocear el audio en exceso.
        self._muestras_bloque = 512

    # -- dispositivo -------------------------------------------------------

    def _asegurar(self, rate, width, channels):
        """Abre el stream, o lo reabre si el formato de audio cambio."""
        if self._stream is not None and (rate, width, channels) == (
            self.rate, self.width, self.channels
        ):
            return True

        self.cerrar()
        with self._lock:
            if self._pa is None:
                self._pa = pyaudio.PyAudio()
            self.rate, self.width, self.channels = rate, width, channels
            try:
                self._stream = self._pa.open(
                    format=self._pa.get_format_from_width(width),
                    channels=channels,
                    rate=rate,
                    output=True,
                    frames_per_buffer=self._muestras_bloque,
                    output_device_index=self.device,
                )
            except Exception as e:
                print(f"[voz] no pude abrir la salida de audio: {e}")
                self._stream = None
                return False
        return True

    # -- reproduccion ------------------------------------------------------

    def escribir(self, pcm, parar=None, rate=22050, width=None, channels=None,
                 write_metrics=None):
        """Reproduce un bloque PCM. Devuelve False si se corto o fallo.

        `parar` es un threading.Event: se comprueba entre sub-bloques, asi que
        el corte se nota en ~23 ms.
        """
        metricas = write_metrics if write_metrics is not None else {}
        metricas.update(
            write_count=0,
            write_total_ms=0.0,
            write_max_ms=0.0,
            write_error_type=None,
        )
        if not pcm:
            return True
        width = width or config.AUDIO_WIDTH
        channels = channels or config.AUDIO_CHANNELS
        if not self._asegurar(rate, width, channels):
            metricas["write_error_type"] = "stream_open_failed"
            return False

        bytes_bloque = self._muestras_bloque * width * channels
        self._reproduciendo = True
        try:
            for i in range(0, len(pcm), bytes_bloque):
                if parar is not None and parar.is_set():
                    metricas["write_error_type"] = "interrupted"
                    return False
                bloque = pcm[i:i + bytes_bloque]
                if len(bloque) < bytes_bloque:
                    # Relleno para no dejar el ultimo bloque a medias.
                    bloque = bloque + b"\x00" * (bytes_bloque - len(bloque))
                write_started = time.perf_counter()
                try:
                    self._stream.write(bloque)
                except Exception as error:
                    metricas["write_error_type"] = type(error).__name__
                    return False
                write_ms = (time.perf_counter() - write_started) * 1000.0
                metricas["write_count"] += 1
                metricas["write_total_ms"] += write_ms
                metricas["write_max_ms"] = max(
                    metricas["write_max_ms"], write_ms)
                self._nivel = rms(bloque)
                self._nivel_suave = (0.88 * self._nivel_suave
                                     + 0.12 * self._nivel)
                self._t_ultimo_audio = time.monotonic()
                self._historial.append((self._t_ultimo_audio, self._nivel_suave))
                # No hace falta guardar mucho mas de un retardo.
                while (self._historial
                       and self._t_ultimo_audio - self._historial[0][0]
                       > 2 * config.BARGE_IN_RETARDO_ECO):
                    self._historial.popleft()
            return True
        finally:
            self._reproduciendo = False
            # Ojo: NO se pone _nivel a 0. Se mantiene el ultimo bloque escrito
            # porque es la referencia de eco que consulta el barge-in desde
            # otro hilo, y entre dos trozos (que es casi todo el tiempo) valdria
            # 0. Se limpia al detener o cerrar.

    def detener(self):
        """Corta ya lo que quede en el buffer del dispositivo."""
        with self._lock:
            if self._stream is not None:
                try:
                    # stop_stream descarta el buffer; start_stream lo deja listo
                    # para la siguiente frase.
                    self._stream.stop_stream()
                    self._stream.start_stream()
                except Exception:
                    pass
        self._nivel = 0.0
        self._nivel_suave = 0.0
        self._historial.clear()
        self._t_ultimo_audio = 0.0

    def cerrar(self):
        with self._lock:
            if self._stream is not None:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            if self._pa is not None:
                try:
                    self._pa.terminate()
                except Exception:
                    pass
                self._pa = None
        self._t_ultimo_audio = 0.0
        self._nivel_suave = 0.0
        self._historial.clear()

    # -- estado ------------------------------------------------------------

    @property
    def reproduciendo(self):
        """True mientras se esta dentro de una llamada a `escribir`."""
        return self._reproduciendo

    @property
    def sonando(self):
        """True si hay voz saliendo por los altavoces ahora mismo."""
        if self._stream is None:
            return False
        if self._reproduciendo:
            return True
        return (time.monotonic() - self._t_ultimo_audio) < _MARGEN_SONANDO

    @property
    def nivel_salida(self):
        """RMS suavizado de lo que estaba sonando hace ~150 ms.

        Ese retardo es el del camino altavoz -> aire -> micro. Es la referencia
        de eco que usa el barge-in, y va retrasada a proposito: si se compara el
        micro con el audio que se escribe ahora mismo, las dos senales se
        desalinean justo cuando el habla cambia rapido (una pausa entre silabas
        baja el nivel de salida al instante mientras el micro sigue oyendo la
        silaba anterior) y el umbral se desploma.
        """
        if not self._historial:
            return 0.0
        limite = time.monotonic() - config.BARGE_IN_RETARDO_ECO
        valor = self._historial[0][1]
        for t, nivel in self._historial:
            if t <= limite:
                valor = nivel
            else:
                break
        return valor

    @property
    def abierto(self):
        return self._stream is not None
