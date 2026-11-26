r"""Prueba real del lado Whisper: faster-whisper contra whisper.cpp, por el puerto.

No va de cuál transcribe mejor —eso lo decide el oído del señor—, sino de cuánto
tarda cada motor en el tramo de ASR de un turno y cuánta RAM deja residente en
la caja de 16 GB. Es el equivalente de `probar_llamacpp_real.py` del lado del
chat.

El audio no se graba del micro: se sintetiza con la misma voz Piper que usa el
TTS de Dark y se remuestrea a 16 kHz mono, que es lo que el Núcleo le manda al
transcriptor. Así las dos rutas oyen exactamente el mismo WAV, en el mismo
orden, y el número es comparable entre motores (y sesgado por igual).

Uso:
    # 1) arrancar el servidor con el modelo que se quiere medir.
    #    El puerto tiene que ser el 9080: es el que trae el adaptador, porque el
    #    8080 de whisper.cpp por defecto ya lo usa el llama-server.
    whisper-server.exe -m ggml-small.bin -t 4 --port 9080

    # 2) correr la prueba (por defecto mide los dos motores)
    python -m voz.pruebas.probar_whispercpp_real
    python -m voz.pruebas.probar_whispercpp_real --saltar=local
    python -m voz.pruebas.probar_whispercpp_real --url=http://127.0.0.1:9080
"""
import io
import os
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:  # la consola de Windows no puede imprimir ni la ñ ni el acento
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import psutil  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import resample_poly  # noqa: E402

from voz.fabrica_stt import crear_transcriptor_local  # noqa: E402

FRASES = (
    "Hola señor, enciende la luz del estudio.",
    "¿Qué tiempo hace mañana en la ciudad?",
    "Apaga la música y baja el volumen a veinte.",
    "Recuérdame revisar el informe el viernes.",
    "Dark, ¿en qué tareas estás ahora mismo?",
)

VOZ_TTS = "piper_voices/es_ES-davefx-medium.onnx"
HILOS = int(os.environ.get("VOZ_WHISPER_CPU_THREADS", "4"))
MODELO_LOCAL = os.environ.get("VOZ_WHISPER_MODEL", "small")
URL_SERVIDOR = os.environ.get("DARK_WHISPERCPP_URL", "http://127.0.0.1:9080")


def _wav(muestras_int16, tasa):
    salida = io.BytesIO()
    with wave.open(salida, "wb") as archivo:
        archivo.setnchannels(1)
        archivo.setsampwidth(2)
        archivo.setframerate(tasa)
        archivo.writeframes(muestras_int16)
    return salida.getvalue()


def _fixtures():
    """Los mismos WAV (16 kHz mono) para los dos motores, sintetizados aquí."""
    raiz = Path(__file__).resolve().parents[2].parent
    ruta_voz = raiz / VOZ_TTS
    if not ruta_voz.exists():
        raise SystemExit(f"no encuentro la voz de Piper en {ruta_voz}")

    from piper.voice import PiperVoice

    voz = PiperVoice.load(str(ruta_voz))
    audios, duraciones = [], []
    for frase in FRASES:
        int16 = b"".join(chunk.audio_int16_bytes for chunk in voz.synthesize(frase))
        tasa = voz.config.sample_rate
        datos = sf.read(io.BytesIO(_wav(int16, tasa)), dtype="float32")[0]
        fino = resample_poly(datos, 16000, tasa).astype("float32")
        audios.append((frase, _wav((fino * 32767).astype("<i2").tobytes(), 16000)))
        duraciones.append(len(fino) / 16000)
    return audios, sum(duraciones)


def _rss_actual():
    return psutil.Process().memory_info().rss / 1e6


def _rss_servidor():
    """RSS de cada `whisper-server` vivo, en MB."""
    salidas = []
    for proceso in psutil.process_iter(["name", "memory_info"]):
        nombre = (proceso.info["name"] or "").lower()
        if nombre.startswith("whisper-server"):
            salidas.append(proceso.info["memory_info"].rss / 1e6)
    return salidas


def _correr(nombre, aparato, audios, extra=""):
    print(f"\n=== {nombre} {extra}")
    tiempos, textos = [], []
    for frase, wav in audios:
        t0 = time.perf_counter()
        resultado = aparato.transcribir_wav(wav)
        dt = time.perf_counter() - t0
        tiempos.append(dt)
        texto = (resultado.get("texto") or "").strip()
        textos.append(texto)
        estado = "ok" if resultado.get("ok") else f"ERROR {resultado.get('error')}"
        print(f"  {dt:5.2f}s  {estado:<20} «{texto}»")
        print(f"        esperado: {frase}")
    total = sum(tiempos)
    print(f"  total {total:.2f}s · media {total / len(tiempos):.2f}s/turno")
    return textos, total


def _abanderados(argv, nombre):
    """Valores de `--nombre=valor`; `--nombre` a secas cuenta como `True`."""
    prefijo = f"--{nombre}"
    salida = []
    for a in argv:
        if a.startswith(prefijo + "="):
            salida.append(a.split("=", 1)[1])
        elif a == prefijo:
            salida.append("True")
    return salida


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    saltar = set(_abanderados(argv, "saltar"))
    banderas = _abanderados(argv, "url")
    url = banderas[0] if banderas else URL_SERVIDOR

    audios, segundos_audio = _fixtures()
    print(f"audio de prueba: {len(audios)} turnos, {segundos_audio:.1f}s en total"
          f" (hilos={HILOS})")

    lineas = {}
    if "local" not in saltar:
        antes = _rss_actual()
        os.environ["DARK_STT_LOCAL_PROVIDER"] = "faster-whisper"
        aparato = crear_transcriptor_local(modelo=MODELO_LOCAL, hilos=HILOS,
                                           log=lambda *a: None)
        t_carga = time.perf_counter()
        aparato.asegurar()
        t_carga = time.perf_counter() - t_carga
        despues = _rss_actual()
        textos, total = _correr(f"faster-whisper ({MODELO_LOCAL}, int8)",
                                aparato, audios,
                                extra=f"[carga {t_carga:.2f}s +{despues - antes:.0f} MB, "
                                      f"proceso {despues:.0f} MB]")
        lineas["local"] = (textos, total, despues - antes)
        aparato.liberar()

    if "servidor" not in saltar:
        vivos = _rss_servidor()
        if not vivos:
            print(f"\n(no hay whisper-server en {url}; arráncalo con -m/--port)")
        else:
            os.environ["DARK_STT_LOCAL_PROVIDER"] = "whisper.cpp"
            os.environ["DARK_WHISPERCPP_URL"] = url
            aparato = crear_transcriptor_local(modelo=MODELO_LOCAL, hilos=HILOS,
                                               log=lambda *a: None)
            aparato.asegurar()
            textos, total = _correr("whisper.cpp (server)", aparato, audios,
                                    extra=f"[RSS servidor {max(vivos):.0f} MB]")
            lineas["servidor"] = (textos, total, max(vivos))

    if len(lineas) == 2:
        (_, s_local, _), (_, s_cpp, _) = lineas["local"], lineas["servidor"]
        t_local, t_cpp = lineas["local"][0], lineas["servidor"][0]
        distintos = [i for i, (a, b) in enumerate(zip(t_local, t_cpp)) if a != b]
        print("\n=== comparación")
        print(f"  segundos de audio reales: {segundos_audio:.1f}")
        print(f"  RTF faster-whisper: {s_local / segundos_audio:.2f} "
              f"({s_local:.2f}s de cómputo)")
        print(f"  RTF whisper.cpp   : {s_cpp / segundos_audio:.2f} "
              f"({s_cpp:.2f}s de cómputo)")
        if s_local:
            print(f"  velocidad relativa: whisper.cpp tarda "
                  f"{s_cpp / s_local:.2f}x lo que faster-whisper")
        print(f"  textos idénticos en {len(t_local) - len(distintos)}/{len(t_local)} "
              f"turnos; distintos en {distintos}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
