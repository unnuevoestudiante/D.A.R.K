r"""
parches.py — Compatibilidad de los servidores Wyoming con Windows.

Resuelve dos problemas concretos y verificados de esta plataforma. Ninguno de
los dos es culpa del codigo de Jarvis, pero sin ellos los servidores no
arrancan o no pueden trabajar.

1. Manejadores de senal (servidores Wyoming)
   ------------------------------------
   El servidor Piper independiente registra SIGINT/SIGTERM con
   `loop.add_signal_handler()`. asyncio NO implementa esa funcion en Windows
   (el ProactorEventLoop no tiene `signal.set_wakeup_fd`), asi que el servidor
   carga la voz, escribe "Ready" y muere:

       File "...\wyoming_piper\__main__.py", line 313, in main
           loop.add_signal_handler(signal.SIGINT, server_task.cancel)
       NotImplementedError

   El ciclo de vida lo controla el supervisor de Jarvis, que arranca y termina
   el proceso hijo directamente, asi que esos manejadores no aportan nada: se
   sustituyen por no-ops.

2. Directorios temporales restringidos (wyoming-faster-whisper)
   -----------------------------------------------------------
   `tempfile.mkdtemp()` y `TemporaryDirectory()` crean el directorio con modo
   0o700. Bajo un token restringido (el sandbox de Windows con el que corre
   DSH) el directorio resultante queda inaccesible **incluso para el propio
   proceso que lo creo**, y su ACL ni siquiera se puede leer:

       PermissionError: [Errno 13] Permission denied:
         '...\\_voz_tmp\\tmpgx64byvt\\speech.wav'

   Comprobado con una sonda: `os.makedirs(ruta)` funciona y
   `os.makedirs(ruta, mode=0o700)` no. wyoming-faster-whisper escribe el WAV de
   cada turno con `tempfile.TemporaryDirectory()`, asi que sin esto no puede
   transcribir nada.

   Para no cambiar el comportamiento de Python cuando no hace falta, primero se
   sondea y solo se parchea si la sonda confirma el problema.
"""

import asyncio
import os
import shutil
import sys
import tempfile

from voz.politica_calidad import (
    UMBRALES_WYOMING,
    decidir,
    senales_de_segmento,
)

# ---------------------------------------------------------------------------
#  1. Manejadores de senal
# ---------------------------------------------------------------------------


def parchear_senales_windows():
    """Hace que add_signal_handler/remove_signal_handler no hagan nada."""
    if sys.platform != "win32":
        return False
    if getattr(asyncio.BaseEventLoop, "_voz_parcheado", False):
        return False

    def _add_signal_handler(self, sig, callback, *args):
        return None

    def _remove_signal_handler(self, sig):
        return False

    asyncio.BaseEventLoop.add_signal_handler = _add_signal_handler
    asyncio.BaseEventLoop.remove_signal_handler = _remove_signal_handler
    asyncio.BaseEventLoop._voz_parcheado = True
    return True


# ---------------------------------------------------------------------------
#  2. Directorios temporales
# ---------------------------------------------------------------------------

# Nombre fijo: la sonda es idempotente y deja como mucho un directorio.
_SONDA = "voz_sonda_permisos"


def _sonda_tempfile_restringido():
    """True si un directorio creado con modo 0o700 queda inutilizable.

    Devuelve False en cuanto algo no cuadra (no se pudo crear el directorio,
    se pudo escribir...), para no parchear nada por error.
    """
    try:
        base = tempfile.gettempdir()
    except Exception:
        return False

    ruta = os.path.join(base, _SONDA)
    try:
        if not os.path.isdir(ruta):
            os.makedirs(ruta, mode=0o700, exist_ok=True)
    except OSError:
        # Ni siquiera se pudo crear: es otro problema, no el que arreglamos.
        return False

    try:
        with open(os.path.join(ruta, "sonda.txt"), "wb") as f:
            f.write(b"x")
        return False
    except OSError:
        return True
    finally:
        try:
            shutil.rmtree(ruta)
        except OSError:
            # Directorio bloqueado: es justo el sintoma que buscamos.
            pass


def _mkdtemp_permisivo(suffix=None, prefix=None, dir=None):
    """Como tempfile.mkdtemp, pero sin modo 0o700 (hereda permisos del padre)."""
    if prefix is None:
        prefix = tempfile.gettempprefix()
    if suffix is None:
        suffix = ""
    if dir is None:
        dir = tempfile.gettempdir()

    nombres = tempfile._get_candidate_names()  # noqa: SLF001
    for _ in range(tempfile.TMP_MAX):
        nombre = next(nombres)
        ruta = os.path.join(dir, f"{prefix}{nombre}{suffix}")
        try:
            os.makedirs(ruta)
        except FileExistsError:
            continue
        except OSError:
            break
        else:
            return ruta
    raise FileExistsError(
        f"no se pudo crear un directorio temporal en {dir!r}"
    )


def parchear_tempfile_si_hace_falta():
    """Sustituye mkdtemp si la sonda demuestra que 0o700 lo inutiliza.

    `TemporaryDirectory` llama al `mkdtemp` del modulo, asi que queda cubierto
    con el mismo parche.
    """
    if getattr(tempfile, "_voz_parcheado", False):
        return False
    if not _sonda_tempfile_restringido():
        return False

    tempfile.mkdtemp = _mkdtemp_permisivo
    tempfile._voz_parcheado = True
    return True


# ---------------------------------------------------------------------------
#  3. Afinado estricto de Whisper
# ---------------------------------------------------------------------------

# Valores que ya usaba el nucleo cuando Whisper corria dentro de su proceso.
# Se reproducen en el servidor porque `wyoming-faster-whisper` aplica los
# valores por defecto de faster-whisper, que incluyen el respaldo de
# temperaturas [0.0 .. 1.0]: cuando el primer intento no supera los umbrales,
# reintenta varias veces y multiplica el tiempo. El nucleo habia quitado ese
# respaldo justo por eso.
#
# Son parametros del motor, aplicados por segmento durante la decodificacion.
# Lo que decide si la frase se acepta o se tira es otra cosa y vive en
# `voz/politica_calidad.py` (ahi estan los umbrales de rechazo medios).
WHISPER_TEMPERATURA = 0.0
WHISPER_UMBRAL_LOGPROB = -0.6        # umbral por segmento para faster-whisper
WHISPER_UMBRAL_NO_SPEECH = 0.95      # umbral por segmento para faster-whisper
WHISPER_UMBRAL_COMPRESION = 1.8      # umbral por segmento para faster-whisper


def vigilar_hilos(segundos=20.0):
    """Vuelca las pilas de todos los hilos cada `segundos`.

    Es la herramienta de diagnostico cuando un servidor se queda colgado: en el
    log aparece exactamente en que linea esta parado cada hilo, en vez de tener
    que adivinar. Se activa con VOZ_VOLCAR_HILOS=1.
    """
    try:
        import faulthandler

        faulthandler.enable()
        faulthandler.dump_traceback_later(segundos, repeat=True, exit=False)
        print(f"[voz] volcado de hilos activado cada {segundos:.0f}s", flush=True)
        return True
    except Exception as e:  # pragma: no cover
        print(f"[voz] no pude activar el volcado de hilos: {e}", flush=True)
        return False


def parchear_whisper_estricto(activo=True):
    """Aplica en el servidor la política de rechazo, con sus propios umbrales.

    El protocolo Wyoming solo entrega el texto en el evento `transcript`, asi
    que los numeros de calidad (logprob, no_speech_prob, compression_ratio) no
    pueden filtrarse en el cliente. Se filtran aqui, en el servidor: una
    transcripcion que no los supera se devuelve vacia, que es exactamente lo
    que hacia el nucleo antes (y el cliente lo interpreta como "no entendi").

    El criterio — que señal se mira, en que orden y que pasa si una señal no
    llegó — no está acá: vive en `voz/politica_calidad.py` y es el mismo que usa
    la ruta local en proceso. Lo único propio de este parche son los numeros
    (`UMBRALES_WYOMING`) y que el texto se devuelve sin normalizar.
    """
    if not activo:
        return False
    try:
        from wyoming_faster_whisper.faster_whisper_handler import (
            FasterWhisperTranscriber,
        )
    except Exception:
        return False
    if getattr(FasterWhisperTranscriber, "_voz_estricto", False):
        return False

    def _transcribir(self, wav_path, language, beam_size=5, initial_prompt=None):
        kwargs = {
            "beam_size": beam_size,
            "language": language,
            "initial_prompt": initial_prompt,
            "vad_filter": self.vad_filter,
            "vad_parameters": self.vad_parameters,
            # Afinado del nucleo:
            "condition_on_previous_text": False,
            "temperature": WHISPER_TEMPERATURA,
            "no_speech_threshold": WHISPER_UMBRAL_NO_SPEECH,
            "log_prob_threshold": WHISPER_UMBRAL_LOGPROB,
            "compression_ratio_threshold": WHISPER_UMBRAL_COMPRESION,
        }
        if self.task:
            kwargs["task"] = self.task

        segmentos, _info = self.model.transcribe(str(wav_path), **kwargs)

        partes, senales = [], []
        for seg in segmentos:
            partes.append(seg.text)
            senales.append(senales_de_segmento(seg))

        decision = decidir(partes, senales, UMBRALES_WYOMING)
        if decision.rechazada:
            print(f"[whisper] rechazo: {decision.motivo()}", flush=True)
            return ""
        return decision.texto

    FasterWhisperTranscriber.transcribe = _transcribir
    FasterWhisperTranscriber._voz_estricto = True
    return True


# ---------------------------------------------------------------------------
#  Aplicacion conjunta
# ---------------------------------------------------------------------------


def aplicar_todos(verboso=True):
    """Aplica todos los parches y devuelve la lista de los que hicieron falta."""
    aplicados = []
    if parchear_senales_windows():
        aplicados.append("manejadores de senal")
    if parchear_tempfile_si_hace_falta():
        aplicados.append("directorios temporales")
    if verboso and aplicados:
        print(f"[voz] parches aplicados: {', '.join(aplicados)}", flush=True)
    return aplicados
