"""Compatibilidad de importación para la personalidad histórica."""
import sys

from identidades import personalidad as _implementacion

sys.modules[__name__] = _implementacion
