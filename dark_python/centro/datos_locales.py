"""Dónde guarda D.A.R.K. sus datos y cómo borrarlos con seguridad.

Solo en una **instalación** (`DARK_USER_DATA_DIR` definido por el Supervisor) hay una carpeta
propia de datos. En desarrollo los datos viven mezclados con el código del repositorio, así
que «Restablecer» no existe ahí: borrar «los datos» sería borrar el repositorio.

Borrado seguro (`borrar_contenido`):
  * solo dentro de `config` y `data` de la raíz de D.A.R.K. (nunca la raíz, nunca el resto);
  * no sigue enlaces simbólicos ni uniones: borra el enlace, no lo que apunta;
  * no se detiene en el primer fallo y devuelve lo que no pudo borrar.
"""
from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from . import rutas

SUBCARPETAS_BORRABLES = ("config", "data")
NOMBRE_RAIZ = "DARK"


def es_instalacion() -> bool:
    return bool(os.environ.get("DARK_USER_DATA_DIR"))


def legible(bytes_: int) -> str:
    if bytes_ >= 1024 ** 3:
        return f"{bytes_ / 1024 ** 3:.1f} GB"
    if bytes_ >= 1024 ** 2:
        return f"{bytes_ / 1024 ** 2:.1f} MB"
    if bytes_ >= 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_} B"


def _es_enlace(ruta: Path) -> bool:
    """Enlace simbólico o unión/reparse point de Windows."""
    try:
        if ruta.is_symlink():
            return True
        atributos = getattr(ruta.lstat(), "st_file_attributes", 0)
        return bool(atributos & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    except OSError:
        return False


def tamano(ruta: Path) -> int:
    """Bytes de un archivo o carpeta, sin seguir enlaces."""
    try:
        if _es_enlace(ruta):
            return 0
        if ruta.is_file():
            return ruta.stat().st_size
        total = 0
        for carpeta, _dirs, archivos in os.walk(ruta, followlinks=False):
            for nombre in archivos:
                hijo = Path(carpeta, nombre)
                if not _es_enlace(hijo):
                    try:
                        total += hijo.stat().st_size
                    except OSError:
                        pass
        return total
    except OSError:
        return 0


def raiz_borrable() -> Path | None:
    """La raíz de D.A.R.K. del usuario (`%LOCALAPPDATA%\\DARK`) o None si no es una instalación."""
    if not es_instalacion():
        return None
    raiz = rutas.raiz_usuario()
    return raiz if raiz.name.upper() == NOMBRE_RAIZ else None


def _quitar(ruta: Path, fallidos: list[str]) -> bool:
    try:
        if _es_enlace(ruta):
            try:
                ruta.unlink()
            except (IsADirectoryError, PermissionError):
                os.rmdir(ruta)  # una unión de Windows se quita como carpeta vacía, sin tocar su destino
        elif ruta.is_dir():
            errores: list[str] = []

            def al_fallar(_func, camino, _info):
                errores.append(camino)
            shutil.rmtree(ruta, onerror=al_fallar)
            if errores:
                fallidos.append(ruta.name)
                return False
        else:
            ruta.unlink()
        return True
    except FileNotFoundError:
        return True
    except OSError:
        fallidos.append(ruta.name)
        return False


def borrar_contenido(raiz: Path) -> tuple[int, list[str]]:
    """Vacía `config` y `data` de `raiz`. Devuelve (entradas borradas, nombres que no se pudieron borrar)."""
    raiz = Path(raiz)
    if raiz.name.upper() != NOMBRE_RAIZ or len(raiz.resolve().parts) < 3:
        raise ValueError("La carpeta de D.A.R.K. no es la esperada; no se borra nada.")
    borrados, fallidos = 0, []
    for sub in SUBCARPETAS_BORRABLES:
        carpeta = raiz / sub
        if _es_enlace(carpeta) or not carpeta.is_dir():
            continue  # si la propia carpeta fuera un enlace, no se toca nada de lo que hay detrás
        for entrada in list(carpeta.iterdir()):
            if _quitar(entrada, fallidos):
                borrados += 1
    return borrados, fallidos
