"""Las notificaciones de Windows como fuente de avisos (WhatsApp, Discord…).

D.A.R.K. no se conecta a WhatsApp ni a Discord (nada de bots ni sesiones
propias): lee lo que esas apps ya le enseñan al usuario en forma de
notificación. Windows guarda cada notificación en una base SQLite del perfil
(`wpndatabase.db`), legible por el propio usuario; se abre en solo lectura y
se sondea cada pocos segundos buscando filas nuevas.

Al arrancar se salta lo que ya estaba: solo cuenta lo que llega después.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable

RUTA_BD = os.path.expandvars(
    r"%LOCALAPPDATA%\Microsoft\Windows\Notifications\wpndatabase.db"
)

#: Qué app es cada remitente de notificaciones. Se compara en minúsculas con
#: el identificador de la app y, para los navegadores, con el sitio de origen.
APPS = (
    ("whatsapp", "WhatsApp"),
    ("discord", "Discord"),
    ("telegram", "Telegram"),
    ("yourphone", "el teléfono"),       # Vínculo móvil: SMS (códigos)
    ("phonelink", "el teléfono"),
)


@dataclass(frozen=True)
class Notificacion:
    orden: int
    app: str            # nombre legible («WhatsApp»)
    fuente: str         # clave corta para el buzón («whatsapp»)
    titulo: str         # normalmente el remitente o el chat
    cuerpo: str


def textos_del_toast(payload: bytes | str) -> tuple[list[str], str]:
    """Los textos visibles de un toast y su atribución (el sitio, en los
    navegadores). Un XML roto da ([], "")."""
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8", "replace")
    try:
        raiz = ET.fromstring(payload)
    except ET.ParseError:
        return [], ""
    textos, atribucion = [], ""
    for t in raiz.iter("text"):
        valor = " ".join((t.text or "").split())
        if not valor:
            continue
        if t.get("placement") == "attribution":
            atribucion = valor
        else:
            textos.append(valor)
    return textos, atribucion


def app_de(handler: str, atribucion: str = "") -> tuple[str, str] | None:
    """(fuente, nombre) de una app vigilada, o None si no interesa."""
    donde = f"{handler} {atribucion}".lower()
    for clave, nombre in APPS:
        if clave in donde:
            fuente = "telefono" if nombre == "el teléfono" else clave
            return fuente, nombre
    return None


def leer_nuevas(con: sqlite3.Connection, desde: int) -> list[Notificacion]:
    """Los toasts de apps vigiladas con `Order` mayor que `desde`."""
    filas = con.execute(
        """SELECT n."Order", h.PrimaryId, n.Payload
           FROM Notification n JOIN NotificationHandler h ON h.RecordId = n.HandlerId
           WHERE n.Type = 'toast' AND n."Order" > ?
           ORDER BY 1""",
        (desde,),
    ).fetchall()
    nuevas = []
    for orden, handler, payload in filas:
        textos, atribucion = textos_del_toast(payload or b"")
        app = app_de(str(handler or ""), atribucion)
        if app is None or not textos:
            continue
        fuente, nombre = app
        titulo = textos[0]
        cuerpo = " ".join(textos[1:])
        nuevas.append(Notificacion(int(orden), nombre, fuente, titulo, cuerpo))
    return nuevas


def ultimo_orden(con: sqlite3.Connection) -> int:
    fila = con.execute('SELECT MAX("Order") FROM Notification').fetchone()
    return int(fila[0] or 0) if fila else 0


def abrir(ruta: str = RUTA_BD) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=2.0,
                           check_same_thread=False)


class VigilanteNotificaciones:
    """Sondea la base de notificaciones y entrega cada una nueva a `entregar`.

    `entregar` decide qué hacer con ella (clasificar y avisar); se le llama
    desde el hilo del vigilante, de una en una."""

    def __init__(self, entregar: Callable[[Notificacion], None], *,
                 ruta: str = RUTA_BD, cada_seg: float = 4.0, log=print):
        self._entregar = entregar
        self._ruta = ruta
        self._cada = cada_seg
        self._log = log
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None

    def iniciar(self) -> bool:
        if os.name != "nt" or not os.path.isfile(self._ruta):
            self._log("[Avisos] sin base de notificaciones de Windows: fuente apagada.")
            return False
        self._hilo = threading.Thread(target=self._bucle, daemon=True,
                                      name="avisos-notificaciones")
        self._hilo.start()
        return True

    def parar(self) -> None:
        self._parar.set()

    def _bucle(self) -> None:
        desde = None
        fallos = 0
        while not self._parar.is_set():
            try:
                con = abrir(self._ruta)
                try:
                    if desde is None:
                        desde = ultimo_orden(con)
                        self._log("[Avisos] vigilando las notificaciones de Windows.")
                    for n in leer_nuevas(con, desde):
                        desde = max(desde, n.orden)
                        try:
                            self._entregar(n)
                        except Exception as e:
                            self._log(f"[Avisos] no se pudo procesar una notificación: {e}")
                    # Las filas de apps no vigiladas también avanzan el cursor.
                    desde = max(desde, ultimo_orden(con))
                finally:
                    con.close()
                fallos = 0
            except sqlite3.Error as e:
                fallos += 1
                if fallos in (1, 10):
                    self._log(f"[Avisos] la base de notificaciones no responde: {e}")
            self._parar.wait(self._cada if fallos < 10 else 60.0)
