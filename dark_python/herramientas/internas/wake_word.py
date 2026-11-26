"""
dark_wake.py
Detector de wake word en streaming con openWakeWord.

Diseñado para reemplazar el uso de Whisper completo (transcribir + difflib)
en la detección de la palabra de activación.

Requisitos:
    pip install openwakeword onnxruntime pyaudio
"""

import os
import time
from collections import deque

import numpy as np


# Ruta por defecto al modelo entrenado. Asume que dark.onnx vive junto
# a este archivo (o al proyecto en general).
# Mantener la carpeta histórica `herramientas` como base de los modelos.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = os.path.join(BASE_DIR, "dark.onnx")
if not os.path.isfile(DEFAULT_MODEL):
    # Fallback: algunos proyectos lo dejan en la raíz del repo
    _alt = os.path.abspath(os.path.join(BASE_DIR, "..", "dark.onnx"))
    if os.path.isfile(_alt):
        DEFAULT_MODEL = _alt
    else:
        _alt2 = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "dark.onnx"))
        if os.path.isfile(_alt2):
            DEFAULT_MODEL = _alt2

# openWakeWord espera exactamente 80 ms @ 16 kHz = 1280 muestras por frame.
FRAME_WW = 1280


class WakeWordDetector:
    """Detector de wake word en streaming con voting.

    Recibe chunks de 1280 samples (80ms @ 16kHz) int16 PCM y devuelve True
    cuando la palabra se detecta N veces en una ventana de M segundos.

    El voting elimina falsos positivos aislados (un pico puntual del modelo
    no activa nada), pero confirma rápido cuando el usuario realmente dice
    la palabra (3 hits en 1s son ~240ms de audio coincidente).
    """

    def __init__(self,
                 model_path=None,
                 threshold=0.8,
                 hits_requeridos=3,
                 ventana_seg=1.0):
        from openwakeword.model import Model

        if model_path is None:
            model_path = DEFAULT_MODEL
        if not os.path.isfile(model_path):
            raise FileNotFoundError(
                f"No encontré el modelo de wake word en {model_path}. "
                f"Copiá dark.onnx junto a dark_wake.py."
            )

        self.model = Model(wakeword_models=[model_path])
        self.model_path = model_path
        self.threshold = threshold
        self.hits_requeridos = hits_requeridos
        self.ventana_seg = ventana_seg
        self._hits = deque()

    def feed(self, audio_int16):
        """Acepta cualquier tamaño; parte en frames de FRAME_WW (1280) internamente;
        cortocircuita en el primer hit. Devuelve True si se confirma la wake word."""
        n = int(audio_int16.shape[0])
        if n == FRAME_WW:
            # Caso normal: un frame exacto.
            return self._feed_frame(audio_int16)
        if n < FRAME_WW:
            print(f"[wake] frame demasiado corto ({n} < {FRAME_WW}); se ignora",
                  flush=True)
            return False
        if n % FRAME_WW != 0:
            print(f"[wake] bloque de {n} muestras no es múltiplo de {FRAME_WW}; "
                  f"se procesan solo los frames completos y se descarta el residuo",
                  flush=True)
        # Procesar frame a frame; cortocircuito: si uno dispara, no seguir.
        for i in range(0, n - FRAME_WW + 1, FRAME_WW):
            if self._feed_frame(audio_int16[i:i + FRAME_WW]):
                return True
        return False

    def _feed_frame(self, audio_int16):
        """Procesa exactamente FRAME_WW muestras (80 ms @ 16 kHz).
        Devuelve True cuando se confirma la wake word."""
        prediction = self.model.predict(audio_int16)

        # El modelo puede devolver varios nombres si cargaste varios .onnx.
        # Nos interesa el score más alto de todos.
        max_score = 0.0
        for score in prediction.values():
            if score > max_score:
                max_score = score

        ahora = time.time()

        # Purgar hits viejos de la ventana
        while self._hits and ahora - self._hits[0] > self.ventana_seg:
            self._hits.popleft()

        if max_score >= self.threshold:
            self._hits.append(ahora)
            if len(self._hits) >= self.hits_requeridos:
                # Confirmado: limpiar para no re-disparar inmediatamente
                self._hits.clear()
                self.reset()
                return True

        return False

    def reset(self):
        """Resetea el buffer interno del modelo. Llamar tras una detección
        confirmada para evitar que se re-dispare con la cola del mismo audio."""
        if hasattr(self.model, "reset"):
            self.model.reset()


if __name__ == "__main__":
    import pyaudio

    RATE = 16000
    CHUNK = 1280

    detector = WakeWordDetector()
    print(f"Modelo: {detector.model_path}")
    print(f"Threshold: {detector.threshold} | "
          f"Voting: {detector.hits_requeridos} hits en {detector.ventana_seg}s")
    print("Di 'dark' para probar. Ctrl+C para salir.")

    pa = pyaudio.PyAudio()
    stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                     input=True, frames_per_buffer=CHUNK)
    try:
        while True:
            chunk = stream.read(CHUNK, exception_on_overflow=False)
            audio_np = np.frombuffer(chunk, dtype=np.int16)
            if detector.feed(audio_np):
                print(">>> WAKE WORD DETECTADA")
    except KeyboardInterrupt:
        pass
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
