"""Compatibilidad histórica; implementación en :mod:`herramientas.internas`."""
import sys

from herramientas.internas import model_broker as _implementacion

sys.modules[__name__] = _implementacion
