"""Compatibilidad histórica; implementación en :mod:`modulos.tv.modulo`."""
import runpy
import sys

from modulos.tv import modulo as _implementacion

if __name__ == "__main__":
    runpy.run_module("modulos.tv.modulo", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
