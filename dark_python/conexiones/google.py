"""La cuenta de Google: un solo enlace, permisos que se suman por servicio.

OAuth de «app de escritorio» con PKCE y redirección a 127.0.0.1, con
autorización incremental (`include_granted_scopes`): conectar Calendar
después de Gmail pide solo el permiso de Calendar y Google devuelve un
token que vale para los dos.

* El cliente OAuth (client_id/secret) lo crea una vez el desarrollador y viaja
  con D.A.R.K. en `config/google_cliente.json`. En una app de escritorio ese
  «secreto» no es confidencial (lo dice Google); lo que sí lo es, el refresh
  token, va al Administrador de credenciales de Windows.
* Lo que no es secreto —qué permisos se concedieron, con qué cuenta, qué
  servicios están activos— se guarda en `config/conexiones.json`.

Google no deja retirar un permiso suelto: desconectar un servicio lo apaga en
D.A.R.K.; al desconectar el último se revoca el token entero en Google.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from typing import Callable, Iterable

import requests

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA_CLIENTE = os.path.join(RAIZ, "config", "google_cliente.json")
#: Nombre del primer borrador (solo Gmail); se sigue aceptando.
RUTA_CLIENTE_ANTIGUA = os.path.join(RAIZ, "config", "gmail_cliente.json")
RUTA_ESTADO = os.path.join(RAIZ, "config", "conexiones.json")
CREDENCIAL = "google"

URL_AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
URL_TOKEN = "https://oauth2.googleapis.com/token"
URL_REVOCAR = "https://oauth2.googleapis.com/revoke"
#: Siempre se piden: dan el correo de la cuenta para enseñarla en el Centro.
ALCANCES_BASE = ("openid", "email")


class ErrorGoogle(RuntimeError):
    """Algo que el usuario puede arreglar; el mensaje se puede decir en voz alta."""


def leer_cliente(ruta: str | None = None) -> dict:
    """client_id y client_secret del JSON que descarga Google Cloud."""
    rutas = [ruta] if ruta else [RUTA_CLIENTE, RUTA_CLIENTE_ANTIGUA]
    existente = next((r for r in rutas if os.path.isfile(r)), None)
    if existente is None:
        raise ErrorGoogle(
            "Falta el cliente de Google: deje el archivo google_cliente.json en la carpeta config.")
    with open(existente, encoding="utf-8") as f:
        data = json.load(f)
    datos = data.get("installed") or data.get("web") or data
    if not datos.get("client_id") or not datos.get("client_secret"):
        raise ErrorGoogle("El archivo del cliente de Google no tiene client_id y client_secret.")
    return {"client_id": datos["client_id"], "client_secret": datos["client_secret"]}


def _pkce() -> tuple[str, str]:
    verificador = secrets.token_urlsafe(64)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    return verificador, reto.decode().rstrip("=")


def url_autorizacion(client_id: str, redirect: str, alcances: Iterable[str],
                     reto: str, estado: str, pista: str = "") -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect,
        "response_type": "code",
        "scope": " ".join(sorted(set(ALCANCES_BASE) | set(alcances))),
        "code_challenge": reto,
        "code_challenge_method": "S256",
        "state": estado,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
    }
    if pista:
        params["login_hint"] = pista   # la misma cuenta que ya está conectada
    return URL_AUTORIZAR + "?" + urllib.parse.urlencode(params)


def correo_del_id_token(id_token: str) -> str:
    """El `email` del id_token (solo para mostrarlo; no se usa para autorizar)."""
    try:
        carga = id_token.split(".")[1]
        carga += "=" * (-len(carga) % 4)
        return str(json.loads(base64.urlsafe_b64decode(carga)).get("email") or "")
    except Exception:
        return ""


def _esperar_codigo(servidor: http.server.HTTPServer, estado: str, limite_seg: float) -> str:
    """Atiende la redirección de Google en 127.0.0.1 y devuelve el `code`."""
    resultado: dict[str, str] = {}

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (nombre de la API de http.server)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == estado:
                if "code" in q:
                    resultado["code"] = q["code"][0]
                else:
                    resultado["error"] = q.get("error", ["denegado"])[0]
            ok = "code" in resultado
            cuerpo = ("Listo: D.A.R.K. ya tiene el permiso. Puede cerrar esta pestaña."
                      if ok else "No se concedió el permiso. Puede cerrar esta pestaña.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<p style='font:16px sans-serif'>{cuerpo}</p>".encode())

        def log_message(self, *args):
            pass

    servidor.RequestHandlerClass = Manejador
    servidor.timeout = 1.0
    fin = time.monotonic() + limite_seg
    while time.monotonic() < fin and not resultado:
        servidor.handle_request()
    if "code" in resultado:
        return resultado["code"]
    if "error" in resultado:
        raise ErrorGoogle("No se concedió el permiso en Google.")
    raise ErrorGoogle("Se acabó el tiempo para autorizar en Google.")


class EstadoGoogle:
    """Lo no secreto de la conexión, en `config/conexiones.json`."""

    def __init__(self, ruta: str = RUTA_ESTADO):
        self._ruta = ruta
        self._lock = threading.Lock()

    def leer(self) -> dict:
        try:
            with open(self._ruta, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {}
        g = data.get("google") if isinstance(data.get("google"), dict) else {}
        return {
            "cuenta": str(g.get("cuenta") or ""),
            "alcances": sorted(set(g.get("alcances") or [])),
            "activos": sorted(set(g.get("activos") or [])),
        }

    def guardar(self, **cambios) -> dict:
        with self._lock:
            try:
                with open(self._ruta, encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                data = {}
            actual = self.leer()
            actual.update(cambios)
            data["google"] = actual
            os.makedirs(os.path.dirname(self._ruta) or ".", exist_ok=True)
            tmp = self._ruta + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._ruta)
            return actual


class CuentaGoogle:
    """El enlace con la cuenta de Google del usuario."""

    def __init__(self, *, http=None, claves=None, estado: EstadoGoogle | None = None,
                 ruta_cliente: str | None = None,
                 abrir_navegador: Callable[[str], object] = webbrowser.open):
        self._http = http or requests.Session()
        self._claves = claves
        self._estado = estado or EstadoGoogle()
        self._ruta_cliente = ruta_cliente
        self._abrir = abrir_navegador
        self._token: str | None = None
        self._expira = 0.0
        self._lock = threading.Lock()

    # -- almacén -------------------------------------------------------
    def _almacen(self):
        if self._claves is None:
            from credenciales import claves

            self._claves = claves.obtener()
        return self._claves

    def _refresh(self) -> str:
        try:
            return self._almacen().leer(CREDENCIAL) or ""
        except Exception:
            return ""

    # -- consulta ------------------------------------------------------
    def hay_cliente(self) -> bool:
        try:
            leer_cliente(self._ruta_cliente)
            return True
        except Exception:
            return False

    def enlazada(self) -> bool:
        return bool(self._refresh())

    def estado(self) -> dict:
        return self._estado.leer()

    def tiene(self, alcances: Iterable[str]) -> bool:
        concedidos = set(self.estado()["alcances"])
        return self.enlazada() and set(alcances) <= concedidos

    # -- autorizar -----------------------------------------------------
    def autorizar(self, alcances: Iterable[str], limite_seg: float = 300.0) -> dict:
        """Pide (sumando a lo ya concedido) los `alcances` en el navegador."""
        cliente = leer_cliente(self._ruta_cliente)
        servidor = http.server.HTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        try:
            redirect = f"http://127.0.0.1:{servidor.server_address[1]}"
            verificador, reto = _pkce()
            estado = secrets.token_urlsafe(16)
            self._abrir(url_autorizacion(cliente["client_id"], redirect, alcances, reto,
                                         estado, pista=self.estado()["cuenta"]))
            codigo = _esperar_codigo(servidor, estado, limite_seg)
        finally:
            servidor.server_close()
        r = self._http.post(URL_TOKEN, data={
            "client_id": cliente["client_id"],
            "client_secret": cliente["client_secret"],
            "code": codigo,
            "code_verifier": verificador,
            "grant_type": "authorization_code",
            "redirect_uri": redirect,
        }, timeout=20)
        data = r.json() if r.status_code == 200 else {}
        refresh = data.get("refresh_token") or self._refresh()
        if not data.get("access_token") or not refresh:
            raise ErrorGoogle("Google no devolvió el permiso; inténtelo de nuevo.")
        self._almacen().guardar(CREDENCIAL, refresh, "Cuenta de Google")
        concedidos = set(str(data.get("scope") or "").split()) | set(self.estado()["alcances"])
        cuenta = correo_del_id_token(str(data.get("id_token") or "")) or self.estado()["cuenta"]
        with self._lock:
            self._token = data["access_token"]
            self._expira = time.monotonic() + float(data.get("expires_in", 0)) - 60
        faltan = set(alcances) - concedidos
        if faltan:
            # El usuario desmarcó alguna casilla en la pantalla de Google.
            self._estado.guardar(cuenta=cuenta, alcances=sorted(concedidos))
            raise ErrorGoogle("Faltó marcar alguno de los permisos en la pantalla de Google.")
        return self._estado.guardar(cuenta=cuenta, alcances=sorted(concedidos))

    def activar(self, servicio: str, activo: bool) -> dict:
        activos = set(self.estado()["activos"])
        (activos.add if activo else activos.discard)(servicio)
        return self._estado.guardar(activos=sorted(activos))

    def revocar(self) -> None:
        """Retira el permiso entero en Google y olvida el enlace."""
        refresh = self._refresh()
        if refresh:
            try:
                self._http.post(URL_REVOCAR, data={"token": refresh}, timeout=20)
            except Exception:
                pass   # sin red: igualmente se olvida aquí
            try:
                self._almacen().borrar(CREDENCIAL)
            except Exception:
                pass
        with self._lock:
            self._token = None
        self._estado.guardar(cuenta="", alcances=[], activos=[])

    # -- llamar a las API ----------------------------------------------
    def token(self) -> str:
        """Un access token vigente (renueva con el refresh token)."""
        with self._lock:
            if self._token and time.monotonic() < self._expira:
                return self._token
        refresh = self._refresh()
        if not refresh:
            raise ErrorGoogle("La cuenta de Google no está conectada.")
        cliente = leer_cliente(self._ruta_cliente)
        r = self._http.post(URL_TOKEN, data={
            "client_id": cliente["client_id"],
            "client_secret": cliente["client_secret"],
            "refresh_token": refresh,
            "grant_type": "refresh_token",
        }, timeout=20)
        if r.status_code in (400, 401):
            # invalid_grant: el usuario retiró el permiso o caducó.
            raise ErrorGoogle("Perdí el acceso a su cuenta de Google; vuelva a conectarla.")
        r.raise_for_status()
        data = r.json()
        with self._lock:
            self._token = data["access_token"]
            self._expira = time.monotonic() + float(data.get("expires_in", 3600)) - 60
            return self._token

    def pedir(self, metodo: str, url: str, **kwargs):
        """Una llamada a una API de Google con el token (reintenta un 401)."""
        for intento in (0, 1):
            r = self._http.request(metodo, url, timeout=20, headers={
                "Authorization": f"Bearer {self.token()}"}, **kwargs)
            if r.status_code == 401 and intento == 0:
                with self._lock:
                    self._token = None
                continue
            if r.status_code == 403:
                raise ErrorGoogle("Google rechazó la petición: falta un permiso o la API no está habilitada.")
            r.raise_for_status()
            return r.json() if r.content else {}
        return {}
