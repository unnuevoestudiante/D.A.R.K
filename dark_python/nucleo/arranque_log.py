"""El log de arranque de la ignición: el estado real de cada pieza.

Al encender D.A.R.K. la pantalla verifica, línea a línea, la infraestructura
(«Gestor de recursos ..... EN LÍNEA»). Aquí se traduce lo que el Núcleo sabe
de cada pieza a esa línea. Es puro: las sondas las hace el Núcleo y se pasan
ya resueltas, para probarlo solo.

Estados: en_linea · cargando · en_espera · sin_respuesta. `None` en una
entrada significa «todavía no se sabe» y se publica como «cargando»: es
verdad, la pieza está arrancando.
"""
from __future__ import annotations

from typing import Any

# nivel de una capacidad (capacidades/servicio.py) → estado del log
_NIVEL = {
    "ok": "en_linea",
    "info": "en_espera",
    "atencion": "en_espera",
    "error": "sin_respuesta",
}


def _de_capacidad(capacidades: Any, ident: str) -> str:
    if not isinstance(capacidades, dict):
        return "cargando"
    for item in capacidades.get("items") or []:
        if item.get("id") == ident:
            return _NIVEL.get(item.get("nivel"), "cargando")
    return "cargando"


def _de_bool(vivo: bool | None) -> str:
    if vivo is None:
        return "cargando"
    return "en_linea" if vivo else "sin_respuesta"


def _de_modelo(ollama_vivo: bool | None, modelo_cargado: bool | None) -> str:
    if ollama_vivo is None:
        return "cargando"
    if not ollama_vivo:
        return "sin_respuesta"
    # Ollama responde pero el modelo no está en memoria: es lo normal tras el
    # arranque (se carga al usarlo o al precalentar), no un fallo.
    return "en_linea" if modelo_cargado else "en_espera"


def piezas_de_arranque(
    *,
    manager_vivo: bool | None,
    capacidades: Any,
    ollama_vivo: bool | None,
    modelo_cargado: bool | None,
) -> list[dict]:
    """Las líneas del log, en el orden en que se verifican."""
    return [
        {"id": "nucleo", "nombre": "Núcleo", "estado": "en_linea"},
        {"id": "puente", "nombre": "Puente de interfaz", "estado": "en_linea"},
        {"id": "manager", "nombre": "Gestor de recursos", "estado": _de_bool(manager_vivo)},
        {"id": "voz_entrada", "nombre": "Reconocimiento de voz",
         "estado": _de_capacidad(capacidades, "voz_entrada")},
        {"id": "voz_salida", "nombre": "Voz de salida",
         "estado": _de_capacidad(capacidades, "voz_salida")},
        {"id": "modelo_local", "nombre": "Modelo local",
         "estado": _de_modelo(ollama_vivo, modelo_cargado)},
        {"id": "vision", "nombre": "Visión y gestos",
         "estado": _de_capacidad(capacidades, "vision")},
    ]
