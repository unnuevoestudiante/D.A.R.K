"""K.3.5a: guardar un sitio desde la interfaz, solo desde este PC.

Dos cosas vigilan estas pruebas, y son las dos que el requisito 4 de K.3 firma:

  * el puente :8765 escucha en 0.0.0.0 (lo hace para que entren la tele y el
    móvil), así que la dirección remota tiene que llegar hasta el despachador:
    sin ella no hay manera de saber quién escribió;
  * `sitio_web` SOLO se acepta de loopback. De cualquier otro origen —y también
    de un origen que no se conozca— se ignora, se registra, y NO se toca
    `config/sitios_web.json`.

Como las pruebas no pueden escribir en el `config/` del proyecto, parchean
`sitios_web.RUTA_SITIOS_WEB` a un temporal y, en el caso de rechazo, afirman
además que la fábrica del almacén no se llega a llamar: si no se construye, no
puede escribir.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.sitios_web import PuertoSitiosWeb  # noqa: E402
from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from modulos.dark_overlay_bridge import OverlayBridge  # noqa: E402
from nucleo import sitios_web  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402


class ConTemporales(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="jarvis_sitios_guardar_")
        self.ruta = os.path.join(self.directorio, "config", "sitios_web.json")

    def tearDown(self):
        shutil.rmtree(self.directorio, ignore_errors=True)

    def escribir(self, datos):
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)

    def leer_crudo(self):
        with open(self.ruta, encoding="utf-8") as f:
            return json.load(f)


class PruebasGuardarEnElAlmacen(ConTemporales):
    def almacen(self):
        return sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

    def test_guardar_cre_el_fichero_y_su_carpeta(self):
        self.almacen().guardar("mi banco", "https://banco-propio.com")

        self.assertEqual(
            self.leer_crudo(),
            {"sitios": [{"nombre": "mi banco",
                         "url": "https://banco-propio.com"}]})

    def test_lo_guardado_se_lee_con_el_mismo_nombre(self):
        self.almacen().guardar("Mi Banco", "https://banco-propio.com")

        self.assertEqual(self.almacen().sitio("la página de mi banco"),
                         "https://banco-propio.com")

    def test_guardar_conserva_lo_que_ya_estaba(self):
        self.escribir({"sitios": [{"nombre": "mi foro",
                                   "url": "https://foro-propio.com"}]})

        self.almacen().guardar("mi banco", "https://banco-propio.com")

        self.assertEqual(len(self.leer_crudo()["sitios"]), 2)

    def test_el_mismo_nombre_se_reemplaza_sin_duplicarse(self):
        self.escribir({"sitios": [{"nombre": "mi banco",
                                   "url": "https://viejo-propio.com"},
                                  {"nombre": "mi foro",
                                   "url": "https://foro-propio.com"}]})

        self.almacen().guardar("Mi Banco", "https://nuevo-propio.com")

        self.assertEqual(
            self.leer_crudo()["sitios"],
            [{"nombre": "Mi Banco", "url": "https://nuevo-propio.com"},
             {"nombre": "mi foro", "url": "https://foro-propio.com"}])
        self.assertEqual(self.almacen().sitio("mi banco"),
                         "https://nuevo-propio.com")

    def test_una_url_que_no_pasa_la_politica_no_se_escribe(self):
        for sucia in ("javascript:alert(1)", "file:///C:/Windows",
                      "https://a:b@banco-propio.com", "notas.txt",
                      "https://banco-propio.com con espacio", ""):
            with self.subTest(url=sucia):
                self.assertIsNone(
                    self.almacen().guardar("mi banco", sucia))
                self.assertFalse(os.path.exists(self.ruta))

    def test_un_nombre_vacio_no_se_escribe(self):
        self.assertIsNone(self.almacen().guardar("   ", "https://x.com"))
        self.assertFalse(os.path.exists(self.ruta))

    def test_guardar_no_deja_ficheros_a_mitad(self):
        # El cambio va por fichero temporal + rename: si se cortara a media
        # escritura, el fichero del usuario quedaría inservible.
        self.almacen().guardar("mi banco", "https://banco-propio.com")

        self.assertEqual(os.listdir(os.path.dirname(self.ruta)),
                         ["sitios_web.json"])

    def test_guardar_un_fichero_roto_lo_reemplaza_con_algo_legible(self):
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write("{ esto no es json")

        self.almacen().guardar("mi banco", "https://banco-propio.com")

        self.assertEqual(self.almacen().sitio("mi banco"),
                         "https://banco-propio.com")

    def test_guardar_devuelve_la_url_que_quedo(self):
        self.assertEqual(
            self.almacen().guardar("desnudo", "dominio.com"),
            "https://dominio.com")

    def test_el_almacen_con_guardar_sigue_cumpliendo_el_puerto(self):
        self.assertIsInstance(self.almacen(), PuertoSitiosWeb)


class PruebasPuenteEntregaElOrigen(unittest.TestCase):
    def test_el_puente_saca_la_ip_de_la_conexion(self):
        conexion = SimpleNamespace(remote_address=("192.168.1.42", 5555))

        self.assertEqual(OverlayBridge._origen_de(conexion), "192.168.1.42")

    def test_sin_direccion_conocida_no_inventa_una(self):
        self.assertIsNone(OverlayBridge._origen_de(
            SimpleNamespace(remote_address=None)))
        self.assertIsNone(OverlayBridge._origen_de(SimpleNamespace()))

    def test_el_puente_pasa_el_origen_al_callback(self):
        import inspect

        origen = inspect.getsource(OverlayBridge._serve)
        self.assertIn("self.on_message(message, origen)", origen)


class PruebasCompuertaEnElNucleo(ConTemporales):
    def nucleo(self, *, bloqueado=False):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._modo_bloqueado = bloqueado
        nucleo._text_queue = Mock()
        nucleo._accion_ui = Mock()
        # `clear_results` ya no tiene hoja en el núcleo: la compuerta le pregunta
        # al dueño, así que el doble se monta allí y el nombre del núcleo apunta
        # al MISMO objeto para que la aserción de abajo cuente el cable.
        dueño = nucleo._capacidades_herramientas()
        dueño._ocultar_resultados_visuales = Mock()
        nucleo._ocultar_resultados_visuales = dueño._ocultar_resultados_visuales
        nucleo._sugerir_dominio = Mock(return_value=None)
        nucleo._almacen_sitios_web = Mock(
            side_effect=lambda: sitios_web.crear_almacen_sitios_web(
                ruta=self.ruta))
        return nucleo

    def almacen(self):
        return sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

    def mensaje(self, nombre="mi banco", url="https://banco-propio.com"):
        return json.dumps({"action": "sitio_web", "nombre": nombre,
                           "url": url})

    def guardar_desde(self, nucleo, origen, texto=None):
        with patch.object(sitios_web, "RUTA_SITIOS_WEB", self.ruta):
            DarkNucleo._encolar_texto_manual(
                nucleo, texto or self.mensaje(), origen)

    def test_loopback_guarda(self):
        nucleo = self.nucleo()

        self.guardar_desde(nucleo, "127.0.0.1")

        self.assertEqual(self.almacen().sitio("mi banco"),
                         "https://banco-propio.com")

    def test_ipv6_loopback_guarda(self):
        self.guardar_desde(self.nucleo(), "::1")

        self.assertTrue(os.path.exists(self.ruta))

    def test_una_ip_de_la_red_no_escribe_nada(self):
        # El requisito 4, medido donde duele: la tele y el móvil entran por la
        # misma puerta 8765, y no pueden escribir en el config del PC.
        nucleo = self.nucleo()

        with patch("builtins.print") as consola:
            self.guardar_desde(nucleo, "192.168.1.42")

        self.assertFalse(os.path.exists(self.ruta))
        nucleo._almacen_sitios_web.assert_not_called()
        self.assertTrue(any("sitio_web" in str(c.args)
                            for c in consola.call_args_list))

    def test_un_origen_desconocido_se_rechaza_por_defecto(self):
        # `None` es una conexión a la que no se le pilló dirección: no puede
        # significar «seguro», significa «no lo sé».
        nucleo = self.nucleo()

        self.guardar_desde(nucleo, None)

        self.assertFalse(os.path.exists(self.ruta))
        nucleo._almacen_sitios_web.assert_not_called()

    def test_localhost_tambien_es_local(self):
        self.guardar_desde(self.nucleo(), "localhost")

        self.assertTrue(os.path.exists(self.ruta))

    def test_bloqueo_facial_no_escribe(self):
        nucleo = self.nucleo(bloqueado=True)

        self.guardar_desde(nucleo, "127.0.0.1")

        self.assertFalse(os.path.exists(self.ruta))

    def test_desde_loopback_una_url_mala_tampoco_escribe(self):
        nucleo = self.nucleo()

        self.guardar_desde(
            nucleo, "127.0.0.1",
            json.dumps({"action": "sitio_web", "nombre": "mi banco",
                        "url": "javascript:alert(1)"}))

        self.assertFalse(os.path.exists(self.ruta))

    def test_sin_sitios_del_usuario_no_se_rompe_nada(self):
        nucleo = self.nucleo()

        self.guardar_desde(nucleo, "127.0.0.1")
        self.guardar_desde(
            nucleo, "127.0.0.1", json.dumps({"action": "sitio_web"}))

        self.assertEqual(len(self.leer_crudo()["sitios"]), 1)

    def test_las_demas_acciones_no_piden_origen(self):
        # El segundo argumento es del puente: quien manda texto suelto o un
        # `clear_results` sigue entrando igual que antes.
        nucleo = self.nucleo()

        DarkNucleo._encolar_texto_manual(
            nucleo, '{"action":"clear_results"}')

        nucleo._accion_ui.assert_called_once()
        self.assertIs(nucleo._accion_ui.call_args.args[0],
                      nucleo._ocultar_resultados_visuales)


class PruebasCadenaCompleta(ConTemporales):
    def test_lo_que_guarda_la_interfaz_lo_abre_la_voz(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._modo_bloqueado = False
        nucleo._text_queue = Mock()
        # Quien abre ya no es el núcleo: el dueño de capacidades construye su
        # almacén con la misma fábrica, así que `RUTA_SITIOS_WEB` vale para los
        # dos extremos de la cadena y no hay que inyectarle nada.
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        ejecutor._sugerir_dominio = Mock(return_value=None)
        abre = Mock(return_value=True)

        with patch.object(sitios_web, "RUTA_SITIOS_WEB", self.ruta):
            DarkNucleo._encolar_texto_manual(
                nucleo, json.dumps({"action": "sitio_web",
                                    "nombre": "mi copia",
                                    "url": "https://mi-copia.com"}),
                "127.0.0.1")
            with patch("herramientas.internas.ejecutor.webbrowser.open", abre):
                mensaje = ejecutor.abrir_en_navegador("mi copia")

        self.assertEqual(abre.call_args[0][0], "https://mi-copia.com")
        self.assertIn("mi copia", mensaje)


if __name__ == "__main__":
    unittest.main()
