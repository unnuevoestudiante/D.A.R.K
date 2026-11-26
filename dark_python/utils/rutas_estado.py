"""Resolución y migración segura de archivos de estado persistente.

Las rutas canónicas viven junto al sistema que posee los datos. Si una
instalación anterior todavía tiene el archivo en la raíz de ``dark_python``
o en ``nucleo``, se traslada solo cuando el destino aún no existe.
"""
from __future__ import annotations

import os
from pathlib import Path


def resolver_ruta_estado(
    sistema: str,
    nombre: str,
    *rutas_legacy: str,
    raiz: str | os.PathLike | None = None,
) -> str:
    """Devuelve la ruta canónica y migra un archivo antiguo sin sobrescribir.

    ``rutas_legacy`` son rutas relativas a ``dark_python``. Si ya hay un
    destino, se respeta; los archivos antiguos quedan intactos para permitir
    una recuperación manual en caso de que ambas versiones existan.
    """
    user_data = os.environ.get("DARK_USER_DATA_DIR")
    installed_data_root = raiz is None and bool(user_data)
    base = (
        Path(raiz).resolve() if raiz is not None
        else Path(user_data).expanduser().resolve() if user_data
        else Path(__file__).resolve().parent.parent
    )
    destino = base / sistema / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)
    # Installed mode keeps any legacy files in the application tree untouched.
    # Development mode retains its existing one-time migration behavior.
    if not destino.exists() and not installed_data_root:
        for relativa in rutas_legacy:
            origen = base / relativa
            if origen.is_file():
                try:
                    os.replace(origen, destino)
                except OSError:
                    # Un bloqueo externo no debe impedir que Dark arranque;
                    # el llamador todavía tendrá la ruta canónica disponible.
                    pass
                if destino.exists():
                    break
                return str(origen)
    return str(destino)
