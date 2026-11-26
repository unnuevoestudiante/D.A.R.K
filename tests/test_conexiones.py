"""Conexiones: la cuenta de Google con permisos por servicio y el registro."""
import json
import pathlib
import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
from types import SimpleNamespace

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from conexiones.google import (  # noqa: E402
    CREDENCIAL,
    CuentaGoogle,
    ErrorGoogle,
    EstadoGoogle,
    correo_del_id_token,
    leer_cliente,
)
from conexiones.registro import POR_ID, Registro, conectores_en  # noqa: E402

G = "https://www.googleapis.com/auth/"


class ClavesFalsas:
    def __init__(self, valor=""):
        self.datos = {CREDENCIAL: valor} if valor else {}

    def leer(self, ident):
        return self.datos.get(ident, "")

    def guardar(self, ident, valor, etiqueta=""):
        self.datos[ident] = valor

    def borrar(self, ident):
        return self.datos.pop(ident, None) is not None


def respuesta(codigo=200, datos=None):
    return SimpleNamespace(status_code=codigo, json=lambda: datos or {},
                           raise_for_status=lambda: None, content=b"x")


def id_token(email):
    import base64
    carga = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"cabecera.{carga}.firma"


class HttpFalso:
    def __init__(self, alcances_concedidos):
        self.posts = []
        self.alcances = alcances_concedidos

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, data))
        if url.endswith("/revoke"):
            return respuesta(200)
        return respuesta(200, {"access_token": "acc", "expires_in": 3600,
                               "refresh_token": "ref", "scope": " ".join(self.alcances),
                               "id_token": id_token("yo@gmail.com")})


def navegador_que_acepta(test, urls):
    def abrir(url):
        urls.append(url)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        vuelta = (q["redirect_uri"][0] + "/?" + urllib.parse.urlencode(
            {"code": "abc", "state": q["state"][0]}))
        threading.Thread(target=lambda: urllib.request.urlopen(vuelta, timeout=5).read(),
                         daemon=True).start()
    return abrir


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = pathlib.Path(self.tmp.name)
        self.cliente = d / "google_cliente.json"
        self.cliente.write_text(json.dumps({"installed": {"client_id": "cid",
                                                          "client_secret": "sec"}}))
        self.estado = EstadoGoogle(str(d / "conexiones.json"))
        self.urls = []

    def tearDown(self):
        self.tmp.cleanup()

    def cuenta(self, http, claves=None):
        return CuentaGoogle(http=http, claves=claves or ClavesFalsas(), estado=self.estado,
                            ruta_cliente=str(self.cliente),
                            abrir_navegador=navegador_que_acepta(self, self.urls))


class PruebaCuenta(Base):
    def test_sin_cliente_se_explica(self):
        with self.assertRaises(ErrorGoogle):
            leer_cliente("no/existe.json")

    def test_autorizar_suma_permisos_y_guarda_la_cuenta(self):
        claves = ClavesFalsas()
        http = HttpFalso([G + "gmail.readonly", G + "gmail.send", "openid", "email"])
        cuenta = self.cuenta(http, claves)
        cuenta.autorizar([G + "gmail.readonly", G + "gmail.send"], limite_seg=10)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[0]).query)
        self.assertEqual(q["include_granted_scopes"], ["true"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(claves.datos[CREDENCIAL], "ref")
        self.assertEqual(cuenta.estado()["cuenta"], "yo@gmail.com")
        self.assertTrue(cuenta.tiene([G + "gmail.readonly"]))
        self.assertFalse(cuenta.tiene([G + "calendar.events"]))
        # El secreto no va al archivo de estado.
        self.assertNotIn("ref", pathlib.Path(self.estado._ruta).read_text())

    def test_si_desmarca_un_permiso_se_dice(self):
        http = HttpFalso([G + "gmail.readonly"])   # faltó gmail.send
        with self.assertRaises(ErrorGoogle):
            self.cuenta(http).autorizar([G + "gmail.readonly", G + "gmail.send"], limite_seg=10)

    def test_id_token(self):
        self.assertEqual(correo_del_id_token(id_token("a@b.c")), "a@b.c")
        self.assertEqual(correo_del_id_token("basura"), "")


class PruebaRegistro(Base):
    def test_conectar_un_servicio_no_conecta_los_demas(self):
        http = HttpFalso(list(POR_ID["calendar"].alcances))
        reg = Registro(self.cuenta(http))
        cambios = []
        reg.al_cambiar(lambda s, a: cambios.append((s, a)))
        self.assertEqual(reg.estado("calendar"), "desconectado")
        reg.conectar(["calendar"])
        self.assertEqual(reg.estado("calendar"), "conectado")
        self.assertEqual(reg.estado("gmail"), "desconectado")
        self.assertEqual(cambios, [("calendar", True)])
        # La pantalla de Google pidió solo lo de Calendar (más openid/email).
        alcances = urllib.parse.parse_qs(urllib.parse.urlparse(self.urls[0]).query)["scope"][0]
        self.assertIn("calendar.events", alcances)
        self.assertNotIn("gmail", alcances)

    def test_desconectar_el_ultimo_revoca_en_google(self):
        http = HttpFalso(list(POR_ID["gmail"].alcances) + list(POR_ID["drive"].alcances))
        claves = ClavesFalsas()
        reg = Registro(self.cuenta(http, claves))
        reg.conectar(["gmail", "drive"])
        self.assertFalse(reg.desconectar(["gmail"]))
        self.assertEqual(reg.estado("gmail"), "desconectado")
        self.assertEqual(reg.estado("drive"), "conectado")
        self.assertTrue(reg.desconectar(["drive"]))
        self.assertTrue(any(u.endswith("/revoke") for u, _ in http.posts))
        self.assertNotIn(CREDENCIAL, claves.datos)

    def test_sin_cliente(self):
        cuenta = CuentaGoogle(claves=ClavesFalsas(), estado=self.estado,
                              ruta_cliente=str(pathlib.Path(self.tmp.name) / "no.json"))
        reg = Registro(cuenta)
        self.assertEqual(reg.estado("gmail"), "sin_cliente")
        self.assertIn("falta el cliente", reg.frase_estado())

    def test_frase_estado(self):
        http = HttpFalso(list(POR_ID["gmail"].alcances) + list(POR_ID["calendar"].alcances))
        reg = Registro(self.cuenta(http))
        self.assertEqual(reg.frase_estado(), "No tiene nada conectado todavía.")
        reg.conectar(["gmail", "calendar"])
        frase = reg.frase_estado()
        self.assertIn("Tiene conectados Gmail y Google Calendar con yo@gmail.com.", frase)
        self.assertIn("Sin conectar: Google Drive y Contactos de Google.", frase)


class PruebaNombres(unittest.TestCase):
    def test_servicios_por_como_se_nombran(self):
        ids = lambda t: [c.id for c in conectores_en(t)]  # noqa: E731
        self.assertEqual(ids("quiero agregar mi correo"), ["gmail"])
        self.assertEqual(ids("conecta mi agenda y mi drive"), ["calendar", "drive"])
        self.assertEqual(ids("añade mi agenda de contactos"), ["contactos"])
        self.assertEqual(ids("conecta mi cuenta de google"), [])


class PruebaVoz(unittest.TestCase):
    """El gestor elige la capacidad y pasa el servicio."""

    @classmethod
    def setUpClass(cls):
        from nucleo.intenciones.gestor import (CAP_CONECTAR_SERVICIO,
                                               CAP_DESCONECTAR_SERVICIO,
                                               CAP_ESTADO_CONEXIONES)
        cls.caps = (CAP_CONECTAR_SERVICIO, CAP_DESCONECTAR_SERVICIO, CAP_ESTADO_CONEXIONES)

    def cual(self, texto):
        for cap in self.caps:
            if any(p.search(texto) for p in cap.patrones):
                return cap.nombre
        return None

    def test_frases(self):
        casos = {
            "quiero agregar mi correo": "conectar_servicio",
            "conecta también mi calendario": "conectar_servicio",
            "desconecta mi correo": "desconectar_servicio",
            "ya no leas mi correo": "desconectar_servicio",
            "ya no leer mi correo": "desconectar_servicio",
            "deja de leer mi correo": "desconectar_servicio",
            "quiero que leer mis correos": "conectar_servicio",
            "quítale el acceso a mi drive": "desconectar_servicio",
            "qué tengo conectado": "estado_conexiones",
            "manda un correo a juan": None,
            "borra el correo de juan": None,
            "abre mi calendario": None,
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(self.cual(texto), esperado)


if __name__ == "__main__":
    unittest.main()
