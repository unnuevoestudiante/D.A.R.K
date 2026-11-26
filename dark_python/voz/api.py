"""api.py — Fachada ÚNICA del subsistema de voz.

Hasta hoy el núcleo importaba 7 símbolos internos repartidos en 6 líneas y un
`try/except` alrededor (la evidencia del audit del 24-oct-2026 era
nucleo/dark_nucleo.py:100-105 y :112). Desde la rama R0 de la normalización, el
consumidor depende de UNA sola línea:

    from voz import api as voz_api

y de paso deja de conocer la estructura interna del paquete: mañana los
servidores Wyoming pueden cambiar por otro transporte y el único archivo que se
toca es este. Los nombres que usaba el núcleo se traducen así:

    voz_supervisor.whisper.estado  ->  voz_api.supervisor.whisper.estado
    voz_config.X                   ->  voz_api.config.X
    voz_rms(pcm)                   ->  voz_api.rms(pcm)
    Capturador(...) / Micro(...)   ->  voz_api.micro.Capturador(...) / .Micro(...)
    SttWyoming(...)                ->  voz_api.stt.SttWyoming(...)
    TtsWyoming(respaldo=...)       ->  voz_api.crear_tts(respaldo=...)   (fábrica)
    crear_transcriptor_local(...)  ->  voz_api.crear_transcriptor_local(...)
    try/except de importaciones     ->  voz_api.disponibilidad()

Pereza deliberada: solo `config` se importa a nivel de módulo (es stdlib
pura). `micro` arrastra pyaudio, y `cliente`/`stt`/`tts`/`supervisor`
arrastran wyoming: se cargan al primer uso, no al importar. Así, un entorno sin
wyoming o sin pyaudio importa `voz.api` sin error. La única que carga de verdad
es `disponibilidad()`, y el núcleo la llama una vez al importar — el mismo
momento en el que antes ocurrían las 7 importaciones.
"""
import importlib  # stdlib: lo usan la sonda y los proxies

from . import config  # stdlib puro: seguro a nivel de módulo

__all__ = ["config", "supervisor", "cliente", "micro", "stt", "tts",
           "fabrica_stt", "fabrica_tts", "rms",
           "crear_transcriptor_local", "crear_tts", "crear_tts_por_cadena", "ruta_modelo_whisper", "crear_piper_local",
           "disponibilidad"]

# Submódulos que el camino de voz de Wyoming necesita de verdad: si falta
# cualquiera, el consumidor debe quedarse en su ruta antigua.
_NECESARIOS = ("cliente", "micro", "stt", "tts", "supervisor")


class _ModuloPerezoso:
    """Proxy de submódulo: importa `voz.<nombre>` al primer atributo usado.

    Expone el MÓDULO completo (clases, funciones y singletons incluidos),
    de modo que `voz_api.micro.Capturador` sigue siendo una clase real
    (se puede heredar e instanciar igual que antes).
    """

    def __init__(self, nombre):
        self._nombre = nombre
        self._mod = None

    def _cargar(self):
        if self._mod is None:
            self._mod = importlib.import_module(f"voz.{self._nombre}")
        return self._mod

    def __getattr__(self, atributo):
        return getattr(self._cargar(), atributo)


# Submódulos perezosos (cada uno paga su dependencia al primer uso):
supervisor = _ModuloPerezoso("supervisor")   # arranca/vigila wyoming-piper y wyoming-faster-whisper
cliente = _ModuloPerezoso("cliente")         # cliente Wyoming (y rms)
micro = _ModuloPerezoso("micro")             # Capturador, Micro, DetectorBargeIn (pyaudio)
stt = _ModuloPerezoso("stt")                 # SttWyoming
tts = _ModuloPerezoso("tts")                 # TtsWyoming
fabrica_stt = _ModuloPerezoso("fabrica_stt") # selección de STT local (DARK_STT_LOCAL_PROVIDER)
fabrica_tts = _ModuloPerezoso("fabrica_tts") # selección de TTS (DARK_TTS_PROVIDER)


def rms(pcm):
    """Nivel RMS de un bloque PCM int16 (atajo directo a voz.cliente.rms).

    Requiere el stack Wyoming instalado (voz.cliente lo importa a nivel de
    módulo). El núcleo solo lo usa dentro de su rama VOZ_DISPONIBLE, así
    que el requisito es el mismo que tenía antes de esta fachada.
    """
    return cliente.rms(pcm)


def crear_piper_local(python=None):
    """Motor de voces locales de Piper en proceso aparte (voz/piper_local.py); no importa Piper."""
    from .piper_local import PiperLocal

    return PiperLocal(python=python)


def ruta_modelo_whisper(id_):
    """Carpeta del modelo Whisper `id_` que la persona descargó desde Voz de entrada."""
    from . import modelos_whisper

    return modelos_whisper.ruta_de(id_)


def crear_transcriptor_local(modelo="small", hilos=4, log=print, motor=None):
    """PuertoSTT según DARK_STT_LOCAL_PROVIDER (delega en fabrica_stt)."""
    return fabrica_stt.crear_transcriptor_local(
        modelo=modelo, hilos=hilos, log=log, motor=motor)


def crear_tts(respaldo=None, log=print):
    """PuertoTTS según DARK_TTS_PROVIDER (delega en fabrica_tts).

    `respaldo`: callable (texto, parar) -> bool para la ruta de emergencia
    (misma convención que el núcleo usa hoy al construir TtsWyoming).
    """
    return fabrica_tts.crear_tts(respaldo=respaldo, log=log)


def crear_tts_por_cadena(base, preferencias, clave_de, sesion, log=print, piper_local=None):
    """TTS que habla con la voz elegida en el Centro y cae a `base` (voz/tts_cadena.py).

    Importa perezoso, igual que el resto de la fachada: pedirlo no arrastra `requests`.
    """
    from .tts_cadena import TtsPorCadena

    return TtsPorCadena(base, preferencias, clave_de, sesion, log=log, piper_local=piper_local)


def disponibilidad():
    """(True, "") si el camino de voz funciona, o (False, motivo).

    Es la prueba que antes hacía el `try/except` del núcleo alrededor de sus
    siete importaciones: aquí se cargan de verdad los submódulos con sus
    dependencias (wyoming, pyaudio), así que se llama una vez al arrancar y
    nunca dentro de un bucle. El llamador guarda el booleano; el motivo se
    imprime para no perder el diagnóstico que antes daba la excepción.
    """
    for nombre in _NECESARIOS:
        try:
            importlib.import_module(f"voz.{nombre}")
        except Exception as error:  # ImportError, OSError de pyaudio, lo que sea
            return False, f"voz.{nombre}: {error}"
    return True, ""
