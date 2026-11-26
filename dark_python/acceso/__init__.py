"""Paquete de acceso: fachada, fábrica y configuración; la implementación
facial vive en herramientas/dark_acceso.py (el usuario pidió conservar ese
nombre).

Import público del núcleo:

    from acceso import FachadaAcceso
"""
from . import config
from .config import configuracion
from .fachada import FachadaAcceso
from .fabrica import crear_gate, crear_servicio_camara

__all__ = ["FachadaAcceso", "crear_gate", "crear_servicio_camara", "config",
           "configuracion"]
