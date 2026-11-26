"""Catálogo de proveedores con los que D.A.R.K. sabe hablar, y dónde se saca la clave de cada uno.

Un proveedor es de **pensamiento** (modelos que conversan, hacen tareas o escriben código) o de **voz**.
Los de pensamiento hablan uno de dos formatos: `openai` (el «chat completions» que la mayoría imita) o
`anthropic` (la API de mensajes propia de Anthropic).

Qué se verificó en la documentación de cada proveedor (24 nov 2026) y qué no:
  * Verificado: Anthropic (`POST /v1/messages`, cabecera `anthropic-version`), DeepSeek
    (`https://api.deepseek.com/chat/completions`, modelos `deepseek-v4-pro` y `deepseek-v4-flash`),
    Mistral (`https://api.mistral.ai/v1`), Gemini (compatible con OpenAI) y las páginas de claves de
    Anthropic, OpenAI, Gemini, Groq y OpenRouter.
  * Sin verificar: la página de claves de DeepSeek y de Mistral, y los nombres de modelos de OpenAI
    (por eso no se sugiere ninguno: se escribe el que muestre su cuenta). xAI se dejó fuera por no
    haberse podido comprobar su dirección.

Las direcciones de las páginas de claves son una **lista cerrada**: «Abrir la página de claves» solo abre
una de estas, nunca una dirección que venga de la pantalla.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Proveedor:
    id: str
    nombre: str
    tipo: str  # "pensamiento" | "voz"
    formato: str  # "openai" | "anthropic" | "elevenlabs" | "fish"
    base_url: str
    url_claves: str
    modelos_sugeridos: tuple[str, ...] = ()
    nota: str = ""


PENSAMIENTO: tuple[Proveedor, ...] = (
    Proveedor("anthropic", "Anthropic (Claude)", "pensamiento", "anthropic", "https://api.anthropic.com/v1",
              "https://console.anthropic.com/settings/keys",
              ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"),
              "Se conecta con la API de mensajes de Anthropic."),
    Proveedor("openai", "OpenAI", "pensamiento", "openai", "https://api.openai.com/v1",
              "https://platform.openai.com/api-keys", (),
              "Escriba el nombre del modelo tal como lo muestra su cuenta."),
    Proveedor("deepseek", "DeepSeek", "pensamiento", "openai", "https://api.deepseek.com",
              "https://platform.deepseek.com/api_keys", ("deepseek-v4-flash", "deepseek-v4-pro")),
    Proveedor("gemini", "Google Gemini", "pensamiento", "openai",
              "https://generativelanguage.googleapis.com/v1beta/openai", "https://aistudio.google.com/apikey"),
    Proveedor("groq", "Groq", "pensamiento", "openai", "https://api.groq.com/openai/v1",
              "https://console.groq.com/keys"),
    Proveedor("openrouter", "OpenRouter", "pensamiento", "openai", "https://openrouter.ai/api/v1",
              "https://openrouter.ai/settings/keys", (), "Un solo acceso a modelos de muchos proveedores."),
    Proveedor("mistral", "Mistral", "pensamiento", "openai", "https://api.mistral.ai/v1",
              "https://console.mistral.ai/api-keys"),
)

VOZ: tuple[Proveedor, ...] = (
    Proveedor("elevenlabs", "ElevenLabs", "voz", "elevenlabs", "https://api.elevenlabs.io/v1",
              "https://elevenlabs.io/app/settings/api-keys"),
    Proveedor("fishaudio", "Fish Audio", "voz", "fish", "https://api.fish.audio",
              "https://fish.audio/app/api-keys/"),
)

TODOS: tuple[Proveedor, ...] = PENSAMIENTO + VOZ
_POR_ID = {p.id: p for p in TODOS}


def por_id(identificador: object) -> Proveedor | None:
    return _POR_ID.get(str(identificador or "").strip().lower())


def de_tipo(tipo: str) -> tuple[Proveedor, ...]:
    return tuple(p for p in TODOS if p.tipo == tipo)


def url_de_claves(identificador: object) -> str | None:
    """La página donde se crea la clave de ese proveedor (solo de la lista cerrada), o None."""
    proveedor = por_id(identificador)
    return proveedor.url_claves if proveedor is not None else None
