"""
cliente.py — Cliente del protocolo Wyoming (JSONL + PCM sobre TCP).

Solo se implementa lo que Jarvis necesita:

  * sondeo sincrono (`describe` -> `info`) para el health-check del supervisor,
  * ASR por lotes (`transcribe` + `audio-start`/`audio-chunk`/`audio-stop`
    -> `transcript`),
  * TTS en streaming (`synthesize` -> `audio-start`/`audio-chunk`.../`audio-stop`),
  * remuestreo, para poder pasar el audio de Piper (22 050 Hz) al ASR (16 kHz).

El flujo de eventos esta documentado en
https://github.com/OHF-Voice/wyoming#event-flow
"""

import asyncio
import json
import os
import socket
import threading
import time

import numpy as np

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.asr import Transcribe, Transcript
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize

from . import config

import concurrent.futures


def correr_async(factory):
    """Ejecuta `factory()` (que devuelve una corrutina) de forma segura.

    `asyncio.run()` falla si el hilo ya tiene event loop (p. ej. precache
    desde un contexto asyncio). En ese caso se usa un hilo aparte.
    """
    def _en_hilo_limpio():
        return asyncio.run(factory())

    try:
        asyncio.get_running_loop()
        hay_loop = True
    except RuntimeError:
        hay_loop = False
    if not hay_loop:
        return _en_hilo_limpio()
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="voz-async"
    ) as pool:
        return pool.submit(_en_hilo_limpio).result()


# ---------------------------------------------------------------------------
#  Candado de sintesis
# ---------------------------------------------------------------------------
#
# `wyoming-piper` carga el modelo de voz de forma perezosa y llama al
# fonemizador de espeak-ng, que usa estado global y NO es seguro entre hilos.
# Con dos peticiones de sintesis a la vez (el precalentamiento de arranque y la
# primera frase real, por ejemplo) el servidor se quedaba colgado: se veia
# fonemizar en su log y nunca llegaba el audio.
#
# Toda peticion de sintesis del proceso pasa por aqui. Cada llamada corre su
# propio bucle de eventos en su propio hilo, asi que un candado normal de hilos
# serializa correctamente sin bloquear ningun bucle ajeno.
LOCK_SINTESIS = threading.RLock()
# Contador visible para el supervisor: no reiniciar Piper a mitad de frase
_SINTESIS_EN_CURSO = 0
_SINTESIS_CONTADOR_LOCK = threading.Lock()

def sintesis_en_curso() -> bool:
    with _SINTESIS_CONTADOR_LOCK:
        return _SINTESIS_EN_CURSO > 0

# Traza de eventos de sintesis para diagnostico: VOZ_TRAZA=1
_TRAZA = os.environ.get("VOZ_TRAZA", "").strip().lower() in (
    "1", "true", "si", "sí", "yes", "on",
)


# ---------------------------------------------------------------------------
#  Utilidades
# ---------------------------------------------------------------------------


def partir_uri(uri):
    """'tcp://127.0.0.1:10300' -> ('127.0.0.1', 10300)."""
    if not uri or "://" not in uri:
        raise ValueError(f"uri invalida: {uri!r}")
    esquema, resto = uri.split("://", 1)
    if esquema != "tcp":
        raise ValueError(f"solo se soporta tcp://, no {esquema!r}")
    host, _, puerto = resto.rpartition(":")
    if not host or not puerto:
        raise ValueError(f"uri sin host o puerto: {uri!r}")
    return host, int(puerto)


def resamplear(pcm, rate_in, rate_out):
    """Remuestreo lineal de PCM int16 mono. Suficiente para alimentar el ASR."""
    if rate_in == rate_out or not pcm:
        return pcm
    a = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if a.size == 0:
        return b""
    n = int(a.size * rate_out / rate_in)
    if n <= 0:
        return b""
    idx = np.linspace(0.0, a.size - 1, n)
    return np.interp(idx, np.arange(a.size), a).astype(np.int16).tobytes()


def rms(pcm):
    """Nivel RMS de un bloque PCM int16."""
    if not pcm:
        return 0.0
    a = np.frombuffer(pcm, dtype=np.int16)
    if a.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(a.astype(np.float32) ** 2)))


# ---------------------------------------------------------------------------
#  Sondeo sincrono (health-check)
# ---------------------------------------------------------------------------


def _resumir_info(data):
    asr = data.get("asr") or []
    tts = data.get("tts") or []
    resumen = {
        "vivo": True,
        "asr": [p.get("name") for p in asr],
        "tts": [p.get("name") for p in tts],
    }
    if asr:
        resumen["requiere_vad_externo"] = asr[0].get("requires_external_vad")
        resumen["modelos_asr"] = [
            m.get("name") for m in (asr[0].get("models") or [])
        ]
    if tts:
        resumen["voces_tts"] = [
            v.get("name") for v in (tts[0].get("voices") or [])
        ]
    return resumen


def sondear(uri, timeout=None):
    """Handshake `describe` -> `info` por socket crudo, sin asyncio.

    Devuelve un resumen del `info`, o None si el servidor no responde.
    """
    timeout = config.TIMEOUT_SALUD if timeout is None else timeout
    try:
        host, puerto = partir_uri(uri)
    except (ValueError, TypeError):
        return None

    try:
        with socket.create_connection((host, puerto), timeout=timeout) as s:
            s.settimeout(timeout)
            s.sendall(b'{"type":"describe"}\n')
            buf = b""
            limite = time.monotonic() + timeout
            while time.monotonic() < limite:
                try:
                    trozo = s.recv(8192)
                except socket.timeout:
                    return None
                if not trozo:
                    return None
                buf += trozo
                while b"\n" in buf:
                    linea, buf = buf.split(b"\n", 1)
                    if not linea.strip():
                        continue
                    try:
                        ev = json.loads(linea.decode("utf-8"))
                    except ValueError:
                        continue
                    if ev.get("type") == "info":
                        return _resumir_info(ev.get("data") or {})
    except OSError:
        return None
    return None


# ---------------------------------------------------------------------------
#  TTS en streaming
# ---------------------------------------------------------------------------


async def sintetizar_stream(uri, texto, al_recibir_pcm, parar=None,
                            timeout_primer=None, al_empezar_audio=None):
    """Serializa la peticion de sintesis y delega.

    El candado es imprescindible: ver la explicacion de LOCK_SINTESIS.
    """
    global _SINTESIS_EN_CURSO
    with LOCK_SINTESIS:
        with _SINTESIS_CONTADOR_LOCK:
            _SINTESIS_EN_CURSO += 1
        try:
            return await _sintetizar_stream(
                uri, texto, al_recibir_pcm, parar, timeout_primer, al_empezar_audio
            )
        finally:
            with _SINTESIS_CONTADOR_LOCK:
                _SINTESIS_EN_CURSO = max(0, _SINTESIS_EN_CURSO - 1)


async def _sintetizar_stream(uri, texto, al_recibir_pcm, parar,
                             timeout_primer, al_empezar_audio):
    """Pide a Piper que sintetice `texto` y entrega el PCM en cuanto llega.

    `al_recibir_pcm(bytes)` se llama por cada trozo de audio (puede bloquear:
    es lo que da el ritmo de reproduccion). `parar` es un threading.Event
    opcional; si se activa, se corta la sintesis. `al_empezar_audio(rate,
    width, channels)` avisa del formato antes del primer trozo.

    Devuelve un dict con tiempos: primer_ms, total_ms, bytes, rate, width,
    channels, frases (numero de audio-start vistos).
    """
    timeout_primer = (
        config.TIMEOUT_PRIMER_AUDIO if timeout_primer is None else timeout_primer
    )
    t0 = time.perf_counter()
    primer_ms = None
    total_bytes = 0
    rate = width = canales = None
    frases = 0

    async with AsyncTcpClient.from_uri(uri) as client:
        await client.write_event(Synthesize(text=texto).event())
        while True:
            if parar is not None and parar.is_set():
                break
            try:
                ev = await asyncio.wait_for(client.read_event(), timeout=timeout_primer)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"el TTS no mando audio en {timeout_primer:.0f}s"
                )
            if ev is None:
                break
            if _TRAZA:
                print(f"[traza tts] {(time.perf_counter()-t0)*1000:7.0f} ms "
                      f"{ev.type} {dict(ev.data or {})}", flush=True)

            if AudioStart.is_type(ev.type):
                a = AudioStart.from_event(ev)
                rate, width, canales = a.rate, a.width, a.channels
                frases += 1
                if al_empezar_audio is not None:
                    al_empezar_audio(rate, width, canales)
            elif AudioChunk.is_type(ev.type):
                audio = AudioChunk.from_event(ev).audio
                if not audio:
                    continue
                if primer_ms is None:
                    primer_ms = (time.perf_counter() - t0) * 1000.0
                total_bytes += len(audio)
                al_recibir_pcm(audio)
            elif AudioStop.is_type(ev.type):
                # `audio-stop` cierra la respuesta completa a este `synthesize`
                # (Piper manda un unico audio-start/audio-stop aunque el texto
                # tenga varias frases). Hay que salir aqui: despues del
                # audio-stop Piper deja la conexion abierta esperando otra
                # peticion, asi que seguir leyendo es esperar para siempre.
                break

    return {
        "primer_ms": primer_ms,
        "total_ms": (time.perf_counter() - t0) * 1000.0,
        "bytes": total_bytes,
        "rate": rate,
        "width": width,
        "channels": canales,
        "frases": frases,
    }


# ---------------------------------------------------------------------------
#  ASR por lotes
# ---------------------------------------------------------------------------


async def transcribir(uri, pcm, rate, width=2, channels=1, language=None,
                      timeout=None):
    """Envia un WAV/PCM completo y devuelve (texto, segundos).

    Manda el audio en trozos de 250 ms para no llenar el socket de golpe.
    """
    timeout = config.TIMEOUT_TRANSCRIPCION if timeout is None else timeout
    t0 = time.perf_counter()
    idioma = language or config.WHISPER_LANGUAGE

    async with AsyncTcpClient.from_uri(uri) as client:
        await client.write_event(Transcribe(language=idioma).event())
        await client.write_event(
            AudioStart(rate=rate, width=width, channels=channels).event()
        )
        paso = max(1, rate * width * channels // 4)  # 250 ms
        for i in range(0, len(pcm), paso):
            await client.write_event(
                AudioChunk(rate=rate, width=width, channels=channels,
                           audio=pcm[i:i + paso]).event()
            )
        await client.write_event(AudioStop().event())

        while True:
            try:
                ev = await asyncio.wait_for(client.read_event(), timeout=timeout)
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"el ASR no respondio en {timeout:.0f}s"
                )
            if ev is None:
                return None, time.perf_counter() - t0
            if Transcript.is_type(ev.type):
                return Transcript.from_event(ev).text, time.perf_counter() - t0
