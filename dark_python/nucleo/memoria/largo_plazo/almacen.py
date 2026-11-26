"""Almacén de la memoria a largo plazo: SQLite cifrado con SQLCipher.

La base canónica vive junto al sistema que la posee
(``nucleo/memoria/largo_plazo/memoria.db``). Si la base existe pero no hay
clave ni copia de recuperación, abrir falla: nunca se genera una clave nueva
que deje los datos cifrados huérfanos.
"""
from __future__ import annotations

import os
from pathlib import Path

from utils.rutas_estado import resolver_ruta_estado

from .clave import obtener_clave

_ESQUEMA = Path(__file__).with_name("esquema.sql")


class AlmacenMemoria:
    def __init__(self, ruta_db: str | os.PathLike | None = None):
        self._ruta = Path(
            ruta_db
            if ruta_db is not None
            else resolver_ruta_estado("nucleo/memoria/largo_plazo", "memoria.db")
        )
        self._conn = None

    @property
    def ruta(self) -> Path:
        return self._ruta

    @property
    def conexion(self):
        if self._conn is None:
            raise RuntimeError("el almacén no está abierto")
        return self._conn

    def abrir(self) -> AlmacenMemoria:
        import sqlcipher3

        nueva = not self._ruta.exists() or self._ruta.stat().st_size == 0
        clave = obtener_clave(crear_si_falta=nueva)
        self._ruta.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlcipher3.connect(str(self._ruta))
        conn.row_factory = sqlcipher3.Row
        try:
            # Clave cruda de 32 bytes en hex; _validar garantiza que no hay
            # nada que interpolar fuera del literal x'...'.
            conn.execute(f"PRAGMA key = \"x'{clave}'\"")
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
            if nueva:
                conn.executescript(_ESQUEMA.read_text(encoding="utf-8"))
        except Exception:
            conn.close()
            raise
        self._conn = conn
        return self

    def cerrar(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> AlmacenMemoria:
        return self.abrir()

    def __exit__(self, *exc) -> None:
        self.cerrar()