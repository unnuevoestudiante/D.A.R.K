"""Credenciales de D.A.R.K.: claves en el Administrador de credenciales de Windows.

    from credenciales import clave_de, obtener

Ver `almacen.py` (acceso por `ctypes`), `claves.py` (claves de API por proveedor) y
`migracion.py` (importar `online_coder.json` con consentimiento).
"""
from .almacen import Almacen, AlmacenMemoria, AlmacenWindows, ErrorAlmacen
from . import catalogo
from .claves import (
    PREFIJO, PROVEEDORES_CONOCIDOS, ErrorClaves, ServicioClaves, clave_de, fijar_servicio,
    id_desde_nombre, id_valido, obtener,
)

__all__ = [
    "catalogo",
    "Almacen", "AlmacenMemoria", "AlmacenWindows", "ErrorAlmacen", "ErrorClaves", "PREFIJO",
    "PROVEEDORES_CONOCIDOS", "ServicioClaves", "clave_de", "fijar_servicio", "id_desde_nombre",
    "id_valido", "obtener",
]
