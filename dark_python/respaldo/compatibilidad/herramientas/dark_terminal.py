"""Compatibilidad histórica; implementación en :mod:`herramientas.externas`."""
import sys

from herramientas.externas import terminal as _implementacion

sys.modules[__name__] = _implementacion
