"""Almacén de credenciales: Administrador de credenciales de Windows vía `ctypes`.

Sin `pywin32` (no viaja en el payload). Los secretos se guardan como UTF-16LE,
que es exactamente lo que escribía `win32cred` con un `str`: la clave de la
memoria a largo plazo ya guardada sigue leyéndose igual.

Nada de este módulo imprime, registra ni devuelve un secreto salvo `leer`, que
existe para quien lo va a usar (una llamada a la API del proveedor). `listar`
nunca incluye el valor.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

# CRED_MAX_CREDENTIAL_BLOB_SIZE: 5 * 512 bytes. En UTF-16 son 1280 caracteres.
MAX_BYTES_SECRETO = 2560
_ERROR_NOT_FOUND = 1168


class ErrorAlmacen(RuntimeError):
    """El almacén no pudo completar la operación. Nunca lleva el secreto."""


@dataclass(frozen=True)
class Entrada:
    target: str
    comentario: str
    escrita_en: str  # ISO 8601 UTC, vacío si el sistema no la dio


class Almacen(Protocol):
    def disponible(self) -> bool: ...
    def leer(self, target: str) -> str | None: ...
    def escribir(self, target: str, secreto: str, comentario: str = "") -> None: ...
    def borrar(self, target: str) -> bool: ...
    def listar(self, prefijo: str) -> list[Entrada]: ...


def _validar_secreto(secreto: str) -> None:
    if not isinstance(secreto, str) or not secreto:
        raise ErrorAlmacen("El valor a guardar está vacío.")
    if len(secreto.encode("utf-16-le")) > MAX_BYTES_SECRETO:
        raise ErrorAlmacen("El valor es demasiado largo para el Administrador de credenciales de Windows.")


class AlmacenMemoria:
    """Almacén en memoria para pruebas y para equipos sin Credential Manager."""

    def __init__(self) -> None:
        self._datos: dict[str, tuple[str, str, str]] = {}

    def disponible(self) -> bool:
        return True

    def leer(self, target: str) -> str | None:
        fila = self._datos.get(target)
        return fila[0] if fila else None

    def escribir(self, target: str, secreto: str, comentario: str = "") -> None:
        _validar_secreto(secreto)
        self._datos[target] = (secreto, comentario, datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def borrar(self, target: str) -> bool:
        return self._datos.pop(target, None) is not None

    def listar(self, prefijo: str) -> list[Entrada]:
        return [Entrada(t, f[1], f[2]) for t, f in sorted(self._datos.items()) if t.startswith(prefijo)]


class AlmacenWindows:
    """Credential Manager (CRED_TYPE_GENERIC, persistencia local al equipo y usuario)."""

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    def __init__(self) -> None:
        self._api = None

    # ------------------------------------------------------------------ ctypes
    def _cargar(self):
        if self._api is not None:
            return self._api
        if sys.platform != "win32":
            raise ErrorAlmacen("El Administrador de credenciales solo existe en Windows.")
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("bajo", wintypes.DWORD), ("alto", wintypes.DWORD)]

        class CREDENCIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME), ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        PCRED = ctypes.POINTER(CREDENCIAL)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCRED)]
        advapi.CredReadW.restype = wintypes.BOOL
        advapi.CredWriteW.argtypes = [PCRED, wintypes.DWORD]
        advapi.CredWriteW.restype = wintypes.BOOL
        advapi.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        advapi.CredDeleteW.restype = wintypes.BOOL
        advapi.CredEnumerateW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                          ctypes.POINTER(ctypes.POINTER(PCRED))]
        advapi.CredEnumerateW.restype = wintypes.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        advapi.CredFree.restype = None
        self._api = (ctypes, advapi, CREDENCIAL, PCRED)
        return self._api

    @staticmethod
    def _iso(ft) -> str:
        ticks = (ft.alto << 32) | ft.bajo
        if not ticks:
            return ""
        momento = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=ticks // 10)
        return momento.isoformat(timespec="seconds")

    # --------------------------------------------------------------- operaciones
    def disponible(self) -> bool:
        try:
            self._cargar()
            return True
        except (ErrorAlmacen, OSError):
            return False

    def leer(self, target: str) -> str | None:
        ctypes, advapi, _cred, pcred = self._cargar()
        puntero = pcred()
        if not advapi.CredReadW(target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(puntero)):
            codigo = ctypes.get_last_error()
            if codigo == _ERROR_NOT_FOUND:
                return None
            raise ErrorAlmacen(f"No se pudo leer del Administrador de credenciales (código {codigo}).")
        try:
            c = puntero.contents
            crudo = ctypes.string_at(c.CredentialBlob, c.CredentialBlobSize) if c.CredentialBlobSize else b""
        finally:
            advapi.CredFree(puntero)
        return crudo.decode("utf-16-le")

    def escribir(self, target: str, secreto: str, comentario: str = "") -> None:
        _validar_secreto(secreto)
        ctypes, advapi, cred_t, _pcred = self._cargar()
        blob = secreto.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        c = cred_t()
        c.Type = self.CRED_TYPE_GENERIC
        c.TargetName = target
        c.Comment = comentario or None
        c.CredentialBlobSize = len(blob)
        c.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
        c.Persist = self.CRED_PERSIST_LOCAL_MACHINE
        c.UserName = "D.A.R.K"
        try:
            if not advapi.CredWriteW(ctypes.byref(c), 0):
                raise ErrorAlmacen(
                    f"No se pudo guardar en el Administrador de credenciales (código {ctypes.get_last_error()}).")
        finally:
            # El buffer es nuestro: no dejar el secreto vivo más de lo necesario.
            ctypes.memset(buffer, 0, len(blob))

    def borrar(self, target: str) -> bool:
        ctypes, advapi, _cred, _pcred = self._cargar()
        if advapi.CredDeleteW(target, self.CRED_TYPE_GENERIC, 0):
            return True
        codigo = ctypes.get_last_error()
        if codigo == _ERROR_NOT_FOUND:
            return False
        raise ErrorAlmacen(f"No se pudo borrar del Administrador de credenciales (código {codigo}).")

    def listar(self, prefijo: str) -> list[Entrada]:
        ctypes, advapi, _cred, pcred = self._cargar()
        from ctypes import wintypes

        cuenta = wintypes.DWORD(0)
        lista = ctypes.POINTER(pcred)()
        if not advapi.CredEnumerateW(prefijo + "*", 0, ctypes.byref(cuenta), ctypes.byref(lista)):
            codigo = ctypes.get_last_error()
            if codigo == _ERROR_NOT_FOUND:
                return []
            raise ErrorAlmacen(f"No se pudo listar el Administrador de credenciales (código {codigo}).")
        try:
            filas = []
            for i in range(cuenta.value):
                c = lista[i].contents
                if c.Type != self.CRED_TYPE_GENERIC or not (c.TargetName or "").startswith(prefijo):
                    continue
                # Solo metadatos: el blob no se toca.
                filas.append(Entrada(c.TargetName, c.Comment or "", self._iso(c.LastWritten)))
            return sorted(filas, key=lambda e: e.target)
        finally:
            advapi.CredFree(lista)
