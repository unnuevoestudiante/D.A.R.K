"""Memoria a largo plazo de D.A.R.K. (especificación v1, cerrada el 12/11/2026).

Todo el sistema vive detrás de la bandera de memoria: con la bandera apagada el
Núcleo no toca este paquete y la memoria de sesión sigue como hasta ahora.

Decisión D2 del primer arranque (24/11/2026): **encendida por defecto**. La persona la
apaga en el Centro (Memoria) y la variable `DARK_MEMORIA_ACTIVA` sigue mandando si está definida
(«1» enciende, cualquier otro valor apaga). Ojo: hoy el Núcleo todavía no lee ni escribe
recuerdos en las conversaciones (etapa 4 de la especificación); la bandera solo registra la
elección para cuando se conecte.
"""
from __future__ import annotations

import os

MEMORIA_ACTIVA = os.environ.get("DARK_MEMORIA_ACTIVA", "1") == "1"


def esta_activa(preferencias=None) -> bool:
    """¿Está encendida? La variable de entorno manda; si no está, la preferencia; por defecto, sí."""
    explicita = os.environ.get("DARK_MEMORIA_ACTIVA")
    if explicita is not None:
        return explicita == "1"
    if preferencias is not None:
        try:
            return bool(preferencias.obtener("ajustes.memoriaActiva", True))
        except Exception:
            return True
    return True