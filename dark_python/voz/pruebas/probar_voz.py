"""Prueba de integracion del subsistema de voz.

Arranca los dos servidores con el supervisor real, mide el TTS y vuelve a
transcribir con el ASR lo que sintetizo Piper (ida y vuelta completa).

Uso (desde dark_python):
    ..\\.venv\\Scripts\\python.exe -m voz.pruebas.probar_voz
"""
import sys
import time

import speech_recognition as sr

from voz import supervisor
from voz.cliente import resamplear, rms
from voz.stt import SttWyoming
from voz.tts import TtsWyoming

fallos = []


def revisar(nombre, condicion, detalle=""):
    print(f"  [{'OK   ' if condicion else 'FALLO'}] {nombre} {detalle}")
    if not condicion:
        fallos.append(nombre)


class ReproductorFalso:
    """Captura el PCM en memoria en vez de sacarlo por los altavoces."""

    reproduciendo = False
    nivel_salida = 0.0
    abierto = True

    def __init__(self):
        self.pcm = bytearray()
        self.rate = None

    def escribir(self, trozo, parar=None, rate=22050, width=2, channels=1):
        if parar is not None and parar.is_set():
            return False
        self.pcm.extend(trozo)
        self.rate = rate
        return True

    def detener(self):
        return None

    def cerrar(self):
        return None


FRASE = "Hola señor, ya está listo el informe que pediste."


def main():
    print("=" * 66)
    print("1) ARRANQUE DE LOS SERVIDORES CON EL SUPERVISOR")
    print("=" * 66)
    t0 = time.time()
    ok = supervisor.arrancar_todo(esperar=True)
    print(f"  arrancar_todo -> {ok} en {time.time() - t0:.1f}s")
    for nombre in ("piper", "whisper"):
        s = supervisor._por_nombre(nombre)
        info = s.info or {}
        print(f"  {nombre}: estado={s.estado} asr={info.get('asr')} "
              f"tts={len(info.get('voces_tts') or [])} voces")
    revisar("los dos servidores responden", ok)

    print("\n" + "=" * 66)
    print("2) TTS (reproductor falso: no suena por los altavoces)")
    print("=" * 66)
    falso = ReproductorFalso()
    tts = TtsWyoming(reproductor=falso, log=print)
    tts.calentar()  # carga la voz; sin esto la primera frase paga ~3 s

    r1 = tts.hablar(FRASE)
    pm = r1.get("primer_ms")
    print(f"  primera sintesis: ok={r1.get('ok')} "
          f"primer_ms={pm if pm is None else round(pm)} "
          f"bytes={r1.get('bytes')} rate={r1.get('rate')}")
    revisar("el TTS sintetiza y entrega audio", r1.get("ok") and r1.get("bytes"))

    r2 = tts.hablar(FRASE)
    revisar("la segunda vez sale de cache", r2.get("cache") is True)

    r3 = tts.hablar("Dame un segundo")
    pm3 = r3.get("primer_ms")
    print(f"  frase corta (filler): primer_ms="
          f"{pm3 if pm3 is None else round(pm3)}")
    revisar("el TTS sintetiza frases cortas", bool(r3.get("ok")))

    print("\n" + "=" * 66)
    print("3) STT: transcribir lo que sintetizo Piper (ida y vuelta)")
    print("=" * 66)
    stt = SttWyoming(log=print)
    # PCM limpio de una sola frase: la cache hace que la sintesis sea inmediata.
    falso.pcm = bytearray()
    tts.hablar(FRASE)
    pcm16 = resamplear(bytes(falso.pcm), falso.rate or 22050, 16000)
    r = stt.transcribir_pcm(pcm16, 16000)
    print(f"  original   : {FRASE!r}")
    print(f"  transcrito : {r.get('texto')!r}  ({r.get('segundos', 0):.2f}s)")
    revisar("el STT responde", r.get("ok"))
    if r.get("texto"):
        a = set(FRASE.lower().replace(",", "").replace(".", "").split())
        b = set(r["texto"].lower().replace(",", "").replace(".", "").split())
        coinciden = len(a & b) / max(1, len(a))
        print(f"  palabras coincidentes: {coinciden * 100:.0f}%")
        revisar("el STT acierta la mayoria", coinciden >= 0.6)

    print("\n" + "=" * 66)
    print("4) CAMINO AudioData (el que usa dark_nucleo.transcribir)")
    print("=" * 66)
    r4 = stt.transcribir_audio_data(sr.AudioData(pcm16, 16000, 2))
    print(f"  transcrito : {r4.get('texto')!r}")
    revisar("AudioData se transcribe", r4.get("ok") and bool(r4.get("texto")))

    print("\n" + "=" * 66)
    print("5) SALIDA DE AUDIO REAL (250 ms de silencio, sin ruido)")
    print("=" * 66)
    from voz.reproductor import ReproductorPCM

    rep = ReproductorPCM(rate=22050)
    ok_rep = rep.escribir(b"\x00" * (22050 * 2 // 4), rate=22050)
    rep.detener()
    rep.cerrar()
    print(f"  escribir -> {ok_rep}")
    revisar("el dispositivo de salida acepta PCM", ok_rep)

    print("\n" + "=" * 66)
    print("6) MICROFONO")
    print("=" * 66)
    from voz.micro import Micro

    micro = Micro()
    if micro.abrir():
        bloque = micro.leer()
        print(f"  dispositivo [{micro.dispositivo}] "
              f"{micro.dispositivo_nombre}: {len(bloque or b'')} bytes, "
              f"nivel={rms(bloque) if bloque else -1:.0f}")
        revisar("el microfono entrega bloques", bloque is not None)
        micro.cerrar()
    else:
        revisar("hay un microfono utilizable", False,
                "(ver voz.pruebas.diagnostico_micro)")

    print("\n" + "=" * 66)
    print("7) PARADA DE LOS SERVIDORES")
    print("=" * 66)
    supervisor.detener_todo()
    time.sleep(1.0)
    revisar("piper parado", not supervisor.piper.en_ejecucion())
    revisar("whisper parado", not supervisor.whisper.en_ejecucion())

    print("\n" + "=" * 66)
    if fallos:
        print(f"RESULTADO: FALLO ({len(fallos)}): {fallos}")
    else:
        print("RESULTADO: OK - el subsistema de voz funciona")
    print("=" * 66)
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
