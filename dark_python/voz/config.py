"""
config.py — Toda la configuracion del subsistema de voz Wyoming en un sitio.

Cualquier valor puede sobreescribirse con una variable de entorno con el prefijo
VOZ_, por ejemplo:

    set VOZ_PIPER_VOICE=es_ES-davefx-medium
    set VOZ_BARGE_IN=0
"""

import os
from config_runtime import get_runtime_value, resolve_runtime_path


def _env(nombre, por_defecto):
    """Lee VOZ_<nombre> del entorno, con el tipo del valor por defecto."""
    valor = os.environ.get(f"VOZ_{nombre}")
    if valor is None or valor == "":
        return por_defecto
    if isinstance(por_defecto, bool):
        return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")
    if isinstance(por_defecto, int):
        try:
            return int(valor)
        except ValueError:
            return por_defecto
    if isinstance(por_defecto, float):
        try:
            return float(valor)
        except ValueError:
            return por_defecto
    return valor


# ---------------------------------------------------------------------------
#  Rutas
# ---------------------------------------------------------------------------

VOZ_DIR = os.path.dirname(os.path.abspath(__file__))
DARK_PYTHON_DIR = os.path.dirname(VOZ_DIR)
PROJECT_ROOT = os.path.dirname(DARK_PYTHON_DIR)

PYTHON_EXE = _env(
    "PYTHON", os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
)

# Logs de los dos servidores (utiles cuando algo no arranca).
LOG_DIR = _env("LOG_DIR", str(resolve_runtime_path("logs")))

# ---------------------------------------------------------------------------
#  Puertos
#  No chocan con lo que ya usa el sistema:
#    8080 overlay | 8765 websocket | 8766 modulos | 5050/5051 managers | 11434 ollama
# ---------------------------------------------------------------------------

PIPER_HOST = _env("PIPER_HOST", get_runtime_value("services.piper.host"))
PIPER_PORT = _env("PIPER_PORT", get_runtime_value("services.piper.port"))
WHISPER_HOST = _env("WHISPER_HOST", get_runtime_value("services.whisper.host"))
WHISPER_PORT = _env("WHISPER_PORT", get_runtime_value("services.whisper.port"))

PIPER_URI = _env("PIPER_URI", f"tcp://{PIPER_HOST}:{PIPER_PORT}")
WHISPER_URI = _env("WHISPER_URI", f"tcp://{WHISPER_HOST}:{WHISPER_PORT}")

# ---------------------------------------------------------------------------
#  TTS (Piper)
# ---------------------------------------------------------------------------

# Voz instalada en piper_voices/. Alternativas locales:
#   es_MX-claude-high, es_AR-daniela-high, es_ES-davefx-medium, es_ES-sharvard-medium
PIPER_VOICE = _env("PIPER_VOICE", get_runtime_value("services.piper.voice"))
PIPER_VOICES_DIR = _env(
    "PIPER_VOICES_DIR", str(resolve_runtime_path("models"))
)
PIPER_PLUGIN_DIR = _env(
    "PIPER_PLUGIN_DIR", os.path.join(PROJECT_ROOT, "plugins", "piper")
)
PIPER_PYTHON_EXE = _env(
    "PIPER_PYTHON_EXE", os.path.join(PIPER_PLUGIN_DIR, "python", "python.exe")
)
PIPER_WORKER = _env(
    "PIPER_WORKER", os.path.join(PIPER_PLUGIN_DIR, "piper_worker.py")
)
PIPER_TEMP_DIR = _env(
    "PIPER_TEMP_DIR", os.path.join(str(resolve_runtime_path("temporary")), "piper")
)


def piper_disponible():
    """True solo si está instalada la extensión separada y existe la voz."""
    modelo = os.path.join(PIPER_VOICES_DIR, f"{PIPER_VOICE}.onnx")
    configuracion = modelo + ".json"
    modulo = os.path.join(
        PIPER_PLUGIN_DIR, "python", "Lib", "site-packages",
        "wyoming_piper", "__main__.py",
    )
    return all(os.path.isfile(path) for path in (
        PIPER_PYTHON_EXE, PIPER_WORKER, modulo, modelo, configuracion,
    ))

# Tamano de los trozos PCM que envia Piper. Mas pequeno = primer sonido antes,
# pero mas llamadas al socket.
PIPER_SAMPLES_PER_CHUNK = _env("PIPER_SAMPLES_PER_CHUNK", 1024)

# Silencio que Piper inserta entre frases.
PIPER_SENTENCE_SILENCE = _env("PIPER_SENTENCE_SILENCE", 0.0)

# ---------------------------------------------------------------------------
#  Reparto de CPU entre el LLM (Ollama) y la voz (Whisper + Piper)
# ---------------------------------------------------------------------------
#
# Sin CPU dedicada, Ollama (que satura todos los hilos que le des) compite con
# Whisper y Piper: el ASR pasaba de 2,2 s a 6-8 s y el primer audio del TTS de
# 0,2 s a 1-4 s mientras el LLM generaba.
#
# Reparto: la voz se queda con los 2 ultimos NUCLEOS FISICOS y el LLM con el
# resto, con UN hilo por nucleo fisico (los hilos SMT hermanos no suman
# rendimiento en inferencia: la CPU esta limitada por ancho de banda de
# memoria). En Windows los logicos 2k y 2k+1 son hermanos del mismo nucleo.
#
# VOZ_CPU_REPARTO=0 lo desactiva. VOZ_CPU_VOZ="12,13,14,15" y
# VOZ_CPU_LLM="0-11" lo fijan a mano.


def _parsear_cpus(texto):
    cpus = []
    for trozo in str(texto).split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        if "-" in trozo:
            a, b = trozo.split("-", 1)
            cpus.extend(range(int(a), int(b) + 1))
        else:
            cpus.append(int(trozo))
    return sorted(set(cpus))


def _repartir_cpus():
    """(cpus_llm, hilos_llm, cpus_voz) o None si no hay que repartir."""
    if not _env("CPU_REPARTO", False):
        return None
    try:
        manual_voz = os.environ.get("VOZ_CPU_VOZ", "").strip()
        manual_llm = os.environ.get("VOZ_CPU_LLM", "").strip()
        if manual_voz and manual_llm:
            llm, voz = _parsear_cpus(manual_llm), _parsear_cpus(manual_voz)
            return llm, max(1, len(llm) // 2), voz

        import psutil

        fisicos = psutil.cpu_count(logical=False) or 0
        logicos = psutil.cpu_count(logical=True) or 0
        if fisicos < 3 or logicos < fisicos:
            return None
        por_nucleo = max(1, logicos // fisicos)
        reservar = 2 if fisicos >= 6 else 1
        nucleos_llm = fisicos - reservar
        corte = nucleos_llm * por_nucleo
        return (list(range(0, corte)), nucleos_llm,
                list(range(corte, logicos)))
    except Exception:
        return None


REPARTO_CPU = _repartir_cpus()
CPUS_LLM = REPARTO_CPU[0] if REPARTO_CPU else None
HILOS_LLM = REPARTO_CPU[1] if REPARTO_CPU else None
CPUS_VOZ = REPARTO_CPU[2] if REPARTO_CPU else None
_HILOS_WHISPER_DEF = min(4, len(CPUS_VOZ)) if CPUS_VOZ else 4

# ---------------------------------------------------------------------------
#  ASR (faster-whisper)
# ---------------------------------------------------------------------------

WHISPER_MODEL = _env("WHISPER_MODEL", get_runtime_value("services.whisper.model"))
WHISPER_LANGUAGE = _env("WHISPER_LANGUAGE", "es")
WHISPER_DEVICE = _env("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = _env("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_CPU_THREADS = _env("WHISPER_CPU_THREADS", _HILOS_WHISPER_DEF)
WHISPER_BEAM_SIZE = _env("WHISPER_BEAM_SIZE", 3)

# Endpointing en el servidor: si es > 0, el servidor manda la transcripcion en
# cuanto Silero detecta ese silencio, sin esperar a nuestro audio-stop.
#
# Por defecto va DESACTIVADO (0) a proposito: el nucleo ya hace su propio
# endpointing con `voz.micro.Capturador` y manda la frase completa de una vez.
# Con endpointing activo, una pausa normal a mitad de frase (0,6 s) haria que
# el servidor diera el turno por terminado e ignorara el resto del audio.
WHISPER_VAD_ENDPOINTING = _env("WHISPER_VAD_ENDPOINTING", 0.0)
WHISPER_VAD_FILTER = _env("WHISPER_VAD_FILTER", True)

# Reponer en el servidor el afinado que el nucleo tenia con Whisper en proceso
# (temperatura fija, sin condicionar por texto previo y con los umbrales de
# calidad ya ajustados). Ver `voz/parches.py`.
WHISPER_AFINADO_ESTRICTO = _env("WHISPER_AFINADO_ESTRICTO", True)

# Cache de HuggingFace donde ya vive Systran/faster-whisper-small.
HF_CACHE_DIR = _env(
    "HF_CACHE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
)
# Directorios donde el servidor busca el modelo. El primero es donde descarga.
WHISPER_DATA_DIRS = [HF_CACHE_DIR]
WHISPER_DOWNLOAD_DIR = _env("WHISPER_DOWNLOAD_DIR", HF_CACHE_DIR)

# Nunca descargar: si el modelo no esta, el servidor falla en vez de bajar nada.
WHISPER_LOCAL_FILES_ONLY = _env("WHISPER_LOCAL_FILES_ONLY", True)

# Sesgo inicial de Whisper. El nucleo le pasa aqui su WHISPER_PROMPT antes de
# arrancar el servidor, para no perder el sesgo lexico que ya tenia.
WHISPER_INITIAL_PROMPT = _env("WHISPER_INITIAL_PROMPT", "")

# ---------------------------------------------------------------------------
#  Audio
# ---------------------------------------------------------------------------

AUDIO_RATE = _env("AUDIO_RATE", 16000)
AUDIO_WIDTH = _env("AUDIO_WIDTH", 2)
AUDIO_CHANNELS = _env("AUDIO_CHANNELS", 1)

# Tamaño del bloque de captura (160 ms a 16 kHz para reducir polling de CPU).
CHUNK_MUESTRAS = _env("CHUNK_MUESTRAS", 2560)

# ---------------------------------------------------------------------------
#  Microfono de conversacion
# ---------------------------------------------------------------------------

# Usar el microfono persistente (un solo stream siempre abierto) en lugar de
# cerrar y reabrir el dispositivo por cada turno. Ponerlo a 0 vuelve al
# comportamiento anterior sin tocar codigo.
MIC_PERSISTENTE = _env("MIC_PERSISTENTE", True)

# Cual dispositivo de entrada usar.
#   None  -> automatico: se prueba el de por defecto y, si no capta nada, se
#            busca otro que si (ver Micro._candidatos).
#   int   -> indice de PyAudio (tambien vale el texto "5").
#   texto -> trozo del nombre, sin distinguir mayusculas ("Realtek", "USB").
#
# En este equipo el dispositivo POR DEFECTO de Windows no capta nada (devuelve
# ceros en cualquier formato) mientras que "Varios microfonos (Realtek(R)
# Audio)" funciona, asi que la autodeteccion no es un lujo.
MIC_DISPOSITIVO = _env("MIC_DISPOSITIVO", None)

# Probar el dispositivo por defecto y, si entrega silencio, buscar otro.
MIC_AUTO = _env("MIC_AUTO", True)

# Sordera del micro despues de que Dark termine de hablar. El camino antiguo
# necesitaba 2,5 s porque cerraba y reabria el dispositivo; con el stream
# persistente y el buffer drenado basta un margen corto.
MIC_GUARDA_POST_TTS = _env("MIC_GUARDA_POST_TTS", 0.4)

# ---------------------------------------------------------------------------
#  Deteccion de voz en el cliente (VAD) y barge-in
# ---------------------------------------------------------------------------

# RMS minimo para considerar que hay voz cuando el TTS esta callado.
VAD_RMS_MINIMO = _env("VAD_RMS_MINIMO", 320)

# Bloque de voz sostenida antes de aceptar que empieza un turno.
VAD_BLOQUES_INICIO = _env("VAD_BLOQUES_INICIO", 3)

# Silencio (segundos) que cierra la captura si el servidor no hizo endpointing.
VAD_SILENCIO_CIERRE = _env("VAD_SILENCIO_CIERRE", 0.9)

# Silencio (segundos) para retroceder al inicio real de la voz al reservar audio.
VAD_PRE_ROLL = _env("VAD_PRE_ROLL", 0.4)

# Interrumpir a Dark hablando. Con altavoces (sin auriculares) es heuristico:
# se exige que el micro supere el eco medido del propio TTS durante varios
# bloques seguidos. Con auriculares funciona de forma fiable.
BARGE_IN = _env("BARGE_IN", True)

# Margen sobre el eco ESPERADO para aceptar barge-in.
#
# El eco no se adivina: se calcula a partir de lo que esta sonando. El detector
# mide el acoplamiento eco/salida de este equipo **al principio de cada frase**,
# porque el mando de volumen de los altavoces es analogico para nosotros: subirlo
# no cambia el nivel digital, asi que un acoplamiento aprendido una sola vez se
# queda corto y el eco acaba superando el umbral (Dark se corta solo). Medido en
# este equipo, a volumen alto el eco llega a 4 600 RMS; con recalibracion por
# frase el umbral lo sigue.
BARGE_IN_MARGEN = _env("BARGE_IN_MARGEN", 1.5)

# Percentil de los niveles de eco observados que se toma como referencia.
# Directamente sobre el nivel del micro, NO sobre la relacion eco/salida:
# dividir se dispara cuando el nivel de salida pasa cerca de cero (en cada pausa
# entre silabas) y una sola muestra mala envenenaba la estimacion entera.
BARGE_IN_PERCENTIL = _env("BARGE_IN_PERCENTIL", 0.9)

# Techo de eco esperado (RMS). Por encima de esto se considera que la voz del
# usuario ya no se puede separar del eco de los altavoces, y el barge-in se
# desactiva solo en vez de cortar a Dark al azar.
#
# Es una red de seguridad, no el mecanismo normal: sin cancelacion de eco por
# hardware, a volumen muy alto el eco y la voz estan al mismo nivel y no hay
# umbral que los separe. Es preferible quedarse sin poder interrumpir (y bajar
# el volumen) que tener a Dark cortandose solo.
BARGE_IN_ECO_MAXIMO = _env("BARGE_IN_ECO_MAXIMO", 2600)

# Ventana deslizante (segundos) sobre la que se estima el eco. Al renovarse
# sola, un cambio de volumen del mando se absorbe en unos segundos.
BARGE_IN_VENTANA_ECO = _env("BARGE_IN_VENTANA_ECO", 4.0)

# Retardo (segundos) del camino altavoz -> aire -> micro. El nivel de salida que
# se usa como referencia de eco va retrasado esta cantidad, para que las dos
# senales esten alineadas en el tiempo.
BARGE_IN_RETARDO_ECO = _env("BARGE_IN_RETARDO_ECO", 0.15)

# Suavizado del nivel del micro (0-1) para ponerlo en la misma escala de tiempo
# que el de la salida (~200 ms en ambos lados). Sin esto la relacion eco/salida
# es ruido.
BARGE_IN_SUAVIZADO = _env("BARGE_IN_SUAVIZADO", 0.4)

# Un pico aislado por encima de este factor puede ser eco o resonancia. Para
# aceptar un corte rapido debe superar el umbral durante varios bloques seguidos.
BARGE_IN_FACTOR_ATAQUE = _env("BARGE_IN_FACTOR_ATAQUE", 2.0)
BARGE_IN_ATAQUE_BLOQUES = _env("BARGE_IN_ATAQUE_BLOQUES", 2)

# RMS minimo absoluto, solo como ultimo recurso cuando no hay eco que medir
# (auriculares) o el audio empieza en silencio digital.
#
# Esta BAJO a proposito: cuando estaba en 1 200 obligaba a acercarse al
# microfono, porque el umbral real es el del eco y este suelo solo debe evitarlo
# todo con la sala en silencio. El ruido de fondo medido es 80-260 RMS, asi que
# 400 sigue muy por encima.
BARGE_IN_RMS_MINIMO = _env("BARGE_IN_RMS_MINIMO", 400)

# Bloques sostenidos por encima del umbral antes de cortar el TTS (~240 ms).
BARGE_IN_BLOQUES = _env("BARGE_IN_BLOQUES", 3)

# Cuanto tiempo (segundos) se mide el eco al principio de cada tramo de voz
# antes de permitir un corte. Es el precio de no saber cuanto eco hay hasta
# haberlo oido; con menos, la estimacion sale de un trozo poco representativo.
# Antes 1.2 s; reducido a 0.8 s para no bloquear la primera frase.
BARGE_IN_GRACIA = _env("BARGE_IN_GRACIA", 0.8)

# ---------------------------------------------------------------------------
#  Supervisor
# ---------------------------------------------------------------------------

# Arrancar los servidores al iniciar el sistema (si no, se levantan al usarlos).
ARRANQUE_AUTO = _env("ARRANQUE_AUTO", True)

# Segundos maximos a esperar a que un servidor cargue y responda.
ESPERA_ARRANQUE = _env("ESPERA_ARRANQUE", 120.0)

# Cada cuanto comprueba el supervisor que siguen vivos (segundos).
INTERVALO_SALUD = _env("INTERVALO_SALUD", 20.0)

# Reintentos de arranque antes de darse por vencido con un servidor.
MAX_REINTENTOS = _env("MAX_REINTENTOS", 5)

# Punta de la senal de salud (segundos).
TIMEOUT_SALUD = _env("TIMEOUT_SALUD", 5.0)

# Arrancar los servidores con --debug y volcar su salida en _voz_logs/.
DEBUG_SERVIDORES = _env("DEBUG", False)

# Tiempo maximo que se espera una transcripcion completa (segundos).
TIMEOUT_TRANSCRIPCION = _env("TIMEOUT_TRANSCRIPCION", 60.0)

# Tiempo maximo que se espera el primer trozo de audio del TTS (segundos).
TIMEOUT_PRIMER_AUDIO = _env("TIMEOUT_PRIMER_AUDIO", 15.0)
