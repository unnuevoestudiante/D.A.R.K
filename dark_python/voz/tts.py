"""
tts.py — Texto a voz sobre Wyoming (Piper).

Ruta nueva:  texto -> wyoming-piper -> PCM en streaming -> tarjeta de sonido
Ruta vieja:  texto -> edge-tts (red) -> archivo MP3 -> VLC abre el archivo

Ventajas medibles (banco de pruebas en _voz_smoke/bench.py):
  * frases cortas: ~230-290 ms hasta el primer sonido,
  * no depende de la red,
  * se puede cortar al instante (barge-in),
  * el dispositivo de salida no se abre y cierra en cada frase.

Las frases cortas y repetidas (fillers, confirmaciones) se cachean en memoria:
a partir de la segunda vez suenan sin espera.
"""

import asyncio
import json
import os
import queue
import threading
import time
import uuid

from . import cliente, config
from .reproductor import ReproductorPCM

# Solo se cachean textos cortos: son los que se repiten (fillers, "Señor?", ...).
MAX_CACHE_TEXTO = 120
MAX_CACHE_ENTRADAS = 64


def _trazar_audio(evento):
    if os.environ.get("DARK_DIAGNOSTICS") != "1":
        return
    print("[DARK-AUDIO] " + json.dumps(
        evento, ensure_ascii=True, separators=(",", ":")), flush=True)


class TtsWyoming:
    """Sintesis y reproduccion de voz, con respaldo opcional."""

    def __init__(self, uri=None, voz=None, reproductor=None, respaldo=None,
                 log=print):
        self.uri = uri or config.PIPER_URI
        self.voz = voz or config.PIPER_VOICE
        self.reproductor = reproductor if reproductor is not None else ReproductorPCM()
        # `respaldo(texto, parar) -> bool`: se usa si el servidor Wyoming falla.
        # El nucleo le pasa aqui su ruta antigua (edge-tts) para no quedarse mudo.
        self.respaldo = respaldo
        self._log = log

        self._cache = {}
        self._lock_cache = threading.Lock()
        # Serializa las peticiones a Piper. No es solo orden: el servidor carga
        # el modelo de voz de forma perezosa en la primera sintesis, y dos
        # peticiones concurrentes con la voz fria (el precalentamiento de
        # arranque y la primera frase real) se quedaban las dos sin respuesta.
        self._lock_habla = threading.RLock()
        self.usos = 0
        self.fallos = 0
        self.cache_aciertos = 0

    # -- estado ------------------------------------------------------------

    @property
    def disponible(self):
        return cliente.sondear(self.uri) is not None

    @property
    def hablando(self):
        return self.reproductor.reproduciendo

    @property
    def sonando(self):
        """True si hay voz saliendo por los altavoces ahora mismo.

        `hablar()` puede tardar segundos en emitir el primer trozo (Piper
        sintetiza antes de enviar). El barge-in debe guiarse por esto y no por
        "esta ocupado", para medir el eco cuando hay eco de verdad.
        """
        return bool(getattr(self.reproductor, "sonando", False))

    @property
    def nivel_salida(self):
        """RMS de lo que esta saliendo por el altavoz.

        Es la referencia para calcular el eco esperado en el microfono: sin
        ella habria que adivinar el eco y el umbral del barge-in fallaria en
        cuanto cambiara el volumen.
        """
        return float(getattr(self.reproductor, "nivel_salida", 0.0))

    def estado(self):
        return {
            "uri": self.uri,
            "voz": self.voz,
            "disponible": self.disponible,
            "usos": self.usos,
            "fallos": self.fallos,
            "cache": len(self._cache),
            "cache_aciertos": self.cache_aciertos,
        }

    # -- API principal -----------------------------------------------------

    def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
        """Sintetiza `texto` y lo reproduce. Devuelve un dict con el resultado.

        `parar`: threading.Event opcional. Si se activa, corta la sintesis y la
        reproduccion (es lo que usa el barge-in).

        `al_pcm(pcm, rate, width, channels)`: se llama ANTES de reproducir en
        el PC (p. ej. para publicar el WAV a la tele al mismo tiempo).

        `solo_pcm`: si True, no reproduce en el PC (modo televisor: solo tele).

        En escritorio, el PCM se reproduce por fragmentos mientras Piper
        sintetiza. En modo solo TV se conserva el búfer completo para publicar
        un único audio. Las frases cacheadas siguen usando la reproducción
        directa del bloque completo.
        """
        texto = (texto or "").strip()
        if not texto:
            return {"ok": True, "vacio": True}

        if parar is None:
            parar = threading.Event()

        utterance_id = uuid.uuid4().hex[:12]
        trace = {
            "event": "tts_playback",
            "utterance_id": utterance_id,
            "wall_time_unix_ns": time.time_ns(),
            "started_ns": time.perf_counter_ns(),
            "cache": False,
            "solo_pcm": bool(solo_pcm),
        }

        def publicar_audio(pcm, rate, width, channels):
            if al_pcm is None or not pcm:
                return
            publish_started = time.perf_counter()
            trace["publish_started_wall_unix_ns"] = time.time_ns()
            try:
                al_pcm(pcm, int(rate or 22050), int(width or 2),
                       int(channels or 1))
            except Exception as e:
                self._log(f"[voz] al_pcm: {e}")
                trace["publish_error_type"] = type(e).__name__
            trace["publish_ms"] = (
                time.perf_counter() - publish_started) * 1000.0
            trace["publish_finished_wall_unix_ns"] = time.time_ns()

        with self._lock_habla:
            preparado = self._preparar_pcm(
                texto,
                parar,
                reproducir_streaming=not solo_pcm,
                publicar_durante_stream=(
                    publicar_audio if al_pcm is not None and not solo_pcm else None),
            )
        trace["synthesis_finished_ns"] = int(
            preparado.get("synthesis_finished_ns") or time.perf_counter_ns())
        if preparado.get("synthesis_finished_wall_unix_ns"):
            trace["synthesis_finished_wall_unix_ns"] = int(
                preparado["synthesis_finished_wall_unix_ns"])
        trace["cache"] = bool(preparado.get("cache"))
        trace["synth_ms"] = float(preparado.get("synth_ms") or 0.0)
        trace["first_pcm_ms"] = preparado.get("primer_ms")
        trace["pcm_bytes"] = int(preparado.get("bytes") or 0)

        if preparado.get("vacio") or preparado.get("cortado"):
            trace["result"] = "empty" if preparado.get("vacio") else "cut"
            trace["finished_ns"] = time.perf_counter_ns()
            _trazar_audio(trace)
            return preparado
        if preparado.get("respaldo") or not preparado.get("pcm"):
            # Respaldo edge-tts ya reprodujo dentro de _usar_respaldo
            if solo_pcm and preparado.get("respaldo"):
                # Idealmente no sonar en PC; el respaldo es difícil de cortar aquí
                pass
            trace["result"] = (
                "fallback" if preparado.get("respaldo") else "no_pcm")
            trace["finished_ns"] = time.perf_counter_ns()
            _trazar_audio(trace)
            return preparado

        if (al_pcm is not None and preparado.get("pcm")
                and not preparado.get("publicado")
                and not preparado.get("synthesis_error")):
            publicar_audio(
                preparado["pcm"], preparado.get("rate"),
                preparado.get("width"), preparado.get("channels"))

        if solo_pcm:
            # No abrir altavoces del PC; el audio va a la tele vía al_pcm
            preparado["ok"] = True
            preparado["solo_pcm"] = True
            synth = float(preparado.get("synth_ms") or 0.0)
            preparado["total_ms"] = synth
            if preparado.get("cache"):
                preparado["primer_ms"] = 0.0
            trace["result"] = "published_only"
            trace["finished_ns"] = time.perf_counter_ns()
            _trazar_audio(trace)
            return preparado

        if preparado.get("streamed"):
            # La síntesis y la reproducción se solapan. El consumidor ya
            # escribió cada fragmento conforme llegó; no volver a reproducir
            # el PCM completo aquí.
            if preparado.get("playback_started_ns"):
                trace["playback_started_ns"] = int(
                    preparado["playback_started_ns"])
                trace["playback_started_wall_unix_ns"] = int(
                    preparado["playback_started_wall_unix_ns"])
            if preparado.get("playback_finished_ns"):
                trace["playback_finished_ns"] = int(
                    preparado["playback_finished_ns"])
                trace["playback_finished_wall_unix_ns"] = int(
                    preparado["playback_finished_wall_unix_ns"])
            preparado["ok"] = bool(preparado.get("stream_ok"))
            preparado["total_ms"] = (
                time.perf_counter_ns() - trace["started_ns"]) / 1_000_000.0
            trace["play_ms"] = float(preparado.get("play_ms") or 0.0)
            trace.update(preparado.get("write_metrics") or {})
            trace["result"] = (
                "played" if preparado["ok"] else "playback_failed")
            trace["streamed"] = True
            trace["finished_ns"] = time.perf_counter_ns()
            _trazar_audio(trace)
            return preparado

        write_metrics = {}
        trace["playback_started_ns"] = time.perf_counter_ns()
        trace["playback_started_wall_unix_ns"] = time.time_ns()
        t0 = time.perf_counter()
        ok = self.reproductor.escribir(
            preparado["pcm"],
            parar=parar,
            rate=int(preparado.get("rate") or 22050),
            width=int(preparado.get("width") or 2),
            channels=int(preparado.get("channels") or 1),
            write_metrics=write_metrics,
        )
        play_ms = (time.perf_counter() - t0) * 1000.0
        trace["playback_finished_ns"] = time.perf_counter_ns()
        trace["playback_finished_wall_unix_ns"] = time.time_ns()
        preparado["ok"] = ok
        synth = float(preparado.get("synth_ms") or 0.0)
        preparado["total_ms"] = synth + play_ms
        if preparado.get("cache"):
            preparado["primer_ms"] = 0.0
        trace.update(write_metrics)
        trace["play_ms"] = play_ms
        trace["result"] = "played" if ok else "playback_failed"
        trace["finished_ns"] = time.perf_counter_ns()
        _trazar_audio(trace)
        return preparado

    def _preparar_pcm(self, texto, parar, reproducir_streaming=False,
                      publicar_durante_stream=None):
        """Sintetiza o lee caché y, en escritorio, reproduce durante la síntesis."""
        cacheado = self._de_cache(texto)
        if cacheado is not None:
            pcm, rate, width, canales = cacheado
            self.cache_aciertos += 1
            return {
                "ok": True, "cache": True, "respaldo": False,
                "primer_ms": 0.0,
                "synth_ms": 0.0,
                "bytes": len(pcm),
                "pcm": pcm,
                "rate": rate,
                "width": width,
                "channels": canales,
            }

        bufer = bytearray()
        cola_audio = queue.Queue(maxsize=8) if reproducir_streaming else None
        estado_stream = {
            "ok": True,
            "started_ns": None,
            "started_wall_unix_ns": None,
            "finished_ns": None,
            "finished_wall_unix_ns": None,
            "error_type": None,
            "write_count": 0,
            "write_total_ms": 0.0,
            "write_max_ms": 0.0,
        }
        formato = {
            "rate": None,
            "width": config.AUDIO_WIDTH,
            "channels": config.AUDIO_CHANNELS,
        }

        def al_empezar_audio(rate, width, canales):
            formato.update(rate=rate, width=width, channels=canales)

        def recibir(pcm):
            bufer.extend(pcm)
            if cola_audio is not None and pcm:
                # La cola limita el audio adelantado a unos pocos fragmentos.
                # Si la tarjeta va más lenta que Piper, aplica contrapresión.
                cola_audio.put(bytes(pcm))

        reproductor_hilo = None
        if cola_audio is not None:
            def consumir_audio():
                bloque_bytes = None
                pendiente = bytearray()

                def escribir_completos(final=False):
                    nonlocal pendiente
                    if not formato["rate"]:
                        return
                    if bloque_bytes is None:
                        return
                    cantidad = len(pendiente)
                    if not final:
                        cantidad -= cantidad % bloque_bytes
                    if cantidad <= 0:
                        return
                    pcm_listo = bytes(pendiente[:cantidad])
                    del pendiente[:cantidad]
                    if not estado_stream["ok"] or parar.is_set():
                        return
                    if estado_stream["started_ns"] is None:
                        estado_stream["started_ns"] = time.perf_counter_ns()
                        estado_stream["started_wall_unix_ns"] = time.time_ns()
                    write_started = time.perf_counter()
                    try:
                        ok = self.reproductor.escribir(
                            pcm_listo,
                            parar=parar,
                            rate=int(formato["rate"]),
                            width=int(formato["width"]),
                            channels=int(formato["channels"]),
                        )
                    except Exception as e:
                        ok = False
                        estado_stream["error_type"] = type(e).__name__
                    write_ms = (time.perf_counter() - write_started) * 1000.0
                    estado_stream["write_count"] += 1
                    estado_stream["write_total_ms"] += write_ms
                    estado_stream["write_max_ms"] = max(
                        estado_stream["write_max_ms"], write_ms)
                    if not ok:
                        estado_stream["ok"] = False
                        estado_stream["error_type"] = (
                            estado_stream["error_type"] or
                            ("interrupted" if parar.is_set() else "write_failed"))

                while True:
                    item = cola_audio.get()
                    try:
                        if item is None:
                            break
                        if formato["rate"] and bloque_bytes is None:
                            bloque_bytes = 512 * int(formato["width"]) * int(
                                formato["channels"])
                        if estado_stream["ok"] and not parar.is_set():
                            pendiente.extend(item)
                            escribir_completos()
                    finally:
                        cola_audio.task_done()

                escribir_completos(final=True)
                estado_stream["finished_ns"] = time.perf_counter_ns()
                estado_stream["finished_wall_unix_ns"] = time.time_ns()

            reproductor_hilo = threading.Thread(
                target=consumir_audio, name="tts-pcm-stream", daemon=True)
            reproductor_hilo.start()

        t0 = time.perf_counter()
        try:
            datos = cliente.correr_async(
                lambda: cliente.sintetizar_stream(
                    self.uri, texto, recibir, parar=parar,
                    al_empezar_audio=al_empezar_audio,
                )
            )
        except Exception as e:
            if cola_audio is not None:
                cola_audio.put(None)
                reproductor_hilo.join()
            self.fallos += 1
            self._log(f"[voz] TTS Wyoming fallo: {e}")
            if estado_stream["started_ns"] is not None:
                # No repetir desde el principio con el respaldo si ya salió
                # parte de esta frase por los altavoces.
                return {
                    "ok": False, "cache": False, "respaldo": False,
                    "error": str(e), "streamed": True, "publicado": False,
                    "stream_ok": False, "synthesis_error": True,
                    "pcm": bytes(bufer), "rate": formato["rate"],
                    "width": formato["width"],
                    "channels": formato["channels"],
                    "bytes": len(bufer),
                    "primer_ms": None, "synth_ms": (
                        time.perf_counter() - t0) * 1000.0,
                    "playback_started_ns": estado_stream["started_ns"],
                    "playback_started_wall_unix_ns":
                        estado_stream["started_wall_unix_ns"],
                    "playback_finished_ns": estado_stream["finished_ns"],
                    "playback_finished_wall_unix_ns":
                        estado_stream["finished_wall_unix_ns"],
                    "play_ms": (
                        (estado_stream["finished_ns"] - estado_stream["started_ns"])
                        / 1_000_000.0
                        if estado_stream["finished_ns"] else 0.0),
                }
            return self._usar_respaldo(texto, parar, error=str(e))

        sintesis_fin_ns = time.perf_counter_ns()
        sintesis_fin_wall_ns = time.time_ns()
        pcm = bytes(bufer) if bufer else None
        publicado = False
        if (cola_audio is not None and publicar_durante_stream is not None
                and pcm and not parar.is_set()):
            publicar_durante_stream(
                pcm, formato["rate"], formato["width"], formato["channels"])
            publicado = True
        if cola_audio is not None:
            cola_audio.put(None)
            reproductor_hilo.join()

        if parar.is_set():
            return {"ok": True, "cortado": True, "cache": False,
                    "respaldo": False,
                    "synthesis_finished_ns": sintesis_fin_ns,
                    "synthesis_finished_wall_unix_ns": sintesis_fin_wall_ns}

        self.usos += 1
        if pcm and formato["rate"]:
            self._guardar_cache(
                texto, pcm, formato["rate"], formato["width"],
                formato["channels"],
            )
        return {
            "ok": bool(pcm), "cache": False, "respaldo": False,
            "primer_ms": datos.get("primer_ms"),
            "synth_ms": (time.perf_counter() - t0) * 1000.0,
            "total_ms": datos.get("total_ms"),
            "bytes": datos.get("bytes"),
            "rate": formato["rate"],
            "pcm": pcm,
            "width": formato["width"],
            "streamed": cola_audio is not None,
            "publicado": publicado,
            "stream_ok": estado_stream["ok"],
            "stream_error_type": estado_stream["error_type"],
            "playback_started_ns": estado_stream["started_ns"],
            "playback_started_wall_unix_ns": estado_stream["started_wall_unix_ns"],
            "playback_finished_ns": estado_stream["finished_ns"],
            "playback_finished_wall_unix_ns": estado_stream["finished_wall_unix_ns"],
            "play_ms": (
                (estado_stream["finished_ns"] - estado_stream["started_ns"])
                / 1_000_000.0
                if estado_stream["started_ns"] and estado_stream["finished_ns"]
                else 0.0
            ),
            "write_metrics": {
                "write_count": estado_stream["write_count"],
                "write_total_ms": estado_stream["write_total_ms"],
                "write_max_ms": estado_stream["write_max_ms"],
                "write_error_type": estado_stream["error_type"],
            },
            "synthesis_finished_ns": sintesis_fin_ns,
            "synthesis_finished_wall_unix_ns": sintesis_fin_wall_ns,
            "channels": formato["channels"],
        }

    def cortar(self):
        """Silencia inmediatamente lo que este sonando."""
        self.reproductor.detener()

    def cerrar(self):
        self.reproductor.cerrar()

    def _usar_respaldo(self, texto, parar, error=None):
        if self.respaldo is None:
            return {"ok": False, "respaldo": False, "error": error}
        try:
            ok = self.respaldo(texto, parar)
        except Exception as e:
            return {"ok": False, "respaldo": True,
                    "error": f"{error} / respaldo: {e}"}
        return {"ok": bool(ok), "respaldo": True, "error": error}

    # -- cache -------------------------------------------------------------

    def _de_cache(self, texto):
        with self._lock_cache:
            return self._cache.get(texto)

    def _guardar_cache(self, texto, pcm, rate, width, canales):
        if len(texto) > MAX_CACHE_TEXTO:
            return
        with self._lock_cache:
            if len(self._cache) >= MAX_CACHE_ENTRADAS:
                # Fuera el primero que entro (dict mantiene el orden).
                self._cache.pop(next(iter(self._cache)), None)
            self._cache[texto] = (pcm, rate, width, canales)

    def calentar(self, frase="Listo."):
        """Fuerza la carga del modelo de voz de Piper.

        La primera sintesis de un servidor recien arrancado tarda unos 3 s mas
        porque Piper carga el ONNX de forma perezosa. Hacerlo al arrancar evita
        que el usuario note lento el primer turno.
        """
        t0 = time.perf_counter()
        with self._lock_habla:
            try:
                ok = self._sintetizar_a_cache(frase)
            except Exception as e:
                self._log(f"[voz] no pude precalentar la voz: {e}")
                return False
        if ok:
            self._log(f"[voz] TTS precalentado en {time.perf_counter() - t0:.1f}s")
        return ok

    def precachear(self, frases, en_hilo=True):
        """Sintetiza por adelantado frases fijas para que suenen sin espera."""
        pendientes = [f for f in frases if f and self._de_cache(f) is None]
        if not pendientes:
            return 0

        def _trabajo():
            hechas = 0
            for frase in pendientes:
                try:
                    if self._sintetizar_a_cache(frase):
                        hechas += 1
                except Exception as e:
                    self._log(f"[voz] no pude precachear {frase!r}: {e}")
            if hechas:
                self._log(f"[voz] {hechas} frase(s) precacheadas")
            return hechas

        if not en_hilo:
            return _trabajo()
        threading.Thread(target=_trabajo, daemon=True, name="voz-precache").start()
        return len(pendientes)

    def _sintetizar_a_cache(self, frase):
        bufer = bytearray()
        formato = {"rate": None, "width": config.AUDIO_WIDTH,
                   "channels": config.AUDIO_CHANNELS}

        def al_empezar_audio(rate, width, canales):
            formato.update(rate=rate, width=width, channels=canales)

        # El lock se toma por frase, no por lista: asi una frase real de Dark
        # no tiene que esperar a que termine todo el precalentamiento.
        with self._lock_habla:
            cliente.correr_async(
                lambda: cliente.sintetizar_stream(
                    self.uri, frase, bufer.extend, al_empezar_audio=al_empezar_audio
                )
            )
        if not bufer or not formato["rate"]:
            return False
        self._guardar_cache(frase, bytes(bufer), formato["rate"],
                            formato["width"], formato["channels"])
        return True
