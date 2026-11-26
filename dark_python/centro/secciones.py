"""Secciones del Centro hechas de **bloques** (párrafos, tablas, interruptores, listas, acciones).

Las bibliotecas y las claves tienen su propia pantalla porque su flujo es complejo. El resto
de secciones (Memoria, Privacidad, Sistema, los ajustes de voz de entrada y de cámara…) son
ajustes y datos: en lugar de una pantalla a medida cada una, devuelven una lista de bloques y
la interfaz los pinta todos con el mismo componente. La sección decide **qué** mostrar y qué
puede hacer la persona; la interfaz no sabe nada de memoria ni de privacidad.

Reglas:
  * Los datos que se devuelven son para mostrar: **nunca** un secreto ni un dato biométrico.
  * Una acción peligrosa (`peligro=True`) la confirma la persona en la pantalla, pero quien la
    ejecuta (`operar`) la vuelve a exigir: un mensaje del WebSocket no es una confirmación.
  * `operar` devuelve el mensaje que se muestra al terminar bien, o lanza `ErrorSeccion`.
"""
from __future__ import annotations

from typing import Any, Protocol


class ErrorSeccion(Exception):
    """Fallo esperable con un mensaje legible."""

    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


class SeccionBloques(Protocol):
    #: Identificador de la sección en el Centro (p. ej. «memoria»).
    id: str
    titulo: str
    #: Lo que D.A.R.K. dice al abrirla (primera persona, breve).
    guia: str
    #: Las operaciones de esta sección empiezan por «<prefijo>_».
    prefijo: str

    def bloques(self) -> list[dict[str, Any]]: ...
    def operar(self, operacion: str, datos: dict) -> str | None: ...
    def limpiar(self) -> None: ...


# ------------------------------------------------------------------ constructores
def parrafo(texto: str, nivel: str = "info") -> dict[str, Any]:
    return {"tipo": "parrafo", "texto": texto, "nivel": nivel if nivel in ("info", "aviso") else "info"}


def tabla(titulo: str, columnas: list[str], filas: list[list[str]]) -> dict[str, Any]:
    return {"tipo": "tabla", "titulo": titulo, "columnas": list(columnas),
            "filas": [[str(c) for c in fila] for fila in filas]}


def interruptor(etiqueta: str, valor: bool, op: str, ayuda: str = "", campo: str = "activa") -> dict[str, Any]:
    return {"tipo": "interruptor", "etiqueta": etiqueta, "ayuda": ayuda, "valor": bool(valor),
            "op": op, "campo": campo}


def accion(etiqueta: str, op: str, datos: dict | None = None, *, confirmar: str | None = None,
           peligro: bool = False, pide_texto: dict | None = None) -> dict[str, Any]:
    """Un botón. `pide_texto={"campo", "etiqueta", "oculto", "minimo"}` pide un texto antes de enviarlo."""
    return {"etiqueta": etiqueta, "op": op, "datos": dict(datos or {}), "confirmar": confirmar,
            "peligro": bool(peligro), "pideTexto": pide_texto}


def lista(titulo: str, items: list[dict[str, Any]], vacio: str = "") -> dict[str, Any]:
    return {"tipo": "lista", "titulo": titulo, "vacio": vacio, "items": items}


def item(titulo: str, detalle: str = "", acciones: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"titulo": titulo, "detalle": detalle, "acciones": acciones or []}


def acciones(*botones: dict[str, Any]) -> dict[str, Any]:
    return {"tipo": "acciones", "acciones": list(botones)}
