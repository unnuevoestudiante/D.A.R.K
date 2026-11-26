"""Tipos independientes del proveedor para solicitudes de chat."""
import base64
import re
from dataclasses import dataclass, field
from typing import (Any, Dict, Iterable, List, Mapping, Optional, Protocol,
                   Union, runtime_checkable)


# Las familias de modelos que marcan su cadena de pensamiento con etiquetas XML
# no dejan la etiqueta en manos del proveedor: el texto llega al consumidor con
# las marcas puestas. Una sola expresión para todas; si otra familia usa otra
# marca, se añade aquí y ningún llamador cambia.
_MARCA_RAZONAMIENTO = re.compile(
    r"<think(?:ing)?\b.*?</think(?:ing)?\s*>", re.DOTALL | re.IGNORECASE)

# Familias que escriben su cadena de pensamiento dentro del texto de la
# respuesta. Con Ollama se apagan con un flag de la solicitud; con un modelo que
# no la emite, el flag no se envia. Este es el unico sitio que conoce nombres
# de familia: los consumidores solo preguntan y obtienen el valor.
_FAMILIAS_CON_CADENA = ("qwen3",)


def apagar_razonamiento(modelo: Optional[str]) -> Optional[bool]:
    """Valor para `reasoning_enabled` segun la familia del modelo.

    False apaga la cadena de pensamiento; None significa "no opinar" y deja el
    proveedor sin enviar el flag, que es lo que ya se hacia con los modelos que
    no la emiten. Un modelo nuevo se añade a la tupla de arriba.
    """
    nombre = (modelo or "").lower()
    return False if any(f in nombre for f in _FAMILIAS_CON_CADENA) else None


def sin_razonamiento(texto: Optional[str]) -> str:
    """Texto visible de una respuesta, sin las marcas de razonamiento.

    Se aplica sobre fragmentos ya acumulados, no sobre tokens sueltos: una
    apertura de etiqueta partida por la mitad del stream solo se quita cuando
    llega su cierre.
    """
    if not texto:
        return ""
    return _MARCA_RAZONAMIENTO.sub("", texto).strip()


def bloque_imagen(datos: bytes, mime: str = "image/png") -> Dict[str, Any]:
    """Un bloque de imagen en la forma de contenido multimodal compatible con OpenAI."""
    uri = f"data:{mime};base64,{base64.b64encode(datos).decode('ascii')}"
    return {"type": "image_url", "image_url": {"url": uri}}


def mensaje_con_imagen(texto: str, datos_imagen: bytes, mime: str = "image/png",
                       rol: str = "user") -> Dict[str, Any]:
    """Un mensaje de chat con texto e imagen, para el rol «vision» (Gemini, Groq)."""
    return {"role": rol, "content": [{"type": "text", "text": texto}, bloque_imagen(datos_imagen, mime)]}


@dataclass(frozen=True)
class ChatRequest:
    """Solicitud de chat expresada con conceptos comunes entre proveedores.

    `response_format` admite dos granularidades del mismo concepto: la cadena
    ``"json"`` pide JSON libre; un ``Mapping`` es un esquema JSON y pide una
    salida que lo respete. Cada motor lo traduce a su forma (Ollama ``format``,
    llama.cpp/OpenAI ``response_format``); el consumidor no conoce el payload.

    `content` de un mensaje es normalmente texto; con un modelo de visión puede
    ser una lista de bloques (`mensaje_con_imagen` construye la forma correcta).
    Hoy solo los proveedores compatibles con OpenAI (Groq, Gemini) la entienden:
    `_cuerpo_anthropic` la convertiría a texto, así que un rol «vision» no debe
    apuntar a un proveedor Anthropic.
    """

    model: str
    messages: List[Dict[str, Any]]
    options: Mapping[str, Any] = field(default_factory=dict)
    response_format: Optional[Union[str, Mapping[str, Any]]] = None
    residency: Optional[str] = None
    reasoning_enabled: Optional[bool] = None


# Vocabulario canonico de lo que un proveedor reporta al terminar de generar.
# Las duraciones se nombran en nanosegundos porque es la unidad en la que el
# proveedor las publica y en la que el analizador de latencia las guarda; el
# contrato no convierte, solo da un nombre que no pertenezca a un motor.
METRICAS_GENERACION = (
    "prompt_tokens",
    "cached_prompt_tokens",
    "completion_tokens",
    "prefill_ns",
    "decode_ns",
    "total_ns",
    "load_ns",
    "finish_reason",
)


@dataclass(frozen=True)
class ChatResult:
    """Respuesta completa; `metrics` llega en las claves de `METRICAS_GENERACION`.

    Un proveedor que no mide algo simplemente no lo manda: los consumidores
    consultan con `.get()` y el número que falta no detiene un turno.
    """

    content: str
    model: str = ""
    finished: bool = True
    status_code: int = 200
    metrics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatEvent:
    """Evento de un stream: puede traer texto, metadatos o cierre."""

    content: str = ""
    finished: bool = False
    metrics: Mapping[str, Any] = field(default_factory=dict)


class ChatStream(Protocol):
    status_code: int

    def iter_events(self) -> Iterable[ChatEvent]: ...

    def close(self) -> None: ...


@runtime_checkable
class ChatProvider(Protocol):
    """Puerto de chat que recibe mensajes y parámetros, no payloads HTTP."""

    def complete(self, request: ChatRequest, timeout: Any = None) -> ChatResult: ...

    def stream(self, request: ChatRequest, timeout: Any = None) -> ChatStream: ...

    def health(self, timeout: Any = None) -> bool: ...

    def loaded_models(self, timeout: Any = None) -> Iterable[str]: ...
