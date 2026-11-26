"""Contratos de los proveedores de voz usados por el Núcleo.

MIGRADO: el contrato canónico vive ahora en `contratos/voz.py` (paquete
neutro que nucleo, especialistas y voz comparten sin ciclos). Este
archivo queda como shim de reexportación para no romper importaciones
antiguas; no añade nada nuevo.

Fuente única de verdad: dark_python/contratos/voz.py
"""
from contratos.voz import (  # noqa: F401
    PuertoSTT,
    PuertoTTS,
    ResultadoTranscripcion,
)

# Alias histórico (voz/contratos.py definía TranscriptorLocal con
# asegurar/liberar/transcribir_wav; PuertoSTT es ese mismo contrato más
# la propiedad `cargado`).
TranscriptorLocal = PuertoSTT

__all__ = ["PuertoSTT", "PuertoTTS", "ResultadoTranscripcion",
           "TranscriptorLocal"]
