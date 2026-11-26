"""Salida de audio nativa de Windows, sin dependencias nuevas.

El payload no trae `pyaudio` ni VLC. Para que una voz por API suene igual, el audio PCM
se envuelve en un WAV y se reproduce con `winsound` (biblioteca estándar).

  * Medido en esta caja: `PlaySound(datos, SND_MEMORY)` es síncrono y **nada lo interrumpe
    desde otro hilo** (ni `SND_PURGE` ni `None`), así que el barge-in no podría cortar la voz.
    Por eso se reproduce **desde un archivo temporal en modo asíncrono**
    (`SND_FILENAME | SND_ASYNC`), que sí se corta al instante con `SND_PURGE`. El archivo
    vive en una carpeta temporal propia y se borra al terminar.
  * `reproducir()` espera lo que dura el audio (o hasta que llegue `parar`/`cortar()`), así que
    bloquea el hilo que habla, igual que cualquier otro TTS.
  * `nivel_salida` es el RMS (int16) de la ventana de 50 ms que suena AHORA, calculado
    del propio PCM y de cuánto lleva sonando: lo que pide el barge-in (contratos/voz.py).

Solo biblioteca estándar. Importar este módulo no importa `winsound`.
"""
from __future__ import annotations

import array
import io
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import uuid
import wave
from typing import Any, Callable

VENTANA_NIVEL_S = 0.05
#: Holgura tras la duración del audio antes de dar la reproducción por terminada.
MARGEN_FIN_S = 0.25


def pcm_a_wav(pcm: bytes, rate: int, canales: int = 1, ancho: int = 2) -> bytes:
    memoria = io.BytesIO()
    with wave.open(memoria, "wb") as w:
        w.setnchannels(canales)
        w.setsampwidth(ancho)
        w.setframerate(rate)
        w.writeframes(pcm)
    return memoria.getvalue()


def leer_wav(datos: bytes) -> tuple[bytes, int, int, int]:
    """(pcm, rate, canales, ancho) de un WAV en memoria. Lanza ValueError si no es válido."""
    try:
        with wave.open(io.BytesIO(datos), "rb") as w:
            return w.readframes(w.getnframes()), w.getframerate(), w.getnchannels(), w.getsampwidth()
    except (wave.Error, EOFError) as error:
        raise ValueError("el audio recibido no es un WAV válido") from error


def duracion_s(pcm: bytes, rate: int, canales: int = 1, ancho: int = 2) -> float:
    return len(pcm) / float(max(1, rate * canales * ancho))


def rms_ventana(pcm: bytes, rate: int, canales: int, ancho: int, desde_s: float,
                ventana_s: float = VENTANA_NIVEL_S) -> float:
    """RMS int16 de `ventana_s` de audio a partir de `desde_s`. 0.0 si no es medible."""
    if ancho != 2 or rate <= 0:
        return 0.0
    paso = canales * ancho
    inicio = max(0, int(desde_s * rate)) * paso
    fin = inicio + max(1, int(ventana_s * rate)) * paso
    trozo = pcm[inicio:fin]
    trozo = trozo[: len(trozo) - len(trozo) % 2]
    if not trozo:
        return 0.0
    muestras = array.array("h")
    muestras.frombytes(trozo)
    if sys.byteorder == "big":  # el PCM del proveedor es little-endian
        muestras.byteswap()
    return math.sqrt(sum(m * m for m in muestras) / len(muestras))


class SalidaNativa:
    """Reproduce PCM por los altavoces con `winsound`."""

    def __init__(self, winsound_mod: Any = None, reloj: Callable[[], float] = time.monotonic) -> None:
        self._ws = winsound_mod
        self._reloj = reloj
        self._lock = threading.Lock()
        self._corte = threading.Event()
        self._inicio: float | None = None
        self._audio: tuple[bytes, int, int, int] | None = None
        self._carpeta: str | None = None

    def _winsound(self) -> Any:
        if self._ws is None and sys.platform == "win32":
            import winsound

            self._ws = winsound
        return self._ws

    @property
    def disponible(self) -> bool:
        return self._winsound() is not None

    @property
    def sonando(self) -> bool:
        return self._inicio is not None

    @property
    def nivel_salida(self) -> float:
        inicio, audio = self._inicio, self._audio
        if inicio is None or audio is None:
            return 0.0
        pcm, rate, canales, ancho = audio
        return rms_ventana(pcm, rate, canales, ancho, self._reloj() - inicio)

    def cortar(self) -> None:
        self._corte.set()
        ws = self._winsound()
        if ws is not None:
            try:
                ws.PlaySound(None, ws.SND_PURGE)
            except Exception:
                pass

    def _carpeta_temporal(self) -> str:
        if self._carpeta is None or not os.path.isdir(self._carpeta):
            self._carpeta = tempfile.mkdtemp(prefix="dark-salida-")
        return self._carpeta

    def reproducir(self, pcm: bytes, rate: int, canales: int = 1, ancho: int = 2,
                   parar: Any = None) -> bool:
        """Suena `pcm` y vuelve cuando termina o se corta. True si llegó a sonar."""
        ws = self._winsound()
        if ws is None or not pcm:
            return False
        if parar is not None and parar.is_set():
            return False
        ruta = os.path.join(self._carpeta_temporal(), uuid.uuid4().hex + ".wav")
        with self._lock:  # una sola reproducción a la vez: winsound solo admite una
            self._corte.clear()
            try:
                with open(ruta, "wb") as archivo:
                    archivo.write(pcm_a_wav(pcm, rate, canales, ancho))
                self._audio = (pcm, rate, canales, ancho)
                self._inicio = self._reloj()
                ws.PlaySound(ruta, ws.SND_FILENAME | ws.SND_ASYNC)
                fin = time.monotonic() + duracion_s(pcm, rate, canales, ancho) + MARGEN_FIN_S
                while True:
                    restante = fin - time.monotonic()
                    if restante <= 0 or self._corte.wait(min(0.05, restante)):
                        break
                    if parar is not None and parar.is_set():
                        self.cortar()
                        break
                return True
            except Exception:
                return False
            finally:
                self._inicio, self._audio = None, None
                try:
                    ws.PlaySound(None, ws.SND_PURGE)  # suelta el archivo antes de borrarlo
                except Exception:
                    pass
                try:
                    os.remove(ruta)
                except OSError:
                    pass

    def cerrar(self) -> None:
        """Borra la carpeta temporal (al salir)."""
        if self._carpeta:
            shutil.rmtree(self._carpeta, ignore_errors=True)
            self._carpeta = None
