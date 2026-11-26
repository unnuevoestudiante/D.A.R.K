"""Adaptador de Ollama para el contrato común de chat.

Módulo del motor: solo lo importa `proveedores/llm/fabrica.py`. Un consumidor
que importa este archivo queda atado a Ollama aunque use tipos neutros.
"""
import json
import os
from typing import Any, Dict, Mapping, Optional

import requests

from proveedores.llm.contrato import ChatEvent, ChatRequest, ChatResult
from config_runtime import get_runtime_value


def _payload(request: ChatRequest, stream: bool) -> Dict[str, Any]:
    """Traduce opciones canónicas a la API específica de Ollama."""
    opciones: Dict[str, Any] = {}
    aliases = {
        "context_tokens": "num_ctx",
        "max_output_tokens": "num_predict",
        "cpu_threads": "num_thread",
        "batch_tokens": "num_batch",
        "repetition_penalty": "repeat_penalty",
        "repetition_window": "repeat_last_n",
        "top_k": "top_k",
        "temperature": "temperature",
        "top_p": "top_p",
    }
    for canonical, ollama_key in aliases.items():
        value = request.options.get(canonical)
        if value is not None:
            opciones[ollama_key] = value

    cuerpo: Dict[str, Any] = {
        "model": request.model,
        "messages": request.messages,
        "stream": stream,
        "options": opciones,
    }
    if request.residency is not None:
        cuerpo["keep_alive"] = request.residency
    if request.response_format is not None:
        cuerpo["format"] = request.response_format
    if request.reasoning_enabled is not None:
        cuerpo["think"] = request.reasoning_enabled
    return cuerpo


# Claves de /api/chat -> vocabulario canonico del contrato. Mismo truco que la
# tabla de opciones: el consumidor pregunta por conceptos, nunca por Ollama.
# Las duraciones pasan tal cual, en nanosegundos.
_METRICAS_CANONICAS = {
    "prompt_eval_count": "prompt_tokens",
    "prompt_eval_cached_count": "cached_prompt_tokens",
    "eval_count": "completion_tokens",
    "prompt_eval_duration": "prefill_ns",
    "eval_duration": "decode_ns",
    "total_duration": "total_ns",
    "load_duration": "load_ns",
    "done_reason": "finish_reason",
}


def _metrics(data: Mapping[str, Any]) -> Dict[str, Any]:
    return {canonica: data[original]
            for original, canonica in _METRICAS_CANONICAS.items()
            if original in data}


class _OllamaStream:
    def __init__(self, response):
        self._response = response
        self.status_code = getattr(response, "status_code", 200)
        self._iterator = None

    def iter_events(self):
        self._iterator = self._response.iter_lines()
        try:
            for line in self._iterator:
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except (TypeError, json.JSONDecodeError):
                    continue
                message = data.get("message") or {}
                yield ChatEvent(
                    content=message.get("content") or "",
                    finished=data.get("done") is True,
                    metrics=_metrics(data),
                )
        finally:
            close = getattr(self._iterator, "close", None)
            if close:
                close()

    def close(self):
        close = getattr(self._response, "close", None)
        if close:
            close()


class OllamaChatProvider:
    """Implementación Ollama; los consumidores solo conocen ChatProvider."""

    def __init__(self, session=None, base_url=None):
        self._http = session or requests.Session()
        self._base_url = (base_url or os.environ.get(
            "DARK_OLLAMA_URL", get_runtime_value("services.ollama.url"))).rstrip("/")

    def complete(self, request: ChatRequest, timeout: Any = None) -> ChatResult:
        response = self._http.post(
            f"{self._base_url}/api/chat",
            json=_payload(request, stream=False), timeout=timeout,
        )
        data = response.json()
        message = data.get("message") or {}
        return ChatResult(
            content=message.get("content") or "",
            model=data.get("model") or "",
            finished=data.get("done") is True,
            status_code=getattr(response, "status_code", 200),
            metrics=_metrics(data),
        )

    def stream(self, request: ChatRequest, timeout: Any = None) -> _OllamaStream:
        response = self._http.post(
            f"{self._base_url}/api/chat",
            json=_payload(request, stream=True), timeout=timeout, stream=True,
        )
        return _OllamaStream(response)

    def health(self, timeout: Any = None) -> bool:
        try:
            response = self._http.get(
                f"{self._base_url}/api/tags", timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def loaded_models(self, timeout: Any = None):
        response = self._http.get(
            f"{self._base_url}/api/ps", timeout=timeout or 2)
        if getattr(response, "status_code", 200) != 200:
            return []
        data = response.json() or {}
        return [model.get("name", "") for model in data.get("models", [])
                if model.get("name")]
