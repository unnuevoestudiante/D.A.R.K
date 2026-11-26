"""Gmail como fuente de avisos: correos nuevos que no son promoción.

El enlace con Google (OAuth, token, permisos) es de `conexiones/`; aquí solo
se vigila. Mientras el conector de Gmail esté conectado, cada minuto se
pregunta por los no leídos de la bandeja que Gmail no clasificó como
promociones, social o foros. Lo que ya estaba al arrancar no se avisa.
"""
from __future__ import annotations

import threading
from typing import Callable

from avisos.notificaciones_windows import Notificacion
from conexiones.google import CuentaGoogle, ErrorGoogle

URL_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
CONSULTA = ("in:inbox is:unread newer_than:2d "
            "-category:promotions -category:social -category:forums")


def remitente(cabecera_from: str) -> str:
    """«Ana Torres <ana@x.com>» → «Ana Torres»; sin nombre, la dirección."""
    texto = cabecera_from.strip()
    if "<" in texto:
        nombre = texto.split("<", 1)[0].strip().strip('"')
        if nombre:
            return nombre
        return texto.split("<", 1)[1].rstrip(">").strip()
    return texto


def como_notificacion(mensaje: dict) -> Notificacion:
    cabeceras = {h.get("name", "").lower(): h.get("value", "")
                 for h in mensaje.get("payload", {}).get("headers", [])}
    asunto = " ".join(cabeceras.get("subject", "").split())
    extracto = " ".join(str(mensaje.get("snippet", "")).split())
    return Notificacion(
        orden=0,
        app="Gmail",
        fuente="correo",
        titulo=remitente(cabeceras.get("from", "")) or "alguien",
        cuerpo=f"Asunto: {asunto}. {extracto}".strip(),
    )


class VigilanteGmail:
    def __init__(self, cuenta: CuentaGoogle, entregar: Callable[[Notificacion], None], *,
                 activo: Callable[[], bool],
                 al_perder_acceso: Callable[[str], None] | None = None,
                 cada_seg: float = 60.0, log=print):
        self._cuenta = cuenta
        self._entregar = entregar
        self._activo = activo
        self._al_perder = al_perder_acceso
        self._cada = cada_seg
        self._log = log
        self._parar = threading.Event()
        self._vistos: set[str] | None = None
        self._hilo: threading.Thread | None = None

    def iniciar(self) -> bool:
        if self._hilo is not None and self._hilo.is_alive():
            return True
        if not self._activo():
            self._log("[Avisos] Gmail no está conectado: fuente apagada.")
            return False
        self._parar.clear()
        self._vistos = None
        self._hilo = threading.Thread(target=self._bucle, daemon=True, name="avisos-gmail")
        self._hilo.start()
        return True

    def parar(self) -> None:
        self._parar.set()

    def _get(self, ruta: str, **params):
        return self._cuenta.pedir("GET", f"{URL_GMAIL}/{ruta}", params=params)

    def revisar(self) -> list[Notificacion]:
        """Una pasada: entrega los no leídos nuevos y los devuelve."""
        lista = self._get("messages", q=CONSULTA, maxResults=15)
        ids = [m["id"] for m in lista.get("messages", [])]
        if self._vistos is None:
            self._vistos = set(ids)   # lo que ya estaba no se avisa
            return []
        nuevas = []
        for mid in ids:
            if mid in self._vistos:
                continue
            self._vistos.add(mid)
            mensaje = self._get(f"messages/{mid}", format="metadata",
                                metadataHeaders=["From", "Subject"])
            n = como_notificacion(mensaje)
            nuevas.append(n)
            self._entregar(n)
        return nuevas

    def _bucle(self) -> None:
        self._log("[Avisos] vigilando Gmail.")
        while not self._parar.is_set():
            if not self._activo():
                self._log("[Avisos] Gmail desconectado: dejo de vigilar.")
                return
            try:
                self.revisar()
            except ErrorGoogle as e:
                self._log(f"[Avisos] Gmail: {e}")
                if self._al_perder is not None:
                    self._al_perder(str(e))
                return
            except Exception as e:
                self._log(f"[Avisos] Gmail no responde: {type(e).__name__}")
            self._parar.wait(self._cada)
