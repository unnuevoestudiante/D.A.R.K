"""Carga de VLC que nunca tumba a D.A.R.K.

`python-vlc` (la parte de Python, que sí viaja en la instalación) necesita además la biblioteca nativa de VLC
(`libvlc`), que viene con la aplicación VLC. Si falta, `import vlc` **no** lanza `ImportError`: lanza
`NotImplementedError` (o hace `sys.exit(1)` si una variable de entorno apunta a una biblioteca rota). Un `except ImportError`
corriente dejaba pasar ambos y el Núcleo moría al arrancar. Aquí se captura todo y se devuelve `None`.

La detección es en vivo: cuando la persona instala VLC y vuelve a comprobar, `cargar_vlc()` lo encuentra sin reiniciar.
"""
from __future__ import annotations

import importlib
import sys
from typing import Any


def cargar_vlc() -> Any | None:
    """El módulo `vlc` si funciona (con su libvlc), o `None`."""
    try:
        modulo = importlib.import_module("vlc")
    except (Exception, SystemExit):
        sys.modules.pop("vlc", None)  # un intento fallido no debe dejar un módulo a medias
        return None
    return modulo if getattr(modulo, "dll", None) is not None else None


def crear_instancia(modulo: Any | None) -> Any | None:
    """Una instancia de VLC, o `None` si no arranca."""
    if modulo is None:
        return None
    try:
        return modulo.Instance()
    except (Exception, SystemExit):
        return None


def vlc_usable() -> bool:
    """¿Puede D.A.R.K. reproducir con VLC ahora mismo? (comprobación real, no solo «está el paquete»)."""
    return cargar_vlc() is not None
