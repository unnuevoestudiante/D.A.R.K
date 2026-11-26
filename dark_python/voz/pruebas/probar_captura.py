"""Prueba el VAD, la formacion de turnos y el barge-in SIN microfono.

Genera senales sinteticas (silencio con ruido de fondo + "voz" modulada) y las
pasa bloque a bloque por el Capturador, igual que hara el bucle real.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.probar_captura
"""
import random
import sys

import numpy as np

from voz.micro import Capturador, DetectorBargeIn

RATE = 16000
CHUNK = 1280  # 80 ms
DUR_BLOQUE = CHUNK / RATE


def ruido(segundos, amplitud=45):
    n = int(segundos * RATE)
    return np.random.default_rng(1).integers(
        -amplitud, amplitud, n, dtype=np.int16).tobytes()


def voz(segundos, amplitud=8000, semilla=7):
    """Senal parecida a voz: ruido modulado por una envolvente lenta."""
    n = int(segundos * RATE)
    rng = np.random.default_rng(semilla)
    base = rng.normal(0, 1, n)
    t = np.arange(n) / RATE
    envolvente = 0.35 + 0.65 * np.abs(np.sin(2 * np.pi * 3.1 * t))
    return (np.clip(base * envolvente, -3, 3) * (amplitud / 3.0)).astype(
        np.int16).tobytes()


def bloques(pcm):
    paso = CHUNK * 2
    for i in range(0, len(pcm) - paso + 1, paso):
        yield pcm[i:i + paso]


def prueba_turnos(etiqueta, senal, esperados):
    cap = Capturador(rate=RATE, chunk=CHUNK)
    inicios, turnos = [], []
    t = 0.0
    for b in bloques(senal):
        r = cap.procesar(b)
        t += DUR_BLOQUE
        if r == "inicio_voz":
            inicios.append(t)
        elif r is not None:
            turnos.append((t, r.duracion))

    print(f"\n--- {etiqueta}")
    print(f"    inicios de voz: {[f'{x:.2f}s' for x in inicios]}")
    print(f"    turnos: {[(f'{x[0]:.2f}s', f'{x[1]:.2f}s') for x in turnos]}")
    ok = len(turnos) == esperados
    print(f"    esperados {esperados} -> {'OK' if ok else 'FALLO'}")
    return ok


def _bloques_eco(pares, k_real=0.10, fluctuacion=0.4, semilla=3):
    """Genera (nivel_micro, nivel_salida) como los ve el detector.

    `pares`: (salida, factor_usuario). El eco se modela como la respuesta de la
    sala al sonido que YA salio (por eso se suaviza la salida igual que hace
    `ReproductorPCM`), con una fluctuacion por bloque: el eco tambien es habla y
    sus picos son bastante mas altos que su valor tipico. Sin esa fluctuacion la
    prueba no diria nada sobre el percentil.
    """
    rng = random.Random(semilla)
    salida_suave = 0.0
    bloques = []
    for salida, factor in pares:
        salida_suave = 0.7 * salida_suave + 0.3 * salida
        k = k_real * (1 + fluctuacion * (rng.random() * 2 - 1))
        bloques.append((k * salida_suave * factor, salida_suave))
    return bloques


def _simular_bargein(etiqueta, bloques_sim, esperado):
    """`bloques_sim`: lista de (nivel_micro, nivel_salida)."""
    det = DetectorBargeIn()
    detectado = False
    for nivel, salida in bloques_sim:
        if det.observar(nivel, reproduciendo=True, nivel_salida=salida):
            detectado = True
            break
    ok = detectado == esperado
    eco = f"{det.eco:.0f}" if det.eco else "--"
    print(f"  {etiqueta:40s} -> {detectado!s:5s} "
          f"(eco ref {eco:>5}, umbral {det.ultimo_umbral:>5.0f}) "
          f"{'OK' if ok else 'FALLO'}")
    return ok


def prueba_bargein():
    """Eco fluctuante con acoplamiento medio 0,10, como el medido aqui."""
    print("\n" + "=" * 64)
    print("DetectorBargeIn (umbral sobre el nivel de eco medido)")
    print("=" * 64)
    print("  el eco se mide del NIVEL DEL MICRO; acoplamiento medio 0,10")
    print(f"  umbral = percentil {DetectorBargeIn().percentil:.0%} del eco "
          f"x {DetectorBargeIn().margen}")

    # Salida alternando segmentos fuertes y flojos, como cualquier habla.
    salidas = [12000, 4000] * 60

    casos = [
        ("solo eco, salida fuerte y floja",
         _bloques_eco([(s, 1.0) for s in salidas]), False),
        ("eco + usuario a 3x el eco",
         _bloques_eco([(s, 1.0) for s in salidas[:40]]
                      + [(s, 3.0) for s in salidas[40:52]]), True),
        ("eco + usuario a 1,2x (por debajo del umbral)",
         _bloques_eco([(s, 1.0) for s in salidas[:40]]
                      + [(s, 1.2) for s in salidas[40:52]]), False),
        ("eco con pico aislado (1 bloque, 6x)",
         _bloques_eco([(s, 1.0) for s in salidas[:40]]
                      + [(salidas[40], 6.0)]), False),
        ("interrupcion fuerte sostenida (2 bloques, 4x)",
         _bloques_eco([(s, 1.0) for s in salidas[:40]]
                      + [(salidas[40], 4.0), (salidas[40], 4.0)]), True),
        ("auriculares: eco casi nulo, voz a 1500",
         [(150, 100)] * 40 + [(1500, 100)] * 6, True),
        ("silencio digital del TTS y el usuario habla",
         _bloques_eco([(s, 1.0) for s in salidas[:40]]) + [(2000, 0.0)] * 6,
         True),
    ]
    return all(_simular_bargein(*c) for c in casos)


def main():
    print("=" * 64)
    print("Capturador: formacion de turnos")
    print("=" * 64)
    ok1 = prueba_turnos("1 frase", ruido(1.0) + voz(2.0) + ruido(1.5), 1)
    ok2 = prueba_turnos("2 frases separadas",
                        ruido(1.0) + voz(1.5) + ruido(1.6) + voz(1.5) + ruido(1.5),
                        2)
    ok3 = prueba_turnos("ruido corto (no debe contar)",
                        ruido(1.0) + np.zeros(int(0.2 * RATE),
                                              dtype=np.int16).tobytes() + ruido(1.5),
                        0)
    ok4 = prueba_bargein()

    print("\n" + "=" * 64)
    todo = all([ok1, ok2, ok3, ok4])
    print("RESULTADO:", "OK" if todo else "FALLO")
    print("=" * 64)
    return 0 if todo else 1


if __name__ == "__main__":
    sys.exit(main())
