"""Compatibilidad de importación; implementación en :mod:`intenciones.gestor`."""
import runpy
import sys

from intenciones import gestor as _implementacion

if __name__ == "__main__":
    runpy.run_module("intenciones.gestor", run_name="__main__")
else:
    sys.modules[__name__] = _implementacion
