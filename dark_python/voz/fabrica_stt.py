"""Selección del proveedor STT local en un único punto de composición.

Aquí — y solo aquí — se sabe qué motor hay detrás del puerto `PuertoSTT`. El
Núcleo pide `voz_api.crear_transcriptor_local()` y no nombra implementaciones.

Un motor nuevo se registra en esta función con su import dentro de la rama:
pedir el transcriptor no debe arrastrar ni `faster_whisper` ni `requests`.
"""
import os

_PROVEEDORES = ("faster-whisper", "whisper.cpp", "windows")

# `modelo` y `hilos` significan cosas distintas según el motor. En
# faster-whisper se aplican al construir el modelo, en el turno que sea; en
# whisper.cpp quedan fijados al arrancar el servicio (--model / --threads) y
# este proceso no puede cambiarlos. `--vad-model` y `--no-fallback` también son
# de arranque: sin el primero, pedir VAD por solicitud revienta el HTTP 500.
_AJUSTES_DE_ARRANQUE = {
    "whisper.cpp": ("--model", "--threads", "--vad-model", "--no-fallback"),
}
_ALIAS = {
    "faster-whisper": "faster-whisper",
    "faster_whisper": "faster-whisper",
    "whisper": "faster-whisper",
    "whisper.cpp": "whisper.cpp",
    "windows": "windows",
    "sapi": "windows",
    "whispercpp": "whisper.cpp",
    "whisper-cpp": "whisper.cpp",
}


def crear_transcriptor_local(modelo="small", hilos=4, log=print, motor=None):
    """Transcriptor según `motor` (preferencia de la persona) o `DARK_STT_LOCAL_PROVIDER`; por defecto faster-whisper."""
    pedido = (motor or os.environ.get("DARK_STT_LOCAL_PROVIDER", "faster-whisper")).strip().lower()
    proveedor = _ALIAS.get(pedido)
    if proveedor is None:
        log(f"[voz] Proveedor STT local desconocido ({pedido}); uso "
            f"faster-whisper. Conocidos: {', '.join(_PROVEEDORES)}. "
            "Registre el suyo en voz/fabrica_stt.py.")
        proveedor = "faster-whisper"

    if proveedor == "windows":
        from voz.stt_windows import WindowsTranscriptor

        return WindowsTranscriptor(log=log)

    if proveedor == "whisper.cpp":
        from voz.stt_whispercpp import WhisperCppTranscriptor

        avisos = " / ".join(_AJUSTES_DE_ARRANQUE["whisper.cpp"])
        log(f"[voz] whisper.cpp: `modelo` y `hilos` se fijan al arrancar el "
            f"servidor ({avisos}) y la URL sale de DARK_WHISPERCPP_URL; lo que "
            f"se pidió acá ({modelo!r}, {hilos}) solo sirve de referencia.")
        return WhisperCppTranscriptor(modelo=modelo, hilos=hilos, log=log)

    from voz.stt_whisper_local import WhisperLocal

    return WhisperLocal(modelo=modelo, dispositivo="cpu", tipo_calculo="int8",
                        hilos=hilos, log=log)
