"""Compara dos modelos de Whisper en latencia y acierto.

Sintetiza un conjunto de frases con Piper (texto conocido), las transcribe con
el modelo indicado y mide cuanto tarda y cuantas palabras acierta.

Ojo: el audio de Piper es limpio, asi que el acierto absoluto sale optimista
comparado con el micro real. Lo util es la COMPARACION entre modelos.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.comparar_modelos small
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.comparar_modelos base
"""
import sys
import time

from voz import config, supervisor
from voz.cliente import resamplear
from voz.stt import SttWyoming
from voz.tts import TtsWyoming

FRASES = [
    "Dark, pon música.",
    "¿Qué hora es?",
    "Abre el navegador.",
    "Recuérdame llamar a mamá mañana.",
    "Sube el volumen un poco.",
    "¿Cuánta memoria libre tengo?",
]


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


def normalizar(texto):
    limpio = (texto or "").lower()
    for c in ".,;:¿?¡!«»\"'()":
        limpio = limpio.replace(c, " ")
    return [p for p in limpio.split() if p]


def acierto(original, transcripcion):
    """Proporcion de palabras del original que aparecen en la transcripcion."""
    a, b = normalizar(original), normalizar(transcripcion)
    if not a:
        return 0.0
    restantes = list(b)
    bien = 0
    for palabra in a:
        if palabra in restantes:
            restantes.remove(palabra)
            bien += 1
    return bien / len(a)


def main():
    modelo = sys.argv[1] if len(sys.argv) > 1 else "small"
    hilos = int(sys.argv[2]) if len(sys.argv) > 2 else config.WHISPER_CPU_THREADS
    config.WHISPER_MODEL = modelo
    config.WHISPER_CPU_THREADS = hilos
    print(f"### MODELO: {modelo}   HILOS: {hilos}", flush=True)

    if not supervisor.arrancar_todo(esperar=True):
        print("no pude arrancar los servidores")
        return 1

    tts = TtsWyoming(reproductor=Falso(), log=lambda *a: None)
    falso = tts.reproductor
    t_tts = time.time()
    tts.calentar()
    print(f"piper precalentado en {time.time() - t_tts:.1f}s", flush=True)

    stt = SttWyoming(log=lambda *a: None)
    # Una transcripcion de calentamiento: la primera paga la inicializacion del
    # encoder de CTranslate2 y no representa el uso normal.
    falso.pcm = bytearray()
    tts.hablar("Calentando.")
    stt.transcribir_pcm(resamplear(bytes(falso.pcm), falso.rate, 16000), 16000)

    tiempos, aciertos = [], []
    for frase in FRASES:
        falso.pcm = bytearray()
        tts.hablar(frase)
        pcm16 = resamplear(bytes(falso.pcm), falso.rate, 16000)
        dur = len(pcm16) / 32000
        r = stt.transcribir_pcm(pcm16, 16000)
        ms = (r.get("segundos") or 0) * 1000
        ac = acierto(frase, r.get("texto"))
        tiempos.append(ms)
        aciertos.append(ac)
        print(f"  {ms:>6.0f} ms  audio {dur:4.2f}s  acierto {ac * 100:>3.0f}%  "
              f"{frase!r}", flush=True)
        print(f"          -> {r.get('texto')!r}", flush=True)

    import statistics

    print(f"\n  RESUMEN {modelo} @ {hilos} hilos: latencia mediana "
          f"{statistics.median(tiempos):.0f} ms"
          f"  (min {min(tiempos):.0f}, max {max(tiempos):.0f})"
          f"  acierto medio {100 * sum(aciertos) / len(aciertos):.1f}%", flush=True)

    supervisor.detener_todo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
