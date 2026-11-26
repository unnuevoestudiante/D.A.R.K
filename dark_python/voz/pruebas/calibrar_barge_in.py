"""Calibra el barge-in con los altavoces y el microfonos REALES.

Que hace
--------
Repite varias rondas de: Dark habla por los altavoces -> tu lo interrumpes
hablando. Mientras, mide en cada bloque:

  * el nivel del micro (que incluye el eco de los altavoces + tu voz),
  * el umbral que calcula el detector,
  * si el detector se dispara y en que momento.

Con eso se separan dos cosas que hasta ahora eran suposiciones: cuanto eco
devuelve TU equipo, y a que nivel hablas tu. De ahi sale el margen.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.calibrar_barge_in [rondas]

NO guarda audio: solo niveles RMS.
"""
import statistics
import sys
import threading
import time

from voz import supervisor
from voz.cliente import rms
from voz.micro import DetectorBargeIn, Micro
from voz.reproductor import ReproductorPCM
from voz.tts import TtsWyoming

RONDAS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
# "voz"  -> el usuario interrumpe (mide si se detecta)
# "silencio" -> el usuario NO habla (mide falsos positivos: cualquier corte es
#               un error, porque no habia nada que interrumpir)
MODO = sys.argv[2] if len(sys.argv) > 2 else "voz"
# Segundos de espera antes de empezar, para poder preparar el volumen.
ESPERA = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

# Bastante larga para que te de tiempo a interrumpir varias veces.
FRASE = (
    "Te cuento un poco como va el sistema de voz que acabo de montar. "
    "Ahora mismo estoy hablando por los altavoces, mientras el microfono "
    "sigue escuchando lo que pasa en la habitacion. Si en algun momento "
    "empiezas a hablar tu, el detector deberia notarlo y cortarme. "
    "Sigo hablando un rato mas para que tengas tiempo de sobra."
)

DUR_BLOQUE = 0.08  # 1280 muestras a 16 kHz


def main():
    print("Arrancando el TTS...", flush=True)
    if not supervisor.piper.asegurar():
        print("El servidor TTS no quedo listo.", flush=True)
        return 1

    micro = Micro()
    if not micro.abrir():
        return 1

    tts = TtsWyoming(log=lambda *a: None)
    reproductor = tts.reproductor
    if not isinstance(reproductor, ReproductorPCM):
        print("Este script necesita el reproductor real.", flush=True)
        return 1

    print("Precalentando la voz...", flush=True)
    tts.calentar()

    print("", flush=True)
    print("=" * 70, flush=True)
    print(f"VAMOS A HACER {RONDAS} RONDAS.", flush=True)
    print("En cada ronda Dark habla ~20 s por los altavoces.", flush=True)
    if MODO == "silencio":
        print("", flush=True)
        print("  *** NO HABLES. Ni una palabra durante toda la prueba. ***", flush=True)
        print("  Sirve para medir si el detector se dispara solo con el eco.", flush=True)
        print("  Cualquier corte cuenta como error.", flush=True)
    else:
        print("TU TAREA: cuando empieces a oirlo, espera un segundo y di algo",
              flush=True)
        print("seguido durante medio segundo o mas, por ejemplo:", flush=True)
        print("    'Dark, para'   'Oye, esperate'   'No, no, eso no'", flush=True)
    print("Deja el volumen en el nivel que usas normalmente.", flush=True)
    print("=" * 70, flush=True)

    if ESPERA > 0:
        print(f"\n>>> Empiezo en {ESPERA:.0f} segundos. Preparate AHORA. <<<\n",
              flush=True)
        restante = ESPERA
        while restante > 0:
            time.sleep(min(5.0, restante))
            restante -= 5.0
            if restante > 0:
                print(f"    ... {restante:.0f} s", flush=True)
        print(">>> EMPEZANDO <<<\n", flush=True)

    rondas = []
    # Un unico detector para toda la sesion, como en el nucleo: el
    # acoplamiento eco/salida se aprende una vez y se conserva entre frases.
    det = DetectorBargeIn()
    for n in range(1, RONDAS + 1):
        print(f"\n--- ronda {n}/{RONDAS}: hablando...", flush=True)
        parar = threading.Event()
        hilo = threading.Thread(target=tts.hablar, args=(FRASE, parar),
                                daemon=True)
        hilo.start()
        time.sleep(0.05)

        det.pausa()
        registros = []          # (nivel, habia_sonido, sin_separacion)
        umbrales = []
        t0 = time.monotonic()
        disparo_ms = None
        # Se sigue mientras el hilo sintetiza O mientras quede voz sonando: la
        # sintesis tarda segundos y la reproduccion continua despues.
        while hilo.is_alive() or tts.sonando:
            pcm = micro.leer()
            if pcm is None:
                continue
            nivel = rms(pcm)
            sonando = tts.sonando
            # Al detector solo se le dice "reproduciendo" cuando SUENA, y se le
            # pasa lo que esta saliendo por el altavoz para que calcule el eco
            # esperado en vez de adivinarlo.
            disparo = det.observar(nivel, reproduciendo=sonando,
                                   nivel_salida=tts.nivel_salida)
            registros.append((nivel, sonando, det.sin_separacion))
            if disparo:
                disparo_ms = (time.monotonic() - t0) * 1000
                umbrales.append(det.ultimo_umbral)
                parar.set()
                tts.cortar()
                micro.drenar(6)
                break
            if sonando:
                umbrales.append(det.ultimo_umbral)

        parar.set()
        hilo.join(timeout=3)

        con_sonido = [n for (n, s, _x) in registros if s]
        ciegos = sum(1 for (_n, s, x) in registros if s and x)
        if not con_sonido:
            print("   (no llego a sonar nada, o el micro no leyo audio)",
                  flush=True)
            continue

        n_eco = max(1, int(0.25 / DUR_BLOQUE))
        eco_base = statistics.fmean(con_sonido[:n_eco])
        resto = con_sonido[n_eco:] or con_sonido
        eco_medio = statistics.median(resto)
        pico = max(con_sonido)
        p90 = sorted(resto)[int(len(resto) * 0.9)] if resto else 0
        ronda = {
            "n": n,
            "eco_base": eco_base,
            "eco_medio": eco_medio,
            "eco_p90": p90,
            "pico": pico,
            "disparo_ms": disparo_ms,
            "umbral": umbrales[-1] if umbrales else 0,
            "eco_ref": det.eco,
            "bloques": len(con_sonido),
            "ciegos": ciegos,
        }
        rondas.append(ronda)
        estado = (f"INTERRUMPIDO a los {disparo_ms:.0f} ms"
                  if disparo_ms is not None else "no se disparo")
        eco_ref = f"{det.eco:.0f}" if det.eco else "--"
        pct_ciego = 100.0 * ciegos / max(1, len(con_sonido))
        aviso = (f" | barge-in APAGADO el {pct_ciego:.0f}% del tiempo"
                 if pct_ciego > 5 else "")
        print(f"   eco medio {eco_medio:>6.0f} | pico {pico:>6.0f} | eco ref "
              f"{eco_ref:>6} | umbral {ronda['umbral']:>6.0f}"
              f" -> {estado}{aviso}", flush=True)

        if n < RONDAS:
            time.sleep(3.0)

    micro.cerrar()
    tts.cerrar()
    supervisor.detener_todo()

    # ---- informe -----------------------------------------------------
    print("\n" + "=" * 70, flush=True)
    print("INFORME DE CALIBRACION", flush=True)
    print("=" * 70, flush=True)
    if not rondas:
        print("No se midio nada.", flush=True)
        return 1

    ecos = [r["eco_medio"] for r in rondas]
    eco = statistics.median(ecos)
    picos = [r["pico"] for r in rondas]
    pico = max(picos)
    disparos = [r for r in rondas if r["disparo_ms"] is not None]

    print(f"  rondas medidas        : {len(rondas)}", flush=True)
    print(f"  eco de los altavoces  : {eco:.0f} RMS (mediana del eco puro)",
          flush=True)
    print(f"  pico mas alto del micro: {pico:.0f} RMS", flush=True)
    print(f"  rondas interrumpidas  : {len(disparos)} de {len(rondas)}",
          flush=True)

    total_bloques = sum(r["bloques"] for r in rondas)
    total_ciegos = sum(r["ciegos"] for r in rondas)
    if total_bloques:
        pct = 100.0 * total_ciegos / total_bloques
        print(f"  barge-in desactivado por eco excesivo: {pct:.0f}% del tiempo",
              flush=True)
        if pct > 5:
            print("    (el eco llega al nivel de tu voz: sin cancelacion de eco",
                  flush=True)
            print("     por hardware no hay umbral que los separe. Baja el",
                  flush=True)
            print("     volumen de los altavoces para recuperar el barge-in.)",
                  flush=True)

    if eco <= 0:
        print("\n  No hay eco medible: estas usando auriculares o el volumen "
              "esta muy bajo.", flush=True)
        print("  Con auriculares el barge-in funciona de sobra con los valores "
              "por defecto.", flush=True)
        return 0

    ratio = pico / eco if eco else 0
    print(f"  relacion voz/eco      : {ratio:.2f}x", flush=True)

    print("", flush=True)
    print("  LECTURA:", flush=True)
    print(f"    el eco puro de tus altavoces llega a {max(picos):.0f} RMS",
          flush=True)
    if eco > 0:
        print(f"    VOZ_BARGE_IN_RMS_MINIMO deberia quedar por encima de eso "
              f"(ahora: 1 200)", flush=True)
    print("    el margen y demas se ajustan con la prueba en silencio:",
          flush=True)
    print("      python -m voz.pruebas.calibrar_barge_in 5 silencio", flush=True)

    print("", flush=True)
    if MODO == "silencio":
        pico_eco = max(picos) if picos else 0
        if pico_eco > 1500:
            print(f"  (el eco llego a {pico_eco:.0f} RMS: el volumen SI "
                  "estaba alto, la prueba vale)", flush=True)
        else:
            print(f"  (ATENCION: el eco solo llego a {pico_eco:.0f} RMS. Si "
                  "querias probar a volumen maximo, sube el volumen y repite.)",
                  flush=True)
        if len(disparos) == 0:
            print("  PERFECTO: 0 falsos positivos en "
                  f"{len(rondas)} rondas. El detector no se dispara con el eco.",
                  flush=True)
        else:
            print(f"  PROBLEMA: {len(disparos)} de {len(rondas)} rondas se "
                  "cortaron SOLAS, sin que hablaras.", flush=True)
            print("  Sube VOZ_BARGE_IN_MARGEN (por ejemplo a 1.8) hasta que "
                  "esto de 0.", flush=True)
    elif len(disparos) == 0:
        print("  No se interrumpio en ninguna ronda. O no hablaste, o el eco",
              flush=True)
        print("  es tan alto que tu voz no lo supera. Prueba a bajar el",
              flush=True)
        print("  volumen de los altavoces (el eco baja y el margen mejora), o",
              flush=True)
        print("  usa auriculares.", flush=True)
    elif ratio < 1.8:
        print("  El eco es alto comparado con tu voz: el barge-in es fragil.",
              flush=True)
        print("  Bajar el volumen de los altavoces es la mejora mas efectiva.",
              flush=True)
    else:
        print(f"  Separacion suficiente: {len(disparos)} de {len(rondas)} "
              "interrupciones detectadas y ninguna con el eco solo.", flush=True)
    print("=" * 70, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
