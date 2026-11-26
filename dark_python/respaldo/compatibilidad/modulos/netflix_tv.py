"""Compatibilidad histórica; implementación en :mod:`modulos.tv.netflix`."""
import sys

from modulos.tv import netflix as _implementacion

sys.modules[__name__] = _implementacion
