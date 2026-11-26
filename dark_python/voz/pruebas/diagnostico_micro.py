"""Encuentra que dispositivo de entrada sirve de verdad, probando todas las APIs.

Un dispositivo sirve si cumple DOS cosas:

  1. capta senal: un micro real siempre tiene ruido de fondo, asi que devolver
     ceros significa que esa ruta no entrega audio;
  2. marca el ritmo: leer 2 s de audio tiene que tardar ~2 s. Hay dispositivos
     virtuales rotos que devuelven los datos al instante, y con ellos el VAD se
     dispara sin sentido.

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.diagnostico_micro
"""
import sys
import time

import numpy as np
import pyaudio

RATE = 16000
CHUNK = 1280
BLOQUES = 25  # 2 s de audio real


def probar(pa, indice, rate, canales=1):
    try:
        stream = pa.open(format=pyaudio.paInt16, channels=canales, rate=rate,
                         input=True, frames_per_buffer=CHUNK,
                         input_device_index=indice)
    except Exception as e:
        return None, f"{e}"[:40]
    niveles = []
    try:
        for _ in range(2):
            stream.read(CHUNK, exception_on_overflow=False)
        t0 = time.perf_counter()
        for _ in range(BLOQUES):
            datos = stream.read(CHUNK, exception_on_overflow=False)
            a = np.frombuffer(datos, dtype=np.int16)
            niveles.append(float(np.sqrt(np.mean(a.astype(np.float32) ** 2)))
                           if a.size else 0.0)
        ritmo = time.perf_counter() - t0
    except Exception as e:
        return None, f"{e}"[:40]
    finally:
        try:
            stream.stop_stream()
            stream.close()
        except Exception:
            pass

    audio = BLOQUES * CHUNK / rate
    return {
        "ritmo": ritmo,
        "factor": audio / ritmo if ritmo else 999.0,
        "pico": max(niveles) if niveles else 0.0,
        "mediana": float(np.median(niveles)) if niveles else 0.0,
    }, None


def main():
    pa = pyaudio.PyAudio()
    usables = []
    try:
        try:
            d = pa.get_default_input_device_info()
            print(f"Dispositivo de entrada POR DEFECTO: [{d['index']}] {d['name']}")
        except Exception:
            print("No hay dispositivo de entrada por defecto.")

        for a in range(pa.get_host_api_count()):
            api = pa.get_host_api_info_by_index(a)
            print(f"\n### API {a}: {api['name']} ({api['deviceCount']} dispositivos)")
            for d in range(api["deviceCount"]):
                try:
                    info = pa.get_device_info_by_host_api_device_index(a, d)
                except Exception:
                    continue
                if info.get("maxInputChannels", 0) < 1:
                    continue
                idx = int(info["index"])
                nombre = (info.get("name", "") or "")[:40]
                nat = int(info.get("defaultSampleRate", 44100))
                for rate in dict.fromkeys([RATE, nat]):
                    r, err = probar(pa, idx, rate)
                    if err:
                        print(f"   [{idx:>3}] {rate:>6}Hz  ERROR          {nombre}")
                        continue
                    usable = r["pico"] >= 4 and 0.5 <= r["factor"] <= 2.0
                    veredicto = "USABLE" if usable else (
                        "sin senal" if r["pico"] < 4 else "no marca ritmo")
                    print(f"   [{idx:>3}] {rate:>6}Hz  {veredicto:<14} "
                          f"pico={r['pico']:>6.0f} factor={r['factor']:>8.2f}  "
                          f"{nombre}")
                    if usable:
                        usables.append((a, api["name"], idx, rate, nombre))
    finally:
        pa.terminate()

    print("\n" + "=" * 84)
    if usables:
        print("COMBINACIONES USABLES (pon el indice en VOZ_MIC_DISPOSITIVO):")
        for a, api, idx, rate, nombre in usables:
            print(f"  API {a} ({api})  dispositivo {idx} @ {rate} Hz -> {nombre}")
    else:
        print("NINGUNA combinacion capta audio utilizable.")
        print("El microfono no esta llegando a las aplicaciones. Revisa, en este")
        print("orden:")
        print("  1. Configuracion > Privacidad y seguridad > Microfono")
        print("     - 'Acceso al microfono' activado")
        print("     - 'Permitir que las aplicaciones de escritorio accedan al")
        print("       microfono' ACTIVADO (es la causa mas comun de silencio)")
        print("  2. Sonido > Grabacion: dispositivo habilitado, volumen sin")
        print("     silenciar, y marcado como predeterminado")
        print("  3. En las propiedades del microfono, pestana Avanzado:")
        print("     desmarca 'Permitir que las aplicaciones tomen el control")
        print("     exclusivo del dispositivo'")
        print("  4. Controlador de audio (Realtek) actualizado o reinstalado")
    print("=" * 84)
    return 0 if usables else 1


if __name__ == "__main__":
    sys.exit(main())
