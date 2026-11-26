"""Compatibilidad histórica; implementación en :mod:`herramientas.internas`."""
import sys

from herramientas.internas import wake_word as _implementacion

sys.modules[__name__] = _implementacion
