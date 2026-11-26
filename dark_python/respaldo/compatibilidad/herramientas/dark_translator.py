"""Compatibilidad histórica; implementación en :mod:`herramientas.externas`."""
import sys

from herramientas.externas import traductor as _implementacion

sys.modules[__name__] = _implementacion
