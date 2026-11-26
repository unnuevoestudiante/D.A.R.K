"""K.3.4: el almacén de sitios que agrega el usuario, por delante de la tabla.

`config/sitios_web.json` guarda los sitios que el usuario añadió. Tres reglas que
vigilan estas pruebas:

  * se LEE CADA VEZ: lo que escribe la interfaz tiene que valer para el siguiente
    «abre X» sin reiniciar nada;
  * va POR DELANTE de la tabla: «mi banco» manda aunque la tabla tenga otra cosa
    para esa palabra, y una URL escrita a mano sigue ganando a todo;
  * degrada, no lanza: un fichero que no existe, un JSON roto o una entrada sin
    URL utilizable se pasan por alto y la resolución sigue su camino.

El puerto está en `contratos/sitios_web.py`, la fábrica y la implementación en
`nucleo/sitios_web.py`, y la composición es la de `resolver_destino()`. Ninguna
prueba escribe en el `config/` del proyecto ni toca la red.
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
from nucleo import sitios_web  # noqa: E402


class ConTemporales(unittest.TestCase):
    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="jarvis_sitios_web_")
        self.ruta = os.path.join(self.directorio, "sitios_web.json")

    def tearDown(self):
        shutil.rmtree(self.directorio, ignore_errors=True)

    def escribir(self, datos):
        with open(self.ruta, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False)


class PruebasPuertoYFabrica(ConTemporales):
    def test_la_implementacion_cumple_el_puerto(self):
        self.escribir({"sitios": [{"nombre": "mi banco",
                                   "url": "https://banco-propio.com"}]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        self.assertIsInstance(almacen, PuertoSitiosWeb)
        self.assertEqual(almacen.sitio("mi banco"), "https://banco-propio.com")

    def test_la_fabrica_acepta_ruta_y_usa_esa_ruta(self):
        self.escribir({"sitios": [{"nombre": "foros",
                                   "url": "https://foros-propio.com"}]})

        self.assertEqual(
            sitios_web.crear_almacen_sitios_web(ruta=self.ruta).sitio("foros"),
            "https://foros-propio.com")

    def test_la_ruta_por_defecto_es_config_sitios_web(self):
        rutas = Path(sitios_web.RUTA_SITIOS_WEB).parts
        self.assertEqual(rutas[-2:], ("config", "sitios_web.json"))

    def test_consultar_no_crea_el_fichero_del_usuario(self):
        # Leer no escribe: el fichero aparece cuando la interfaz guarda algo
        # (K.3.5), no porque el Núcleo lo haya consultado.
        ruta = os.path.join(self.directorio, "config", "sitios_web.json")
        almacen = sitios_web.crear_almacen_sitios_web(ruta=ruta)

        self.assertFalse(os.path.exists(ruta))
        self.assertIsNone(almacen.sitio("cualquiera"))
        self.assertEqual(almacen.listar(), [])


class PruebasLectura(ConTemporales):
    def test_se_lee_cada_vez_sin_cachear(self):
        self.escribir({"sitios": [{"nombre": "mi banco",
                                   "url": "https://viejo-propio.com"}]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)
        self.assertEqual(almacen.sitio("mi banco"), "https://viejo-propio.com")

        self.escribir({"sitios": [{"nombre": "mi banco",
                                   "url": "https://nuevo.com"}]})
        self.assertEqual(almacen.sitio("mi banco"), "https://nuevo.com")

    def test_sin_fichero_no_hay_nada(self):
        almacen = sitios_web.crear_almacen_sitios_web(
            ruta=os.path.join(self.directorio, "no-existe.json"))

        self.assertIsNone(almacen.sitio("cualquiera"))
        self.assertEqual(almacen.listar(), [])

    def test_un_json_roto_no_deja_sin_navegador(self):
        with open(self.ruta, "w", encoding="utf-8") as f:
            f.write("{ esto no es json")
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        self.assertIsNone(almacen.sitio("mi banco"))
        self.assertEqual(almacen.listar(), [])

    def test_una_forma_que_no_es_lista_de_sitios_se_ignora(self):
        for datos in ({"sitios": "no es lista"}, {"otra_clave": []}, [], 7, None):
            self.escribir(datos)
            almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)
            self.assertIsNone(almacen.sitio("mi banco"), datos)

    def test_solo_entran_sitios_con_nombre_y_url_aprovechable(self):
        self.escribir({"sitios": [
            {"nombre": "mi banco", "url": "https://banco-propio.com"},
            {"nombre": "sin url"},
            {"url": "https://sin-nombre.com"},
            {"nombre": "con script", "url": "javascript:alert(1)"},
            {"nombre": "con claves", "url": "https://a:b@banco.com"},
            {"nombre": "desnudo", "url": "dominio.com"},
        ]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        self.assertEqual(
            almacen.listar(),
            [{"nombre": "mi banco", "url": "https://banco-propio.com"},
             {"nombre": "desnudo", "url": "https://dominio.com"}])

    def test_el_nombre_se_normaliza_antes_de_comparar(self):
        self.escribir({"sitios": [{"nombre": "Mi Banco",
                                   "url": "https://banco-propio.com"}]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        for como_llegue in ("  mi banco ", "MI BANCO", "la página de mi banco",
                            "el sitio de Mi Banco", "  Mi   Banco "):
            self.assertEqual(almacen.sitio(como_llegue),
                              "https://banco-propio.com", como_llegue)

    def test_lo_que_no_es_capaz_la_tabla_no_lo_inventa_el_almacen(self):
        # «mi banco oficial» no lo resuelve la tabla porque `normalizar_destino`
        # quita prefijos («la página de»), no sufijos. El almacén usa la misma
        # normalización: comparten idioma, así que comparten también los fallos.
        self.escribir({"sitios": [{"nombre": "Mi Banco",
                                   "url": "https://banco-propio.com"}]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        self.assertIsNone(almacen.sitio("mi banco oficial"))
        self.assertIsNone(sitios_web.sitio_conocido("youtube oficial"))

    def test_dos_sitios_con_el_mismo_nombre_gana_el_primero(self):
        self.escribir({"sitios": [
            {"nombre": "repeat", "url": "https://uno.com"},
            {"nombre": "repeat", "url": "https://dos.com"},
        ]})

        self.assertEqual(
            sitios_web.crear_almacen_sitios_web(ruta=self.ruta)
            .sitio("repeat"), "https://uno.com")


class PruebasPrioridadEnLaResolucion(ConTemporales):
    def test_el_almacen_gana_a_la_tabla(self):
        self.escribir({"sitios": [{"nombre": "youtube",
                                   "url": "https://mi-copia.com"}]})
        almacen = sitios_web.crear_almacen_sitios_web(ruta=self.ruta)

        url, origen = sitios_web.resolver_destino("youtube", almacen=almacen)

        self.assertEqual((url, origen), ("https://mi-copia.com", "usuario"))

    def test_la_url_escrita_gana_al_almacen(self):
        almacen = Mock()
        url, origen = sitios_web.resolver_destino(
            "https://escrito.com/nota", almacen=almacen)

        self.assertEqual((url, origen), ("https://escrito.com/nota", "url"))
        almacen.sitio.assert_not_called()

    def test_sin_almacen_el_camino_de_k33_sigue_igual(self):
        self.assertEqual(
            sitios_web.resolver_destino("youtube"),
            ("https://www.youtube.com", "tabla"))

    def test_el_almacen_va_delante_del_modelo(self):
        sugerir = Mock(return_value="otra.com")
        self.escribir({"sitios": [{"nombre": "pajarito",
                                   "url": "https://mi-pajarito.com"}]})

        url, origen = sitios_web.resolver_destino(
            "pajarito", sugerir=sugerir, resuelve=lambda d: True,
            almacen=sitios_web.crear_almacen_sitios_web(ruta=self.ruta))

        self.assertEqual((url, origen), ("https://mi-pajarito.com", "usuario"))
        sugerir.assert_not_called()

    def test_un_almacen_que_falla_no_deja_sin_navegador(self):
        almacen = Mock()
        almacen.sitio = Mock(side_effect=OSError("fichero bloqueado"))

        url, origen = sitios_web.resolver_destino("youtube", almacen=almacen)

        self.assertEqual((url, origen), ("https://www.youtube.com", "tabla"))

    def test_un_nombre_vacio_no_consulta_el_almacen(self):
        almacen = Mock()

        self.assertEqual(sitios_web.resolver_destino("   ", almacen=almacen),
                          ("", "vacio"))
        almacen.sitio.assert_not_called()


class PruebasEnElEjecutor(ConTemporales):
    """El dueño que abre la página lee el almacén que escribe la interfaz."""

    def ejecutor_con_este_almacen(self):
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        ejecutor._sugerir_dominio = Mock(return_value=None)
        ejecutor._almacen_sitios_web = Mock(
            return_value=sitios_web.crear_almacen_sitios_web(ruta=self.ruta))
        return ejecutor

    def test_abrir_en_navegador_abre_lo_que_puso_el_usuario(self):
        self.escribir({"sitios": [{"nombre": "YouTube",
                                   "url": "https://mi-copia.com"}]})
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre):
            mensaje = self.ejecutor_con_este_almacen().abrir_en_navegador("YouTube")

        self.assertEqual(abre.call_args[0][0], "https://mi-copia.com")
        self.assertIn("YouTube", mensaje)

    def test_lo_escrito_por_la_interfaz_vale_al_siguiente_abrir(self):
        # La razón de leer sin caché: el panel de sitios escribe y el dueño no
        # se reinicia. Mismo almacén, dos aperturas, fichero cambiado en medio.
        self.escribir({"sitios": [{"nombre": "mi foro",
                                   "url": "https://uno.com"}]})
        ejecutor = self.ejecutor_con_este_almacen()
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre):
            ejecutor.abrir_en_navegador("mi foro")
            self.escribir({"sitios": [{"nombre": "mi foro",
                                       "url": "https://dos.com"}]})
            ejecutor.abrir_en_navegador("mi foro")

        self.assertEqual([l[0][0] for l in abre.call_args_list],
                          ["https://uno.com", "https://dos.com"])

    def test_sin_sitios_del_usuario_manda_la_tabla(self):
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre):
            self.ejecutor_con_este_almacen().abrir_en_navegador("YouTube")

        self.assertEqual(abre.call_args[0][0], "https://www.youtube.com")


if __name__ == "__main__":
    unittest.main()
