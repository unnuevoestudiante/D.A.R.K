"""«Abrir D.A.R.K. al encender el equipo»: la misma entrada que deja el instalador en HKCU\\...\\Run.

Solo para este usuario y sin permisos de administrador. Solo tiene sentido en una instalación (donde existe
`DarkSupervisor.exe` junto a la aplicación); en desarrollo no se ofrece.
"""
from __future__ import annotations

import sys
from pathlib import Path

CLAVE_RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
NOMBRE_VALOR = "D.A.R.K."


class InicioWindows:
    def __init__(self, supervisor: Path, winreg_modulo=None) -> None:
        self.supervisor = supervisor
        self._winreg = winreg_modulo

    def _reg(self):
        if self._winreg is None:
            import winreg

            self._winreg = winreg
        return self._winreg

    @property
    def disponible(self) -> bool:
        return self.supervisor.is_file() and (self._winreg is not None or sys.platform == "win32")

    def activo(self) -> bool:
        reg = self._reg()
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, CLAVE_RUN, 0, reg.KEY_READ) as clave:
                valor, _tipo = reg.QueryValueEx(clave, NOMBRE_VALOR)
                return isinstance(valor, str) and bool(valor)
        except OSError:
            return False

    def fijar(self, activo: bool) -> None:
        reg = self._reg()
        with reg.CreateKeyEx(reg.HKEY_CURRENT_USER, CLAVE_RUN, 0, reg.KEY_SET_VALUE) as clave:
            if activo:
                reg.SetValueEx(clave, NOMBRE_VALOR, 0, reg.REG_SZ, f'"{self.supervisor}"')
            else:
                try:
                    reg.DeleteValue(clave, NOMBRE_VALOR)
                except FileNotFoundError:
                    pass
