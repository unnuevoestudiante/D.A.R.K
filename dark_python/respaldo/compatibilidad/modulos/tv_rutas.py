"""Compatibilidad histórica; implementación en :mod:`modulos.tv.rutas`."""
import sys

from modulos.tv import rutas as _implementacion

sys.modules[__name__] = _implementacion
