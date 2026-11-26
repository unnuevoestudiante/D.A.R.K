"""El registro de conectores: qué servicios hay y en qué estado está cada uno.

Un conector declara su nombre, los permisos de Google que necesita y cómo se
le llama al hablar. Quien conecta o desconecta (la voz, el Centro) pasa por
aquí; quien usa el servicio (avisos, herramientas) pregunta `activo()`.

Estados de un conector:
  * ``sin_cliente``   — falta `config/google_cliente.json` (lo pone el desarrollador).
  * ``desconectado``  — nunca se conectó o se desconectó.
  * ``falta_permiso`` — está activo pero Google ya no tiene todos sus permisos
    (p. ej. una versión nueva de D.A.R.K. pide uno más): hay que reconectar.
  * ``conectado``
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Iterable

from conexiones.google import CuentaGoogle, ErrorGoogle

G = "https://www.googleapis.com/auth/"


@dataclass(frozen=True)
class Conector:
    id: str
    nombre: str
    #: Para decirlo: «su Gmail», «su calendario».
    articulo: str
    alcances: tuple[str, ...]
    #: Palabras con las que el usuario lo nombra (sin tildes, minúsculas).
    sinonimos: tuple[str, ...]
    descripcion: str


CONECTORES: tuple[Conector, ...] = (
    Conector(
        "gmail", "Gmail", "su Gmail",
        (G + "gmail.readonly", G + "gmail.send"),
        ("gmail", "correo", "correos", "email", "emails", "mail", "mails", "bandeja"),
        "Avisa de los correos importantes, los busca y lee, y responde con su permiso.",
    ),
    Conector(
        "calendar", "Google Calendar", "su calendario",
        (G + "calendar.events",),
        ("calendar", "calendario", "calendarios", "agenda", "eventos", "citas"),
        "Su agenda: qué tiene hoy, avisos antes de cada evento y crear eventos con su permiso.",
    ),
    Conector(
        "drive", "Google Drive", "su Drive",
        (G + "drive.readonly",),
        ("drive", "documentos de google", "archivos de google", "nube"),
        "Busca y abre sus documentos de Google Drive.",
    ),
    Conector(
        "contactos", "Contactos de Google", "sus contactos",
        (G + "contacts.readonly", G + "contacts.other.readonly"),
        ("contactos", "contacto", "agenda de contactos", "personas"),
        "Sabe quién es quién para nombrarlos en los avisos y escribirles.",
    ),
)
POR_ID = {c.id: c for c in CONECTORES}


def _plano(texto: str) -> str:
    texto = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def conectores_en(texto: str) -> list[Conector]:
    """Los conectores que nombra una frase («conecta mi correo y mi agenda»)."""
    plano = _plano(texto)
    hallados = []
    for c in CONECTORES:
        if any(re.search(rf"\b{re.escape(s)}\b", plano) for s in c.sinonimos):
            hallados.append(c)
    # «agenda de contactos» es Contactos, no Calendar.
    if POR_ID["contactos"] in hallados and "agenda de contactos" in plano:
        hallados = [c for c in hallados if c.id != "calendar"]
    return hallados


def lista_hablada(nombres: list[str]) -> str:
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


class Registro:
    """Estado y alta/baja de los conectores sobre una cuenta de Google."""

    def __init__(self, cuenta: CuentaGoogle | None = None):
        self.cuenta = cuenta or CuentaGoogle()
        #: Quien quiera enterarse (el vigilante de Gmail, el Centro).
        self._oyentes: list[Callable[[str, bool], None]] = []

    def al_cambiar(self, oyente: Callable[[str, bool], None]) -> None:
        self._oyentes.append(oyente)

    def _avisar(self, servicio: str, activo: bool) -> None:
        for oyente in list(self._oyentes):
            try:
                oyente(servicio, activo)
            except Exception as e:
                print(f"[Conexiones] oyente falló: {e}")

    def estado(self, servicio: str) -> str:
        c = POR_ID[servicio]
        if not self.cuenta.hay_cliente():
            return "sin_cliente"
        if servicio not in self.cuenta.estado()["activos"]:
            return "desconectado"
        if not self.cuenta.tiene(c.alcances):
            return "falta_permiso"
        return "conectado"

    def activo(self, servicio: str) -> bool:
        return self.estado(servicio) == "conectado"

    def resumen(self) -> list[dict]:
        """Para el Centro y para decir «¿qué tengo conectado?»."""
        cuenta = self.cuenta.estado()["cuenta"]
        return [{"id": c.id, "nombre": c.nombre, "descripcion": c.descripcion,
                 "estado": self.estado(c.id), "cuenta": cuenta} for c in CONECTORES]

    def conectar(self, servicios: Iterable[str]) -> list[str]:
        """Pide en una sola pantalla de Google los permisos de esos servicios.
        Devuelve los que quedaron conectados. Lanza ErrorGoogle."""
        servicios = [s for s in servicios if s in POR_ID]
        pendientes = [s for s in servicios if not self.cuenta.tiene(POR_ID[s].alcances)]
        if pendientes:
            alcances = [a for s in pendientes for a in POR_ID[s].alcances]
            self.cuenta.autorizar(alcances)
        for s in servicios:
            self.cuenta.activar(s, True)
            self._avisar(s, True)
        return servicios

    def desconectar(self, servicios: Iterable[str]) -> bool:
        """Apaga esos servicios. Si no queda ninguno, revoca el permiso en
        Google. Devuelve si se revocó."""
        for s in servicios:
            if s in POR_ID:
                self.cuenta.activar(s, False)
                self._avisar(s, False)
        if not self.cuenta.estado()["activos"] and self.cuenta.enlazada():
            self.cuenta.revocar()
            return True
        return False

    def frase_estado(self) -> str:
        """«Tiene conectados Gmail y Google Calendar. Sin conectar: …»."""
        if not self.cuenta.hay_cliente():
            return ("Las conexiones aún no están listas: falta el cliente de Google "
                    "en la carpeta config.")
        conectados = [c.nombre for c in CONECTORES if self.estado(c.id) == "conectado"]
        rotos = [c.nombre for c in CONECTORES if self.estado(c.id) == "falta_permiso"]
        libres = [c.nombre for c in CONECTORES if self.estado(c.id) == "desconectado"]
        partes = []
        if conectados:
            cuenta = self.cuenta.estado()["cuenta"]
            con = f" con {cuenta}" if cuenta else ""
            partes.append(f"Tiene conectado{'s' if len(conectados) > 1 else ''} "
                          f"{lista_hablada(conectados)}{con}.")
        else:
            partes.append("No tiene nada conectado todavía.")
        if rotos:
            partes.append(f"{lista_hablada(rotos)} necesita{'n' if len(rotos) > 1 else ''} "
                          "que lo vuelva a conectar.")
        if libres and conectados:
            partes.append(f"Sin conectar: {lista_hablada(libres)}.")
        return " ".join(partes)


__all__ = ["CONECTORES", "POR_ID", "Conector", "ErrorGoogle", "Registro",
           "conectores_en", "lista_hablada"]
