"""Compatibilidad de importación para el gestor histórico de temas.

La implementación vive ahora en :mod:`memoria.temas`.
"""
import runpy
import sys

from memoria import temas as _implementacion

if __name__ == "__main__":  # conserva `python -m nucleo.dark_temas`
    runpy.run_module("memoria.temas", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
