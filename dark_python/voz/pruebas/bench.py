"""Mide las latencias del subsistema de voz en caliente.

Lo que percibe el usuario:
  * TTS: de pedir la frase a oir el primer trozo de audio.
  * ASR: de terminar de hablar (audio-stop) a tener la transcripcion.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.bench
"""
import asyncio
import statistics
import sys
import time

from voz import supervisor
from voz.cliente import resamplear
from voz.stt import SttWyoming
from voz.tts import TtsWyoming

CORTAS = ["Señor?", "Ya lo reviso...", "Dame un segundo"]
LARGA = ("Claro, señor. He revisado el estado del sistema y todo funciona "
         "con normalidad. La memoria está al cuarenta por ciento.")


class Falso:
    reproduciendo = False
    nivel_salida = 0.0
    abierto = True

    def __init__(self):
        self.pcm = bytearray()
        self.rate = 22050

    def escribir(self, trozo, parar=None, rate=22050, width=2, channels=1):
        self.pcm.extend(trozo)
        self.rate = rate
        return True

    def detener(self):
        return None

    def cerrar(self):
        return None


def main():
    print("arrancando servidores...")
    if not supervisor.arrancar_todo(esperar=True):
        print("no pude arrancar los servidores")
        return 1

    falso = Falso()
    tts = TtsWyoming(reproductor=falso, log=print)
    print("\nprecalentando el TTS (carga el modelo de voz)...")
    tts.calentar()

    print("\n" + "=" * 60)
    print("TTS EN CALIENTE (ms hasta el primer audio)")
    print("=" * 60)
    for frase in CORTAS:
        falso.pcm = bytearray()
        r = tts.hablar(frase)
        pm = r.get("primer_ms")
        print(f"  {pm if pm is None else round(pm):>6} ms   {frase!r}")

    falso.pcm = bytearray()
    r = tts.hablar(LARGA)
    pcm, rate = bytes(falso.pcm), falso.rate
    dur = len(pcm) / (rate * 2) if rate else 0
    print(f"  {round(r.get('primer_ms') or 0):>6} ms   frase larga "
          f"({dur:.2f}s de audio, total {round(r.get('total_ms') or 0)} ms)")

    print("\n" + "=" * 60)
    print("ASR EN CALIENTE (ms de fin de habla a transcripcion)")
    print("=" * 60)
    stt = SttWyoming(log=print)
    audio16 = resamplear(pcm, rate, 16000)
    print(f"  audio de prueba: {len(audio16) / 32000:.2f}s")
    tiempos = []
    for i in range(4):
        r = stt.transcribir_pcm(audio16, 16000)
        ms = (r.get("segundos") or 0) * 1000
        if not r.get("ok"):
            print(f"  intento {i + 1}: fallo ({r.get('error')})")
            continue
        tiempos.append(ms)
        etiqueta = "frio" if i == 0 else "caliente"
        print(f"  intento {i + 1} ({etiqueta}): {ms:>6.0f} ms  -> {r['texto']!r}")
    if len(tiempos) > 1:
        cal = tiempos[1:]
        print(f"\n  ASR en caliente: min={min(cal):.0f} ms  "
              f"mediana={statistics.median(cal):.0f} ms  max={max(cal):.0f} ms")
        seg = len(audio16) / 32000
        print(f"  ({seg:.2f}s de audio -> {statistics.median(cal) / 1000 / seg:.2f}x "
              f"el tiempo real)")

    supervisor.detener_todo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
