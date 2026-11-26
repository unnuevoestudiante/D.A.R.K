"""Compatibilidad histórica; implementación en :mod:`herramientas.internas`."""
import sys

from herramientas.internas import tracer as _implementacion

sys.modules[__name__] = _implementacion
