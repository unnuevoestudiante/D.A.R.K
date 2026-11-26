"""Compatibilidad histórica; coordinador en :mod:`modulos.hive`."""
import runpy
import sys

from modulos.hive import coordinador as _implementacion

if __name__ == "__main__":
    runpy.run_module("modulos.hive.coordinador", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
