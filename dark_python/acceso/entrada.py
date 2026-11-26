"""Última actividad de teclado o mouse, como presencia.

Si el usuario escribe o mueve el mouse con la cabeza girada, está delante
aunque la cámara no le vea la cara: esa actividad cuenta como presencia y
evita el bloqueo. Lo contrario NO vale (lo decidió el usuario): no tocar
nada no prueba que se fue —puede estar leyendo o viendo un video—, así que
la inactividad nunca bloquea por sí sola; manda la cámara.

Windows: GetLastInputInfo da el tick de la última entrada. Fuera de Windows
(o si falla) no hay dato y se devuelve 0.0, que equivale a «sin actividad».
"""
from __future__ import annotations

import ctypes
import os
import time


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def segundos_sin_entrada() -> float | None:
    """Segundos desde la última tecla o movimiento de mouse; None si no se sabe."""
    if os.name != "nt":
        return None
    try:
        info = _LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        ahora = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        # Los ticks son de 32 bits y dan la vuelta cada ~49 días.
        return ((ahora - info.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


def ultima_entrada() -> float:
    """El time.monotonic() de la última actividad, o 0.0 si no se sabe."""
    idle = segundos_sin_entrada()
    if idle is None:
        return 0.0
    return time.monotonic() - idle
