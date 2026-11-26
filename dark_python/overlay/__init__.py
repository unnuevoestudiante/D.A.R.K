"""Subsistema de overlay: el puerto, la config y la fábrica del puente.

El núcleo importa SOLO de aquí (o de `contratos.overlay` para el tipo):

    from overlay import crear_bridge          # levanta el puente
    from contratos.overlay import PuertoOverlay  # el tipo, para anotar/dobles

El motor (modulos/dark_overlay_bridge.py) no se importa fuera de fabrica.py.
"""
from . import config
from .config import configuracion
from .fabrica import crear_bridge
from .fachada import FachadaOverlay

__all__ = ["config", "configuracion", "crear_bridge", "FachadaOverlay"]
