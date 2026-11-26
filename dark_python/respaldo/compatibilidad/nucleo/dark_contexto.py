"""Compatibilidad de importación para el módulo histórico.

La implementación vive ahora en :mod:`memoria.contexto`.
"""
import runpy
import sys

from memoria import contexto as _implementacion

if __name__ == "__main__":  # conserva el modo de demostración histórico
    runpy.run_module("memoria.contexto", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
