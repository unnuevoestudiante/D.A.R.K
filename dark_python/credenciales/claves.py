"""Claves de API de proveedores: destino `D.A.R.K/api/<id>` en el Administrador de credenciales.

Los archivos de configuración guardan solo el *id* de la credencial, nunca la
clave. Quien necesita la clave para llamar al proveedor usa `clave_de(id)`, que
nunca lanza: sin clave devuelve "" y el proveedor simplemente no está disponible.
"""
from __future__ import annotations

import re
import threading

from . import catalogo
from .almacen import Almacen, AlmacenWindows, ErrorAlmacen

PREFIJO = "D.A.R.K/api/"
MAX_LARGO_CLAVE = 1000

# Proveedores que el Centro ofrece de entrada (ver `catalogo.py`). Cualquier otro id válido también sirve.
PROVEEDORES_CONOCIDOS: tuple[tuple[str, str], ...] = tuple((p.id, p.nombre) for p in catalogo.TODOS)

_RE_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")


class ErrorClaves(ValueError):
    """Entrada inválida o almacén no disponible. El mensaje nunca contiene la clave."""


def id_valido(proveedor: object) -> str:
    texto = str(proveedor or "").strip().lower()
    if not _RE_ID.fullmatch(texto):
        raise ErrorClaves("El nombre del proveedor solo admite letras minúsculas, números, guion y guion bajo (máximo 40).")
    return texto


def id_desde_nombre(nombre: object) -> str:
    """Id de credencial a partir de un nombre libre («Groq 2» → «groq-2»)."""
    texto = re.sub(r"[^a-z0-9_-]+", "-", str(nombre or "").strip().lower()).strip("-_")
    return texto[:40] if _RE_ID.fullmatch(texto[:40] or "-") else ""


def _validar_valor(valor: object) -> str:
    texto = str(valor or "").strip()
    if not texto:
        raise ErrorClaves("Escribe la clave antes de guardar.")
    if len(texto) > MAX_LARGO_CLAVE:
        raise ErrorClaves("La clave es demasiado larga: revisa que hayas pegado solo la clave.")
    if any(c.isspace() or ord(c) < 32 for c in texto):
        raise ErrorClaves("La clave no puede tener espacios ni saltos de línea: revisa lo que pegaste.")
    return texto


class ServicioClaves:
    def __init__(self, almacen: Almacen) -> None:
        self._almacen = almacen

    def disponible(self) -> bool:
        return self._almacen.disponible()

    @staticmethod
    def validar(valor: object) -> str:
        """Comprueba que lo pegado parezca una clave (sin espacios ni saltos) y la devuelve limpia. No guarda nada."""
        return _validar_valor(valor)

    def _target(self, proveedor: object) -> str:
        return PREFIJO + id_valido(proveedor)

    def guardar(self, proveedor: object, valor: object, etiqueta: str = "") -> None:
        target, secreto = self._target(proveedor), _validar_valor(valor)
        try:
            self._almacen.escribir(target, secreto, str(etiqueta)[:80])
            # Verificar de vuelta: una escritura que no se puede leer no cuenta.
            if self._almacen.leer(target) != secreto:
                raise ErrorClaves("Windows no devolvió la clave que se acaba de guardar; no se considera guardada.")
        except ErrorAlmacen as error:
            raise ErrorClaves(str(error)) from None

    def leer(self, proveedor: object) -> str:
        try:
            return self._almacen.leer(self._target(proveedor)) or ""
        except (ErrorAlmacen, ErrorClaves):
            return ""

    def existe(self, proveedor: object) -> bool:
        return bool(self.leer(proveedor))

    def borrar(self, proveedor: object) -> bool:
        try:
            return self._almacen.borrar(self._target(proveedor))
        except ErrorAlmacen as error:
            raise ErrorClaves(str(error)) from None

    def listar(self) -> list[dict]:
        """Qué claves hay (id, fecha, etiqueta). Nunca el valor."""
        try:
            filas = self._almacen.listar(PREFIJO)
        except ErrorAlmacen:
            return []
        return [{"proveedor": f.target[len(PREFIJO):], "escritaEn": f.escrita_en, "etiqueta": f.comentario}
                for f in filas]


_lock = threading.Lock()
_servicio: ServicioClaves | None = None


def obtener() -> ServicioClaves:
    global _servicio
    with _lock:
        if _servicio is None:
            _servicio = ServicioClaves(AlmacenWindows())
        return _servicio


def fijar_servicio(servicio: ServicioClaves | None) -> None:
    """Sustituye el servicio (pruebas). `None` vuelve al del equipo."""
    global _servicio
    with _lock:
        _servicio = servicio


def clave_de(credencial: object) -> str:
    """Clave guardada para ese id, o "" si no hay o el almacén no responde."""
    try:
        return obtener().leer(credencial)
    except Exception:
        return ""
