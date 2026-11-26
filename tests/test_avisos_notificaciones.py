"""Notificaciones de Windows como avisos: lectura de la base y clasificación."""
import pathlib
import sqlite3
import sys
import unittest
from types import SimpleNamespace

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from avisos.clasificador import Clasificador, es_codigo, interpretar  # noqa: E402
from avisos.notificaciones_windows import (  # noqa: E402
    Notificacion,
    app_de,
    leer_nuevas,
    textos_del_toast,
    ultimo_orden,
)


def toast(*textos, atribucion=""):
    cuerpo = "".join(f"<text>{t}</text>" for t in textos)
    if atribucion:
        cuerpo += f'<text placement="attribution">{atribucion}</text>'
    return f'<toast><visual><binding template="ToastGeneric">{cuerpo}</binding></visual></toast>'.encode()


def base_falsa(filas):
    """Mismo esquema (lo que se usa) que wpndatabase.db."""
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE NotificationHandler (RecordId INTEGER, PrimaryId TEXT)")
    con.execute('CREATE TABLE Notification ("Order" INTEGER, HandlerId INTEGER, '
                "Type TEXT, Payload BLOB)")
    handlers = {}
    for orden, handler, payload in filas:
        rid = handlers.setdefault(handler, len(handlers) + 1)
        con.execute("INSERT INTO Notification VALUES (?, ?, 'toast', ?)", (orden, rid, payload))
    for handler, rid in handlers.items():
        con.execute("INSERT INTO NotificationHandler VALUES (?, ?)", (rid, handler))
    return con


WA = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"


class PruebaLectura(unittest.TestCase):
    def test_textos_y_atribucion(self):
        textos, attr = textos_del_toast(toast("Ana", "¿Mañana?", atribucion="web.whatsapp.com"))
        self.assertEqual(textos, ["Ana", "¿Mañana?"])
        self.assertEqual(attr, "web.whatsapp.com")
        self.assertEqual(textos_del_toast(b"<roto"), ([], ""))

    def test_apps_vigiladas(self):
        self.assertEqual(app_de(WA), ("whatsapp", "WhatsApp"))
        self.assertEqual(app_de("com.squirrel.Discord.Discord"), ("discord", "Discord"))
        self.assertEqual(app_de("Opera.GX", "web.whatsapp.com"), ("whatsapp", "WhatsApp"))
        self.assertEqual(app_de("Microsoft.YourPhone_8wekyb3d8bbwe!App")[0], "telefono")
        self.assertIsNone(app_de("Windows.Defender.SecurityCenter"))

    def test_solo_las_nuevas_y_de_apps_vigiladas(self):
        con = base_falsa([
            (1, WA, toast("Viejo", "ya estaba")),
            (2, "Windows.Defender.SecurityCenter", toast("Defender", "análisis")),
            (3, WA, toast("Ana", "¿Mañana?")),
        ])
        self.assertEqual(ultimo_orden(con), 3)
        nuevas = leer_nuevas(con, 1)
        self.assertEqual([(n.orden, n.titulo, n.cuerpo) for n in nuevas], [(3, "Ana", "¿Mañana?")])


def noti(titulo, cuerpo, fuente="whatsapp", app="WhatsApp"):
    return Notificacion(1, app, fuente, titulo, cuerpo)


class ProveedorFalso:
    def __init__(self, respuesta=None, error=None):
        self.respuesta, self.error, self.pedidos = respuesta, error, []

    def complete(self, solicitud, timeout=None):
        self.pedidos.append(solicitud)
        if self.error:
            raise self.error
        return SimpleNamespace(content=self.respuesta)


class PruebaClasificador(unittest.TestCase):
    def test_codigo_es_urgente_sin_preguntar_y_sin_digitos(self):
        prov = ProveedorFalso()
        v = Clasificador(prov)(noti("Google", "Tu código de verificación es 482913",
                                    fuente="telefono", app="el teléfono"))
        self.assertTrue(v.urgente and v.importante)
        self.assertNotIn("482913", v.frase)
        self.assertEqual(prov.pedidos, [])

    def test_no_todo_numero_es_un_codigo(self):
        self.assertFalse(es_codigo(noti("Ana", "llego en 2025 minutos jaja")))
        self.assertTrue(es_codigo(noti("Discord", "Your login code: 123-456")))

    def test_groq_decide(self):
        prov = ProveedorFalso('{"importante": true, "urgente": false, '
                              '"frase": "Ana le escribe por WhatsApp: pregunta por mañana."}')
        v = Clasificador(prov)(noti("Ana", "¿Sigue en pie lo de mañana?"))
        self.assertTrue(v.importante)
        self.assertEqual(v.frase, "Ana le escribe por WhatsApp: pregunta por mañana.")
        self.assertEqual(v.clave, "whatsapp:ana")

    def test_groq_descarta_el_spam(self):
        prov = ProveedorFalso('{"importante": false, "urgente": false, "frase": ""}')
        self.assertFalse(Clasificador(prov)(noti("Temu", "¡90% de descuento!")).importante)

    def test_sin_groq_el_respaldo_avisa_los_mensajes(self):
        v = Clasificador(ProveedorFalso(error=RuntimeError("sin red")), log=lambda *_: None)(
            noti("Ana", "hola"))
        self.assertTrue(v.importante)
        self.assertEqual(v.frase, "Tiene un mensaje de Ana en WhatsApp.")

    def test_respuesta_ilegible(self):
        self.assertIsNone(interpretar("no sé", noti("a", "b")))
        self.assertIsNone(interpretar('{"importante": "quizá"}', noti("a", "b")))


if __name__ == "__main__":
    unittest.main()
