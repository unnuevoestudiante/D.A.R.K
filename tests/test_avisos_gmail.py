"""Gmail como fuente de avisos: vigilancia sobre la cuenta de Google compartida."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from avisos.clasificador import Clasificador  # noqa: E402
from avisos.gmail import CONSULTA, VigilanteGmail, como_notificacion, remitente  # noqa: E402


def correo(de, asunto, extracto):
    return {"snippet": extracto, "payload": {"headers": [
        {"name": "From", "value": de}, {"name": "Subject", "value": asunto}]}}


class CuentaFalsa:
    """Lo que el vigilante usa de CuentaGoogle: `pedir`."""

    def __init__(self):
        self.mensajes = {}
        self.pedidos = []

    def pedir(self, metodo, url, params=None):
        self.pedidos.append((metodo, url, params))
        if url.endswith("/messages"):
            return {"messages": [{"id": i} for i in self.mensajes]}
        return self.mensajes[url.rsplit("/", 1)[1]]


class PruebaVigilante(unittest.TestCase):
    def test_lo_que_ya_estaba_no_se_avisa_y_lo_nuevo_si(self):
        cuenta = CuentaFalsa()
        cuenta.mensajes = {"viejo": correo("Temu <x@temu.com>", "Oferta", "90%")}
        entregadas = []
        v = VigilanteGmail(cuenta, entregadas.append, activo=lambda: True, log=lambda *_: None)
        self.assertEqual(v.revisar(), [])
        cuenta.mensajes["nuevo"] = correo('"Ana Torres" <ana@uni.edu>', "Examen",
                                          "Se mueve al jueves")
        nuevas = v.revisar()
        self.assertEqual(v.revisar(), [])
        self.assertEqual([n.titulo for n in nuevas], ["Ana Torres"])
        self.assertEqual(entregadas, nuevas)
        self.assertIn("Examen", nuevas[0].cuerpo)
        self.assertEqual(cuenta.pedidos[0][2]["q"], CONSULTA)
        self.assertIn("-category:promotions", CONSULTA)

    def test_sin_conector_no_arranca(self):
        v = VigilanteGmail(CuentaFalsa(), lambda n: None, activo=lambda: False,
                           log=lambda *_: None)
        self.assertFalse(v.iniciar())

    def test_remitente(self):
        self.assertEqual(remitente('"Ana" <a@b.c>'), "Ana")
        self.assertEqual(remitente("<a@b.c>"), "a@b.c")
        self.assertEqual(remitente("a@b.c"), "a@b.c")

    def test_codigo_por_correo_es_urgente(self):
        n = como_notificacion(correo("Google <no-reply@google.com>",
                                     "Código de verificación", "Tu código es 482913"))
        v = Clasificador(None)(n)
        self.assertTrue(v.urgente)
        self.assertEqual(v.frase, "Llegó un código de acceso por Gmail.")

    def test_sin_groq_un_correo_se_avisa(self):
        v = Clasificador(None)(como_notificacion(correo("Ana <a@b.c>", "Hola", "qué tal")))
        self.assertTrue(v.importante)
        self.assertEqual(v.frase, "Tiene un correo de Ana.")


if __name__ == "__main__":
    unittest.main()
