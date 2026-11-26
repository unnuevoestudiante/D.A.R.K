"""Prueba aislada del wakeword entrenado, con voting y threshold alto."""
import sys
import os
import time

sys.path.insert(0, r"C:\Users\samue\Desktop\D.A.R.K\dark_python")
from herramientas.dark_wake import WakeWordDetector

import numpy as np
import pyaudio

RATE = 16000
CHUNK = 1280

# Threshold más alto + voting: 3 hits en 1 segundo = wake word real
THRESHOLD = 0.8
VENTANA_SEG = 1.0
HITS_REQUERIDOS = 3

detector = WakeWordDetector(model_names=("dark.onnx",), threshold=THRESHOLD)
pa = pyaudio.PyAudio()
stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                 input=True, frames_per_buffer=CHUNK)

print(f"Threshold: {THRESHOLD} | Voting: {HITS_REQUERIDOS} hits en {VENTANA_SEG}s")
print("Di 'dark' varias veces. Ctrl+C para salir.")
print("También probá hablar normal sin decir 'dark' durante 30 segundos.")
print()

buffer_hits = []  # timestamps de hits recientes
try:
    while True:
        chunk = stream.read(CHUNK, exception_on_overflow=False)
        audio_np = np.frombuffer(chunk, dtype=np.int16)

        if detector.feed(audio_np):
            ahora = time.time()
            buffer_hits.append(ahora)
            buffer_hits = [t for t in buffer_hits if ahora - t <= VENTANA_SEG]

            if len(buffer_hits) >= HITS_REQUERIDOS:
                print(f">>> WAKE WORD DETECTADA ({len(buffer_hits)} hits)")
                detector.reset()
                buffer_hits = []
        # limpiamos el buffer aunque no haya hit
        ahora = time.time()
        buffer_hits = [t for t in buffer_hits if ahora - t <= VENTANA_SEG]

except KeyboardInterrupt:
    pass
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()