"""Paquete de gestos: fachada, fábrica y configuración. La implementación vive
en herramientas/gestos.py (el motor) y en herramientas/dark_gestos_canal.py (el
canal), y los nombres se conservan porque ya trabajan con ellos las pruebas y el
banco `--ver`.

Import público del núcleo:

    from gestos import FachadaGestos
"""
from . import config
from .config import configuracion
from .fachada import FachadaGestos
from .fabrica import crear_canal, crear_motor

__all__ = ["FachadaGestos", "crear_motor", "crear_canal", "config", "configuracion"]
