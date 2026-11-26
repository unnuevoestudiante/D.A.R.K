"""Compatibilidad histórica; manifiesto en :mod:`herramientas.internas`."""
import sys

from herramientas.internas import manifest_tools as _implementacion

sys.modules[__name__] = _implementacion
