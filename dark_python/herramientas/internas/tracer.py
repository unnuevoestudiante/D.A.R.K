# dark_trace.py
#
# Molde de instrumentación para el pipeline de voz de D.A.R.K (todo-en-un-
# proceso Python). Objetivo: medir, sin adivinar, cuánto tarda cada etapa de
# un turno de voz. Cero infraestructura nueva para empezar -- funciona con un
# simple print(); si más adelante querés verlo centralizado junto con el
# Gestor de Recursos y el Task Manager, hay un modo opcional que reporta a
# DarkPulse (ver el `reporter` al final).
#
# Diseño clave, igual que la versión C# que ya vimos: medir NUNCA debe
# agregar latencia real al pipeline de voz. Por eso el reporte a DarkPulse
# (si lo activás) es fire-and-forget en un hilo aparte.

from __future__ import annotations

import time
import uuid
import json
import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

# Mismas etapas que ya identificamos en el código real de Dark. Agregá más
# si hace falta, pero no le cambies el nombre a las existentes: así los
# resúmenes de distintos turnos se pueden comparar entre sí.
STAGE_CAPTURE = "capture"          # recognizer.listen() -- desde que arranca hasta que vuelve audio
STAGE_STT = "stt"                  # self.transcribir()
STAGE_WAKEWORD_MATCH = "wakeword_match"   # difflib, debería ser ~0ms
STAGE_CLASSIFIER = "classifier"    # _clasificar_necesita_herramienta
STAGE_LLM_STREAM = "llm_stream"    # todo el streaming de _ask_core_con_herramientas
STAGE_LLM_TOOL_CHOICE = "llm_tool_choice"   # _llm_elegir_tool: pregunta de 6 tokens de salida
STAGE_TOOL_EXEC = "tool_exec"      # _ejecutar_herramienta
STAGE_TTS = "tts"                  # generación + reproducción de una frase
STAGE_INTENCION = "intencion"      # interpretar + ejecutar la acción reconocida


def set_trace_metadata(trace, **fields):
    setter = getattr(trace, "set_metadata", None)
    if callable(setter):
        setter(**fields)


def set_trace_error(trace, error, phase):
    setter = getattr(trace, "set_error", None)
    if callable(setter):
        setter(error, phase)


def trace_has_mark(trace, name):
    checker = getattr(trace, "has_mark", None)
    return bool(checker(name)) if callable(checker) else False


@dataclass
class _TurnTrace:
    turn_id: str
    started_at: float = field(default_factory=time.time)
    started_monotonic_ns: int = field(default_factory=time.perf_counter_ns)
    events: list = field(default_factory=list)  # (stage, duration_ms, note)
    inference_events: list = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, stage, duration_ms, note=None):
        with self.lock:
            self.events.append((stage, duration_ms, note))

    def add_inference(self, event):
        with self.lock:
            self.inference_events.append(event)

    def snapshot_events(self):
        with self.lock:
            return list(self.events), list(self.inference_events)

    def total_ms(self):
        events, _ = self.snapshot_events()
        return sum(e[1] for e in events)

    def summary_lines(self, events=None):
        # Las etapas no cubren todo el turno (la ruta de intención no tiene
        # stage propio). Sin el tiempo real del turno, un "total 0ms" parece
        # que no costó nada cuando en verdad se fueron 11 s fuera del radar.
        real = (time.time() - self.started_at) * 1000
        if events is None:
            events, _ = self.snapshot_events()
        sumado = sum(e[1] for e in events)
        fuera = real - sumado
        remate = f"  | {fuera:.0f}ms sin etapa" if fuera > 500 else ""
        lines = [f"=== Turno {self.turn_id} — etapas {sumado:.0f}ms, "
                 f"turno real {real:.0f}ms{remate} ==="]
        for stage, dur, note in events:
            extra = f"  // {note}" if note else ""
            lines.append(f"  {stage:<16} {dur:7.0f}ms{extra}")
        return lines


class InferenceTrace:
    """Métricas de una petición local, sin inferir tiempos de cola."""

    _DURATIONS = {
        "request_build_ns": ("request_build_start", "request_ready"),
        "worker_idle_wait_ns": ("worker_started", "worker_idle_ready"),
        "worker_idle_wait_failed_ns": (
            "worker_started", "worker_idle_wait_failed"),
        "model_residency_check_ns": (
            "model_residency_check_start", "model_residency_check_end"),
        "lock_wait_ns": ("lock_wait_start", "lock_acquired"),
        "lock_acquire_failed_ns": (
            "lock_wait_start", "lock_acquire_failed"),
        "lock_held_ns": ("lock_acquired", "lock_released"),
        "broker_lock_wait_ns": ("broker_lock_wait_start", "broker_lock_acquired"),
        "broker_ps_ns": ("broker_ps_start", "broker_ps_end"),
        "manager_load_ns": ("manager_load_start", "manager_load_end"),
        "model_prepare_ns": ("model_prepare_start", "model_prepare_end"),
        "broker_ensure_ns": ("broker_ensure_start", "broker_ensure_end"),
        "post_to_headers_ns": ("post_start", "headers_received"),
        "post_to_response_received_ns": ("post_start", "response_received"),
        "post_to_first_chunk_ns": ("post_start", "first_chunk"),
        "post_to_first_content_ns": ("post_start", "first_content"),
        "post_to_response_done_ns": ("post_start", "response_done"),
        "post_to_iterator_exit_ns": ("post_start", "iterator_exit"),
        "post_to_iterator_close_ns": ("post_start", "iterator_close_called"),
        "request_wall_ns": ("request_started", "response_handled"),
        "request_to_fallback_ns": (
            "request_started", "fallback_message_selected"),
        "post_to_fallback_ns": ("post_start", "fallback_message_selected"),
        "request_to_fallback_queued_ns": (
            "request_started", "fallback_message_queued"),
        "post_to_fallback_queued_ns": (
            "post_start", "fallback_message_queued"),
        "headers_to_response_handled_ns": (
            "headers_received", "response_handled"),
        "response_processing_ns": ("response_received", "response_handled"),
        "response_to_speech_thread_join_ns": (
            "response_done", "speech_thread_joined"),
    }

    def __init__(self, tracer, task_type, model, stream, parent_turn_id=None):
        self.request_id = uuid.uuid4().hex
        self.task_type = task_type
        self.model = model
        self.stream = stream
        self.parent_turn_id = parent_turn_id
        self._tracer = tracer
        self._marks = {}
        self._ollama = {}
        self._metadata = {}
        self._error = None
        self._outcome = "incomplete"
        self._finished = False
        self._lock = threading.Lock()

    def mark(self, name):
        with self._lock:
            if not self._finished:
                self._marks.setdefault(name, time.perf_counter_ns())

    # Clave historica del registro -> vocabulario canonico del proveedor.
    # El bloque persistido conserva los nombres de siempre porque el analisis de
    # latencia ya los lee; lo que no puede volver a pasar es que un consumidor
    # lea claves de Ollama desde el puerto.
    _PERSISTIDAS = (
        ("prompt_eval_count", "prompt_tokens"),
        ("prompt_eval_cached_count", "cached_prompt_tokens"),
        ("prompt_eval_duration", "prefill_ns"),
        ("eval_count", "completion_tokens"),
        ("eval_duration", "decode_ns"),
        ("total_duration", "total_ns"),
        ("load_duration", "load_ns"),
    )

    def set_metricas_generacion(self, datos):
        with self._lock:
            if self._finished:
                return
            self._ollama = {historica: datos[canonica]
                            for historica, canonica in self._PERSISTIDAS
                            if canonica in datos}

    def set_metadata(self, **fields):
        if os.environ.get("DARK_DIAGNOSTICS") != "1":
            return
        with self._lock:
            if not self._finished:
                self._metadata.update(fields)

    def set_error(self, error, phase):
        if os.environ.get("DARK_DIAGNOSTICS") != "1":
            return
        with self._lock:
            if self._finished:
                return
            self._error = {
                "phase": phase,
                "exception_type": type(error).__name__,
            }

    def has_mark(self, name):
        with self._lock:
            return name in self._marks

    def finish(self, outcome):
        with self._lock:
            if self._finished:
                return
            self._marks["event_finalized"] = time.perf_counter_ns()
            self._outcome = outcome
            self._finished = True
            marks = dict(self._marks)
            event = {
                "event": "llm_request",
                "request_id": self.request_id,
                "parent_turn_id": self.parent_turn_id,
                "task_type": self.task_type,
                "model": self.model,
                "stream": self.stream,
                "outcome": self._outcome,
                "wall_time_unix_ns": time.time_ns(),
                "timestamps_ns": marks,
                "durations_ns": {
                    name: marks[end] - marks[start]
                    for name, (start, end) in self._DURATIONS.items()
                    if start in marks and end in marks
                },
                "metadata": dict(self._metadata),
                "error": self._error,
                "ollama": dict(self._ollama),
            }
        self._tracer.record_inference(event)


class TurnTracer:
    """
    Un TurnTracer por turno de voz (una detección de wake word + su
    conversación). Se crea al detectar la wake word y se descarta al volver
    a 'idle'.

    Uso:
        tracer = TurnTracer()

        with tracer.measure(STAGE_STT):
            texto = self.transcribir(audio)

        tracer.record(STAGE_WAKEWORD_MATCH, 0.3)  # si ya tenés la duración

        tracer.finish()  # imprime (y opcionalmente reporta) el resumen
    """

    def __init__(self, turn_id=None, reporter=None):
        self._trace = _TurnTrace(turn_id or uuid.uuid4().hex[:8])
        self._reporter = reporter  # opcional: instancia de DarkPulseReporter
        self._finished = False
        self._finish_lock = threading.Lock()

    @property
    def turn_id(self):
        return self._trace.turn_id

    @contextmanager
    def measure(self, stage, note=None):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            dur_ms = (time.perf_counter() - t0) * 1000
            self.record(stage, dur_ms, note)

    def record(self, stage, duration_ms, note=None):
        with self._finish_lock:
            late = self._finished
            if not late:
                self._trace.add(stage, duration_ms, note)
        if late:
            self._print_late_stage(stage, duration_ms)

    @staticmethod
    def _print_late_stage(stage, duration_ms):
        print("[DARK-STAGE-LATE] " + json.dumps({
            "stage": stage,
            "duration_ms": duration_ms,
            "late_event": True,
        }, ensure_ascii=True, separators=(",", ":")))

    def begin_inference(self, task_type, model, stream, parent_turn_id=None):
        return InferenceTrace(
            self, task_type, model, stream,
            parent_turn_id or self.turn_id)

    def record_inference(self, event):
        with self._finish_lock:
            late = self._finished
            if not late:
                self._trace.add_inference(event)
        if late:
            self._print_inference(event, late=True)

    @staticmethod
    def _print_inference(event, late=False):
        output = dict(event)
        if late:
            output["late_event"] = True
        print("[LLM-METRICS] " + json.dumps(output, ensure_ascii=True,
                                            separators=(",", ":")))

    def finish(self):
        with self._finish_lock:
            if self._finished:
                return
            self._finished = True
            events, inference_events = self._trace.snapshot_events()
        if os.environ.get("DARK_DIAGNOSTICS") == "1":
            ended_ns = time.perf_counter_ns()
            print("[DARK-TURN] " + json.dumps({
                "event": "turn_finished",
                "turn_id": self.turn_id,
                "wall_time_unix_ns": time.time_ns(),
                "started_ns": self._trace.started_monotonic_ns,
                "finished_ns": ended_ns,
                "duration_ns": ended_ns - self._trace.started_monotonic_ns,
            }, ensure_ascii=True, separators=(",", ":")), flush=True)
        for line in self._trace.summary_lines(events):
            print(line)
        for event in inference_events:
            self._print_inference(event)
        if self._reporter:
            self._reporter.send(self._trace)


class NullTracer:
    """
    Se comporta igual que TurnTracer pero no mide ni imprime nada. Pasala
    en vez de un TurnTracer real para apagar la instrumentación sin tener
    que tocar el resto del código (por ejemplo, en producción una vez que
    ya optimizaste y no la necesitás corriendo todo el tiempo).
    """

    @contextmanager
    def measure(self, stage, note=None):
        yield

    def record(self, stage, duration_ms, note=None):
        pass

    def begin_inference(self, task_type, model, stream, parent_turn_id=None):
        return None

    def finish(self):
        pass


class DarkPulseReporter:
    """
    Opcional. Si en algún momento querés ver los turnos de voz en el mismo
    lugar que el Gestor de Recursos y el Task Manager, instanciá esto y
    pasaselo a TurnTracer(reporter=...). Requiere 'requests' (ya lo usás
    en main.py) y que DarkPulse esté corriendo en localhost:5052.
    """

    def __init__(self, base_url="http://localhost:5052"):
        self._base_url = base_url

    def send(self, trace: _TurnTrace):
        threading.Thread(target=self._send_sync, args=(trace,), daemon=True).start()

    def _send_sync(self, trace: _TurnTrace):
        import requests  # import local: si DarkPulse no está, no queremos
                          # que este módulo rompa nada por un import fallido
        payload = {
            "turnId": trace.turn_id,
            "service": "DarkVoice",
            "events": [
                {"stage": stage, "durationMs": dur, "note": note}
                for stage, dur, note in trace.events
            ],
            "finalized": True,
        }
        try:
            requests.post(f"{self._base_url}/telemetry/turn", json=payload, timeout=0.8)
        except Exception:
            pass  # igual que en la versión C#: la telemetría nunca debe
                  # frenar ni romper el turno de voz real
