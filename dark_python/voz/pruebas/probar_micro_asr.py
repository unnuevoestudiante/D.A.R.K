"""Escucha el microfono REAL y transcribe cada turno con el ASR de Wyoming.

Valida de punta a punta la entrada de voz (micro -> VAD -> turno -> Whisper) y,
de paso, sirve para calibrar el VAD: informa del ruido de fondo, del umbral
efectivo y del nivel de cada bloque.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.probar_micro_asr [segundos]
"""
import statistics
import sys
import time

from voz import supervisor
from voz.micro import Capturador, Micro
from voz.stt import SttWyoming

SEGUNDOS = float(sys.argv[1]) if len(sys.argv) > 1 else 45.0


def main():
    print("Arrancando el ASR (la primera vez tarda en cargar el modelo)...",
          flush=True)
    if not supervisor.whisper.asegurar():
        print("El servidor ASR no quedo listo.", flush=True)
        return 1

    stt = SttWyoming(log=print)
    micro = Micro()
    if not micro.abrir():
        return 1

    cap = Capturador()
    print("", flush=True)
    print("=" * 66, flush=True)
    print(f"ESCUCHANDO {SEGUNDOS:.0f} SEGUNDOS. Habla con normalidad.", flush=True)
    print("Prueba frases como: 'Dark, que hora es'  o  'pon musica'.", flush=True)
    print("=" * 66, flush=True)

    niveles = []
    turnos = 0
    t0 = time.time()
    ultimo_informe = t0
    try:
        while time.time() - t0 < SEGUNDOS:
            pcm = micro.leer()
            if pcm is None:
                continue
            r = cap.procesar(pcm)
            niveles.append(cap.vad.ultimo_nivel)

            if r == "inicio_voz":
                print(f"  [{time.time() - t0:5.1f}s] empieza la voz "
                      f"(nivel {cap.vad.ultimo_nivel:.0f}, "
                      f"umbral {cap.vad.umbral:.0f})", flush=True)
            elif r is not None:
                turnos += 1
                print(f"  [{time.time() - t0:5.1f}s] turno de {r.duracion:.2f}s "
                      f"-> transcribiendo...", flush=True)
                res = stt.transcribir_pcm(r.pcm, r.rate, r.width, r.channels)
                if res.get("ok"):
                    print(f"        TEXTO: {res['texto']!r}  "
                          f"({res['segundos']:.2f}s)", flush=True)
                else:
                    print(f"        FALLO: {res.get('error')}", flush=True)

            if time.time() - ultimo_informe >= 3.0:
                ultimo_informe = time.time()
                print(f"  [{time.time() - t0:5.1f}s] nivel {cap.vad.ultimo_nivel:>6.0f}"
                      f" / umbral {cap.vad.umbral:>6.0f}"
                      f" / ruido {cap.vad.ruido or 0:>6.0f}", flush=True)
    finally:
        micro.cerrar()
        supervisor.detener_todo()

    print("", flush=True)
    print("=" * 66, flush=True)
    print(f"RESUMEN  (dispositivo [{micro.dispositivo}] "
          f"{micro.dispositivo_nombre})", flush=True)
    if niveles:
        o = sorted(niveles)
        n = len(o)
        print(f"  bloques: {n}   turnos detectados: {turnos}", flush=True)
        print(f"  nivel minimo   : {o[0]:.0f}", flush=True)
        print(f"  nivel mediana  : {o[n // 2]:.0f}", flush=True)
        print(f"  nivel p90      : {o[int(n * 0.9)]:.0f}", flush=True)
        print(f"  nivel maximo   : {o[-1]:.0f}", flush=True)
        print(f"  ruido de fondo : {(cap.vad.ruido or 0):.0f}", flush=True)
        print(f"  umbral final   : {cap.vad.umbral:.0f}", flush=True)
        if turnos == 0:
            print("  AVISO: no se detecto ningun turno. Si hablaste, sube la "
                  "sensibilidad bajando VOZ_VAD_RMS_MINIMO.", flush=True)
    print("=" * 66, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
