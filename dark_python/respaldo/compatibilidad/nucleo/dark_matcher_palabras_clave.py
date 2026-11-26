"""Compatibilidad de importación; implementación en :mod:`intenciones`."""
import sys

from intenciones import matcher_palabras_clave as _implementacion

sys.modules[__name__] = _implementacion
