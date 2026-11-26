"""Clave de la memoria a largo plazo: almacén seguro de Windows y recuperación.

La clave vive en el Credential Manager (vía ctypes, sin pywin32; mismo formato UTF-16LE).
La copia de recuperación es un archivo exportable cifrado con una frase de
paso (AES-256-GCM, clave derivada con scrypt); restaurarla devuelve la clave
al almacén seguro. La clave nunca se imprime ni se registra en logs.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
from pathlib import Path

TARGET_CREDENCIAL = "D.A.R.K/memoria_largo_plazo"
_RE_CLAVE = re.compile(r"[0-9a-f]{64}")
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


class ErrorClave(RuntimeError):
    """No hay clave disponible y crear una nueva dejaría datos huérfanos."""


def _validar(clave: str) -> str:
    if not _RE_CLAVE.fullmatch(clave):
        raise ValueError("clave inválida: se esperan 64 caracteres hexadecimales en minúsculas")
    return clave


def _leer_almacen() -> str | None:
    from credenciales import AlmacenWindows

    return AlmacenWindows().leer(TARGET_CREDENCIAL)


def _escribir_almacen(clave: str) -> None:
    from credenciales import AlmacenWindows

    AlmacenWindows().escribir(TARGET_CREDENCIAL, clave, "memoria a largo plazo")


def obtener_clave(*, crear_si_falta: bool) -> str:
    """Clave del almacén seguro; solo genera una si no hay base que proteger."""
    clave = _leer_almacen()
    if clave is not None:
        return _validar(clave)
    if not crear_si_falta:
        raise ErrorClave(
            "la base existe pero no hay clave en el almacén seguro; "
            "restaura la copia con: python -m nucleo.memoria.largo_plazo.clave restaurar RUTA"
        )
    clave = secrets.token_hex(32)
    _escribir_almacen(clave)
    return clave


def _derivar(frase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salt, length=32, n=n, r=r, p=p).derive(frase.encode("utf-8"))


def exportar_recuperacion(ruta: str | os.PathLike, frase: str) -> Path:
    """Copia de la clave cifrada con la frase de paso; no sobrescribe otra copia."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not frase:
        raise ValueError("la frase de paso no puede estar vacía")
    clave = _leer_almacen()
    if clave is None:
        raise ErrorClave("no hay clave que exportar")
    destino = Path(ruta)
    if destino.exists():
        raise FileExistsError(f"ya existe una copia en {destino}; no se sobrescribe")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    aes = AESGCM(_derivar(frase, salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P))
    cifrado = aes.encrypt(nonce, _validar(clave).encode("ascii"), None)
    datos = {
        "version": 1,
        "kdf": {"nombre": "scrypt", "n": _SCRYPT_N, "r": _SCRYPT_R, "p": _SCRYPT_P},
        "salt": salt.hex(),
        "nonce": nonce.hex(),
        "cifrado": base64.b64encode(cifrado).decode("ascii"),
    }
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(datos, indent=2) + "\n", encoding="ascii")
    return destino


def restaurar_desde_archivo(ruta: str | os.PathLike, frase: str) -> None:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    try:
        datos = json.loads(Path(ruta).read_text(encoding="ascii"))
        kdf = datos["kdf"]
        aes = AESGCM(
            _derivar(frase, bytes.fromhex(datos["salt"]), kdf["n"], kdf["r"], kdf["p"])
        )
        clave = aes.decrypt(
            bytes.fromhex(datos["nonce"]), base64.b64decode(datos["cifrado"]), None
        ).decode("ascii")
    except (InvalidTag, KeyError, TypeError, ValueError) as e:
        raise ErrorClave("frase incorrecta o archivo de recuperación dañado") from e
    _validar(clave)
    _escribir_almacen(clave)


def _main() -> int:
    import argparse
    import getpass

    p = argparse.ArgumentParser(description="Clave de la memoria a largo plazo de D.A.R.K.")
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("estado", help="dice si hay clave en el almacén seguro (no la imprime)")
    exp = sub.add_parser("exportar", help="escribe la copia de recuperación cifrada con frase")
    exp.add_argument("archivo")
    res = sub.add_parser("restaurar", help="devuelve al almacén seguro la clave de un archivo")
    res.add_argument("archivo")
    args = p.parse_args()
    try:
        if args.orden == "estado":
            print(
                "clave presente en el almacén seguro"
                if _leer_almacen() is not None
                else "sin clave"
            )
        elif args.orden == "exportar":
            frase = getpass.getpass("Frase de paso para la copia: ")
            if frase != getpass.getpass("Repítela: "):
                print("las frases no coinciden")
                return 1
            print(f"copia cifrada escrita en {exportar_recuperacion(args.archivo, frase)}")
        else:
            restaurar_desde_archivo(args.archivo, getpass.getpass("Frase de paso: "))
            print("clave restaurada en el almacén seguro")
    except (ErrorClave, ValueError, FileExistsError) as e:
        print(f"error: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())