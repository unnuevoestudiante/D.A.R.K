"""Migración consentida de `online_coder.json` al Administrador de credenciales.

Pasos (los decide la persona, ninguno ocurre solo):
  1. `analizar`: dice qué claves hay en el archivo, **sin leer su valor hacia la interfaz**.
  2. `importar`: las guarda en el almacén y comprueba que se leen de vuelta.
  3. Solo si se pidió `borrar_origen` y todo se verificó, quita `api_key` del archivo y deja
     en su lugar `credencial: <id>`. El archivo se reescribe de forma atómica.

`DARK_CHAT_API_KEY` es un opt-in por entorno de quien lo puso: se informa, pero no se toca.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .claves import ErrorClaves, ServicioClaves, id_desde_nombre, id_valido


def _leer(ruta: Path) -> dict[str, Any]:
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        raise ErrorClaves(f"No se pudo leer {ruta.name}: {type(error).__name__}.") from None
    if not isinstance(datos, dict):
        raise ErrorClaves(f"{ruta.name} no tiene el formato esperado.")
    return datos


def _entradas_con_clave(datos: dict[str, Any]) -> list[tuple[int, str, dict[str, Any]]]:
    """(posición, id de credencial, entrada) de cada proveedor que trae `api_key` en claro."""
    usados: set[str] = set()
    salida = []
    for i, entrada in enumerate(datos.get("providers") or []):
        if not isinstance(entrada, dict) or not str(entrada.get("api_key") or "").strip():
            continue
        base = ""
        if entrada.get("credencial"):
            try:
                base = id_valido(entrada["credencial"])
            except ErrorClaves:
                base = ""
        base = base or id_desde_nombre(entrada.get("name")) or id_desde_nombre(entrada.get("provider")) or f"proveedor-{i + 1}"
        identificador, n = base, 2
        while identificador in usados:
            identificador, n = f"{base}-{n}"[:40], n + 1
        usados.add(identificador)
        salida.append((i, identificador, entrada))
    return salida


def analizar(ruta: Path, servicio: ServicioClaves) -> dict[str, Any]:
    """Qué se podría migrar. No incluye ningún valor de clave."""
    entradas = []
    existe = ruta.is_file()
    if existe:
        for _pos, identificador, entrada in _entradas_con_clave(_leer(ruta)):
            entradas.append({
                "id": identificador,
                "nombre": str(entrada.get("name") or identificador),
                "proveedor": str(entrada.get("provider") or ""),
                "yaGuardada": servicio.existe(identificador),
            })
    return {
        "archivo": ruta.name, "existe": existe, "entradas": entradas,
        "entorno": bool(os.environ.get("DARK_CHAT_API_KEY", "").strip()),
    }


def importar(ruta: Path, servicio: ServicioClaves, *, borrar_origen: bool = False,
             reemplazar: bool = False) -> dict[str, Any]:
    datos = _leer(ruta)
    candidatas = _entradas_con_clave(datos)
    if not candidatas:
        raise ErrorClaves("No hay claves en el archivo que migrar.")
    importadas, omitidas = [], []
    for _pos, identificador, entrada in candidatas:
        if servicio.existe(identificador) and not reemplazar:
            omitidas.append(identificador)
            continue
        servicio.guardar(identificador, entrada["api_key"], etiqueta="importada de online_coder.json")
        importadas.append(identificador)
    verificadas = set(importadas) | set(omitidas)
    origen_borrado = False
    if borrar_origen and all(servicio.existe(i) for _p, i, _e in candidatas):
        for pos, identificador, _entrada in candidatas:
            proveedor = datos["providers"][pos]
            proveedor.pop("api_key", None)
            proveedor["credencial"] = identificador
        _escribir_atomico(ruta, datos)
        origen_borrado = True
    return {"importadas": importadas, "omitidas": omitidas, "origenBorrado": origen_borrado,
            "verificadas": len(verificadas)}


def _escribir_atomico(ruta: Path, datos: dict[str, Any]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporal = tempfile.mkstemp(dir=ruta.parent, prefix=ruta.name, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, indent=2, ensure_ascii=False)
            archivo.write("\n")
        os.replace(temporal, ruta)
    except BaseException:
        try:
            os.unlink(temporal)
        except OSError:
            pass
        raise
