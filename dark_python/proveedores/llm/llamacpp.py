"""Adaptador de llama.cpp (`llama-server`) para el contrato común de chat.

Segunda implementación del puerto, escrita para comprobar que `ChatProvider` no
tiene forma de Ollama. Solo la importa `fabrica.py`; `DARK_LLM_PROVIDER=llamacpp`
la elige sin tocar a ningún consumidor.

Hablamos contra el endpoint compatible con OpenAI (`/v1/chat/completions`), que
es el único que recibe `messages`. El nativo `/completion` pide el prompt ya
plantillado y obligaría a Dark a conocer la plantilla de chat de cada modelo.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterable, Mapping, Optional

import requests

from proveedores.llm.contrato import ChatEvent, ChatRequest, ChatResult
from config_runtime import get_runtime_value

# Opciones del contrato que llama.cpp no acepta por solicitud: son banderas con
# las que se arranca el servidor. Un adaptador honesto las reporta en vez de
# dejarlas caer en silencio.
OPCIONES_DE_ARRANQUE = {
    "context_tokens": "--ctx-size",
    "cpu_threads": "--threads",
    "batch_tokens": "--batch-size",
}

# El contrato dice "json"; OpenAI y llama.cpp esperan el objeto completo.
_FORMATO_RESPUESTA = {"json": "json_object"}

# Vocabulario canónico -> clave del cuerpo de /v1/chat/completions.
_ALIAS = {
    "max_output_tokens": "n_predict",
    "repetition_penalty": "repeat_penalty",
    "repetition_window": "repeat_last_n",
    "top_k": "top_k",
    "temperature": "temperature",
    "top_p": "top_p",
}


def _payload(request: ChatRequest, stream: bool) -> Dict[str, Any]:
    cuerpo: Dict[str, Any] = {
        "model": request.model,
        "messages": request.messages,
        "stream": stream,
        # Sin esto cada turno re-prefilaba todo el prompt; es la bandera que
        # convierte el prefijo estable en cacheo real.
        "cache_prompt": True,
    }
    for canonica, nombre in _ALIAS.items():
        valor = request.options.get(canonica)
        if valor is not None:
            cuerpo[nombre] = valor

    if request.response_format is not None:
        fmt = request.response_format
        if isinstance(fmt, Mapping):
            # Esquema JSON: llama-server lo pide junto al tipo json_object.
            cuerpo["response_format"] = {"type": "json_object", "schema": fmt}
        else:
            cuerpo["response_format"] = {
                "type": _FORMATO_RESPUESTA.get(fmt, fmt)}
    if request.reasoning_enabled is False:
        cuerpo["reasoning_effort"] = "none"
    if stream:
        cuerpo["stream_options"] = {"include_usage": True}
    return cuerpo


def _nanosegundos(desde_milis: Any) -> Optional[int]:
    if not isinstance(desde_milis, (int, float)):
        return None
    return int(round(desde_milis * 1e6))


def _metricas(data: Mapping[str, Any]) -> Dict[str, Any]:
    """`usage` + `timings` traducidos al vocabulario canónico del contrato.

    Lo que llama.cpp no reporta (`total_ns`, `load_ns`) simplemente no va: los
    consumidores consultan con `.get()`.
    """
    metricas: Dict[str, Any] = {}
    uso = data.get("usage") or {}
    detalles = uso.get("prompt_tokens_details") or {}
    tiempos = data.get("timings") or {}

    for clave_canonica, fuente in (
        ("prompt_tokens", uso.get("prompt_tokens")),
        ("completion_tokens", uso.get("completion_tokens")),
        ("cached_prompt_tokens", detalles.get("cached_tokens",
                                             tiempos.get("cache_n"))),
        ("prefill_ns", _nanosegundos(tiempos.get("prompt_ms"))),
        ("decode_ns", _nanosegundos(tiempos.get("predicted_ms"))),
    ):
        if fuente is not None:
            metricas[clave_canonica] = fuente

    elecciones = data.get("choices") or []
    if elecciones:
        motivo = elecciones[0].get("finish_reason")
        if motivo:
            metricas["finish_reason"] = motivo
    return metricas


def _contenido(data: Mapping[str, Any]) -> str:
    opciones = data.get("choices") or []
    if not opciones:
        return ""
    primera = opciones[0]
    return ((primera.get("message") or {}).get("content")
            or (primera.get("delta") or {}).get("content")
            or "")


class LlamaCppStream:
    def __init__(self, response):
        self._response = response
        self.status_code = getattr(response, "status_code", 200)
        self._iterator = None

    def iter_events(self):
        self._iterator = self._response.iter_lines()
        # El orden real de un stream de llama-server es: deltas, un chunk con
        # `finish_reason`, otro chunk con `usage` y `choices` vacío, y `[DONE]`.
        # El consumidor del puerto lee las métricas en el evento `finished`
        # (porque en Ollama el done las trae), así que aquí `finished` es solo
        # `[DONE]` y las cifras se acumulan hasta ese momento.
        acumuladas: Dict[str, Any] = {}
        try:
            for line in self._iterator:
                if not line:
                    continue
                texto = line.decode("utf-8") if isinstance(line, bytes) else line
                if texto.startswith("data: "):
                    texto = texto[6:]
                if texto.strip() == "[DONE]":
                    yield ChatEvent(content="", finished=True,
                                    metrics=dict(acumuladas))
                    continue
                try:
                    data = json.loads(texto)
                except (TypeError, json.JSONDecodeError):
                    continue
                metricas = _metricas(data)
                acumuladas.update(metricas)
                yield ChatEvent(content=_contenido(data), finished=False,
                                metrics=metricas)
        finally:
            close = getattr(self._iterator, "close", None)
            if close:
                close()

    def close(self):
        close = getattr(self._response, "close", None)
        if close:
            close()


class LlamaCppProvider:
    """Implementación de llama.cpp; los consumidores solo conocen ChatProvider."""

    def __init__(self, session=None, base_url=None, log=None):
        self._http = session or requests.Session()
        self._base_url = (base_url or os.environ.get(
            "DARK_LLAMACPP_URL", get_runtime_value("services.llamaCpp.url"))).rstrip("/")
        self._log = log or print
        self._avisado = set()

    def _avisar_arranque(self, request: ChatRequest) -> None:
        pendientes = {c for c in OPCIONES_DE_ARRANQUE
                      if request.options.get(c) is not None}
        nuevos = pendientes - self._avisado
        if not nuevos:
            return
        self._avisado |= pendientes
        self._log("[llamacpp] estas opciones van al arrancar el servidor, no "
                  "en la solicitud: "
                  + ", ".join(f"{c}={request.options[c]} ({OPCIONES_DE_ARRANQUE[c]})"
                              for c in sorted(nuevos)))

    def complete(self, request: ChatRequest, timeout: Any = None) -> ChatResult:
        self._avisar_arranque(request)
        response = self._http.post(
            f"{self._base_url}/v1/chat/completions",
            json=_payload(request, stream=False), timeout=timeout,
        )
        data = response.json()
        return ChatResult(
            content=_contenido(data),
            model=data.get("model") or request.model,
            finished=bool((data.get("choices") or [{}])[0].get("finish_reason"))
            or data.get("done") is True,
            status_code=getattr(response, "status_code", 200),
            metrics=_metricas(data),
        )

    def stream(self, request: ChatRequest, timeout: Any = None) -> LlamaCppStream:
        self._avisar_arranque(request)
        response = self._http.post(
            f"{self._base_url}/v1/chat/completions",
            json=_payload(request, stream=True), timeout=timeout, stream=True,
        )
        return LlamaCppStream(response)

    def health(self, timeout: Any = None) -> bool:
        try:
            response = self._http.get(f"{self._base_url}/health",
                                      timeout=timeout or 2)
            return getattr(response, "status_code", 200) == 200
        except Exception:
            return False

    def loaded_models(self, timeout: Any = None) -> Iterable[str]:
        """llama-server sirve un solo modelo por instancia; /v1/models lo nombra."""
        try:
            response = self._http.get(f"{self._base_url}/v1/models",
                                      timeout=timeout or 2)
        except Exception:
            return []
        if getattr(response, "status_code", 200) != 200:
            return []
        data = response.json() or {}
        return [m.get("id", "") for m in data.get("data", []) if m.get("id")]
