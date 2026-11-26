"""Compatibilidad histórica; servidor en :mod:`modulos.hive.servidor`."""
import runpy
import sys

from modulos.hive import servidor as _implementacion

if __name__ == "__main__":
    runpy.run_module("modulos.hive.servidor", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
