"""La otra superficie también puede escribir: el texto entra por HTTP.

El input del overlay manda su texto por el mismo WebSocket de estado (8765) por el
que lo recibe. HollOSW no puede hacer lo mismo sin dejar de ser un cliente de solo
lectura —el puente convierte cualquier mensaje de cliente en texto escrito por el
usuario, o sea en una orden—, así que su texto entra por una ruta HTTP aparte y
cae en la misma `on_message` que el del overlay.

Ref: dark_python/modulos/dark_overlay_bridge.py (`recibir_texto_externo`,
`es_local`, el `do_POST` del Handler).

Solo stdlib: OverlayBridge construido por __new__, sin abrir puertos ni hilos.
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

# El mismo tope que declara el puente: se repite aquí a propósito para que subirlo
# obligue a mirar esta prueba.
TOPE = 4096


def bridge_que_anota():
    from modulos.dark_overlay_bridge import OverlayBridge

    b = OverlayBridge.__new__(OverlayBridge)
    recibidos = []
    # La firma real del alambre: `on_message` recibe el texto y quien lo envió.
    b.on_message = lambda texto, origen=None: recibidos.append((texto, origen))
    return b, recibidos


class PruebaTextoExterno(unittest.TestCase):
    def test_el_texto_se_entrega_como_llegaria_del_overlay(self):
        b, recibidos = bridge_que_anota()
        self.assertTrue(b.recibir_texto_externo("hola dark"))
        self.assertEqual(recibidos, [("hola dark", None)])

    def test_se_entrega_igual_que_desde_el_websocket(self):
        """Lo que se reenvía es el texto tal cual: sin recortar ni transformar."""
        b, recibidos = bridge_que_anota()
        b.recibir_texto_externo("  Pon un fondo de montana  ")
        self.assertEqual(recibidos, [("  Pon un fondo de montana  ", None)])

    def test_no_se_envia_texto_vacio(self):
        for texto in ("", "   ", "\n\t"):
            with self.subTest(repr(texto)):
                b, recibidos = bridge_que_anota()
                self.assertFalse(b.recibir_texto_externo(texto))
                self.assertEqual(recibidos, [])

    def test_se_rechaza_lo_que_no_es_texto(self):
        for cosa in (None, 12, ["hola"], {"action": "x"}):
            with self.subTest(repr(cosa)):
                b, recibidos = bridge_que_anota()
                self.assertFalse(b.recibir_texto_externo(cosa))
                self.assertEqual(recibidos, [])

    def test_se_rechaza_un_texto_desmedido(self):
        b, recibidos = bridge_que_anota()
        self.assertFalse(b.recibir_texto_externo("a" * (TOPE + 1)))
        self.assertEqual(recibidos, [])

    def test_un_texto_en_el_limite_si_pasa(self):
        b, recibidos = bridge_que_anota()
        self.assertTrue(b.recibir_texto_externo("a" * TOPE))
        self.assertEqual(len(recibidos), 1)

    def test_sin_on_message_no_explode(self):
        from modulos.dark_overlay_bridge import OverlayBridge

        b = OverlayBridge.__new__(OverlayBridge)
        b.on_message = None
        self.assertFalse(b.recibir_texto_externo("hola"))

    def test_el_origen_viaja_con_el_texto(self):
        """La compuerta de `sitio_web` decide por la dirección remota: si el origen
        se pierde al encolarse, la escritura queda muda aunque el texto sea válido."""
        b, recibidos = bridge_que_anota()
        peticion = '{"action": "sitio_web", "nombre": "Foro", "url": "foro-x.net"}'
        self.assertTrue(b.recibir_texto_externo(peticion, "127.0.0.1"))
        self.assertEqual(recibidos, [(peticion, "127.0.0.1")])

    def test_la_puerta_es_solo_para_esta_maquina(self):
        from modulos.dark_overlay_bridge import es_local

        for ip in ("127.0.0.1", "127.0.0.2", "::1", "localhost"):
            with self.subTest(ip):
                self.assertTrue(es_local(ip))
        for ip in ("192.168.1.9", "10.0.0.1", "169.254.1.1", "", "no-es-una-ip"):
            with self.subTest(ip):
                self.assertFalse(es_local(ip))


class PruebaRutaHttp(unittest.TestCase):
    """La ruta existe y solo llama a la puerta: el resto lo decide `recibir_texto_externo`."""

    def setUp(self):
        fuente = (
            DARK_PYTHON / "modulos" / "dark_overlay_bridge.py"
        ).read_text(encoding="utf-8")
        self.arbol = ast.parse(fuente)

    def _funciones_llamadas(self, nodo):
        """Nombres de todo lo que se llama dentro de un nodo, por atributo o suelto."""
        nombres = set()
        for l in ast.walk(nodo):
            if not isinstance(l, ast.Call):
                continue
            if isinstance(l.func, ast.Attribute):
                nombres.add(l.func.attr)
            elif isinstance(l.func, ast.Name):
                nombres.add(l.func.id)
        return nombres

    def test_el_handler_tiene_do_post(self):
        nombres = {
            n.name
            for n in ast.walk(self.arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        self.assertIn("do_POST", nombres)

    def test_do_post_pide_el_texto_a_la_puerta_y_mira_el_peer(self):
        for n in ast.walk(self.arbol):
            if isinstance(n, ast.FunctionDef) and n.name == "do_POST":
                llamadas = self._funciones_llamadas(n)
                self.assertIn("recibir_texto_externo", llamadas)
                self.assertIn("es_local", llamadas)
                return
        self.fail("no hay do_POST en el handler")

    def test_do_post_entrega_a_la_puerta_la_direccion_del_peer(self):
        """El `es_local` del handler y el `ORIGENES_LOCALES` del núcleo no son la
        misma comprobación: la segunda mira el origen que se reenvía, así que si
        do_POST no pasa la dirección remota, ninguna escritura llega a abrirse."""
        for n in ast.walk(self.arbol):
            if isinstance(n, ast.FunctionDef) and n.name != "do_POST":
                continue
            for l in ast.walk(n):
                if not (isinstance(l, ast.Call) and isinstance(l.func, ast.Attribute)):
                    continue
                if l.func.attr != "recibir_texto_externo":
                    continue
                self.assertEqual(
                    len(l.args), 2,
                    "la puerta recibe solo el texto: el origen se pierde")
                self.assertIn(
                    "client_address", ast.unparse(l),
                    "la puerta no recibe la dirección del peer")
                return
        self.fail("do_POST no llama a recibir_texto_externo")


if __name__ == "__main__":
    unittest.main()
