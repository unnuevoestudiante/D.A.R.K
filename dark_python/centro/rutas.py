"""Rutas del Centro de configuración (preferencias y estado del primer arranque).

Contrato de M0_1_CONFIGURACION: la configuración del usuario vive en
`%LOCALAPPDATA%\\DARK\\config`, separada de los datos (`...\\data`) y de la
aplicación. En una instalación el Supervisor fija `DARK_USER_DATA_DIR` a
`%LOCALAPPDATA%\\DARK\\data`, así que la raíz del usuario es su carpeta padre.
En desarrollo (sin esa variable) se usa una carpeta propia junto al código para
no mezclar con los datos del repositorio.
"""
from __future__ import annotations

import os
from pathlib import Path

_DESARROLLO = Path(__file__).resolve().parents[1] / ".estado_usuario"


def raiz_usuario() -> Path:
    datos = os.environ.get("DARK_USER_DATA_DIR")
    if datos:
        return Path(datos).expanduser().resolve().parent
    return _DESARROLLO


def dir_config() -> Path:
    return raiz_usuario() / "config"


def dir_setup() -> Path:
    """Donde el instalador deja el registro de aceptación de condiciones."""
    return raiz_usuario() / "setup"


def ruta_preferencias() -> Path:
    return dir_config() / "preferences.json"


def ruta_primer_arranque() -> Path:
    return dir_config() / "firstrun.json"


def ruta_online_coder() -> Path:
    """Proveedores de nube (sin claves: esas van al Administrador de credenciales)."""
    return dir_config() / "online_coder.json"


def ruta_perfiles_modelos() -> Path:
    """Catálogo de modelos por perfil de equipo (viaja con la aplicación, en `config/`)."""
    return Path(__file__).resolve().parents[2] / "config" / "model-profiles.json"


def ruta_aceptacion_instalador() -> Path:
    return dir_setup() / "terms-acceptance.json"
