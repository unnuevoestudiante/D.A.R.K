"""K.3.2 — `abrir_en_navegador`: la mitad que sí abre el navegador.

`investigar` (K.3.1) busca y resume sin navegar. Esta es la otra mitad: una
frase que pide una página en pantalla acaba en `webbrowser.open` y nada más. La
decisión del destino tiene tres capas y este archivo mide las dos primeras:
la tabla determinista (capa 1) y la política de URL. La capa 2 —el modelo
propone un dominio y se comprueba que resuelve— llega en K.3.3, y el sitio que
agrega el usuario desde la interfaz, en K.3.4.

Ninguna prueba toca la red ni al modelo: el navegador se parchea siempre y el
proveedor de chat se sustituye por un Mock que no tiene que verse llamado.
"""
import pathlib
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.fabrica import crear_banco
from herramientas.internas import manifest_tools as tm
from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from nucleo import sitios_web  # noqa: E402
from nucleo.intenciones.gestor import CAPACIDADES_NUCLEO, GestorIntenciones  # noqa: E402


def _intencion(texto):
    return GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(texto)


class PruebasCapacidad(unittest.TestCase):
    """Qué capacidad resuelve cada frase, y con qué parámetro."""

    def test_abre_la_pagina_de_python(self):
        intencion = _intencion("abre la página de Python")
        self.assertEqual(intencion.action, "abrir_en_navegador")
        self.assertEqual(intencion.params_planos()["consulta"], "Python")

    def test_busca_en_el_navegador(self):
        intencion = _intencion("busca en el navegador recetas de paella")
        self.assertEqual(intencion.action, "abrir_en_navegador")
        self.assertEqual(
            intencion.params_planos()["consulta"], "recetas de paella")

    def test_pon_en_pantalla_el_sitio_de(self):
        self.assertEqual(
            _intencion("pon en pantalla el sitio de Wikipedia").action,
            "abrir_en_navegador")

    def test_abre_ese_sitio_descrito(self):
        intencion = _intencion(
            "Ábreme ese sitio donde uno puede consultar repositorios de "
            "código, GitHub")
        self.assertEqual(intencion.action, "abrir_en_navegador")
        self.assertEqual(
            intencion.params_planos()["consulta"],
            "GitHub")

    def test_busca_x_sin_mentionar_navegador_sigue_investigando(self):
        """La guarda que separa las dos mitades: «busca X» no roba la página."""
        self.assertEqual(_intencion("busca recetas de paella").action,
                         "investigar")

    def test_busca_en_internet_sigue_investigando(self):
        self.assertEqual(
            _intencion("busca en internet algo sobre agentes autónomos").action,
            "investigar")

    def test_donde_puedo_encontrar_sigue_investigando(self):
        self.assertEqual(
            _intencion(
                "¿Dónde puedo encontrar la documentación de Python?").action,
            "investigar")

    def test_averigua_que_dice_sobre_una_pagina_sigue_investigando(self):
        """Pide el contenido de la página, no la página: es `investigar`."""
        self.assertEqual(
            _intencion(
                "Averigua qué dice la página oficial de Ollama").action,
            "investigar")

    def test_son_veintiseis_capacidades(self):
        self.assertEqual(len(CAPACIDADES_NUCLEO), 26)  # + conexiones: conectar, desconectar y estado


class PruebasTablaDeterminista(unittest.TestCase):
    """Capa 1: la tabla resuelve la marca sin modelo y sin red."""

    def test_marca_conocida_da_su_dominio(self):
        self.assertEqual(sitios_web.sitio_conocido("youtube"),
                         "https://www.youtube.com")
        self.assertEqual(sitios_web.sitio_conocido("Python"),
                         "https://www.python.org")

    def test_normaliza_acentos_mayusculas_y_sobrantes(self):
        self.assertEqual(sitios_web.sitio_conocido("  PÁGINA DE EL PAÍS "),
                         "https://elpais.com")

    def test_marca_inventada_no_esta_en_la_tabla(self):
        self.assertIsNone(sitios_web.sitio_conocido("pajarito-de-mi-barrio"))

    def test_resuelve_por_tabla(self):
        url, origen = sitios_web.resolver_destino("YouTube")
        self.assertEqual((url, origen), ("https://www.youtube.com", "tabla"))


class PruebasPoliticaDeUrl(unittest.TestCase):
    """Lo que se acepta como URL antes de abrir nada (punto 3 de la tarea)."""

    def test_http_y_https_siempre(self):
        self.assertEqual(sitios_web.url_valida("https://example.com/a?b=1"),
                         "https://example.com/a?b=1")
        self.assertEqual(sitios_web.url_valida("http://example.com"),
                         "http://example.com")

    def test_dominio_solo_gana_el_esquema(self):
        self.assertEqual(sitios_web.url_valida("python.org"),
                         "https://python.org")

    def test_rechaza_esquemas_peligrosos(self):
        for mal in ("javascript:alert(1)", "file:///C:/Windows/win.ini",
                    "data:text/html,<script>alert(1)</script>"):
            with self.subTest(valor=mal):
                self.assertIsNone(sitios_web.url_valida(mal))

    def test_rechaza_credenciales_en_la_url(self):
        self.assertIsNone(sitios_web.url_valida("https://user:pass@example.com"))

    def test_rechaza_lo_que_no_es_dominio(self):
        self.assertIsNone(sitios_web.url_valida("python"))
        self.assertIsNone(sitios_web.url_valida(""))
        self.assertIsNone(sitios_web.url_valida(None))

    def test_resuelve_por_url_cuando_ya_lo_es(self):
        url, origen = sitios_web.resolver_destino("example.com/notas")
        self.assertEqual((url, origen),
                         ("https://example.com/notas", "url"))

    def test_sin_tabla_y_sin_url_va_a_busqueda(self):
        url, origen = sitios_web.resolver_destino("pajarito de mi barrio")
        self.assertEqual(origen, "busqueda")
        self.assertIn("pajarito%20de%20mi%20barrio", url)
        self.assertTrue(url.startswith("https://www.google.com/search?q="))


class PruebasEspejoDelAbrir(unittest.TestCase):
    """Quién decide la página que llega al navegador: el dueño de capacidades.

    Desde el corte de web/sitios `abrir_en_navegador` y `_sugerir_dominio` viven
    en `herramientas/internas/ejecutor.py` y el núcleo ya no los define. Lo que
    se mide es la dirección abierta: si el dueño elige otra capa de la tabla, o
    deja de rechazar un esquema prohibido, el usuario ve abierta una página
    distinta de la que dijo sin que ningún mensaje lo advierta.
    """

    def setUp(self):
        self.directorio = tempfile.mkdtemp(prefix="dark_sitios_espejo_")
        self.ruta = os.path.join(self.directorio, "config", "sitios_web.json")

    def tearDown(self):
        import shutil

        shutil.rmtree(self.directorio, ignore_errors=True)

    def _ejecutor(self):
        # El almacén real no se lee: lo que hay en `config/sitios_web.json`
        # mandaría sobre la tabla y el resultado dependería de la máquina.
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        ejecutor._llm_provider = Mock()
        ejecutor._llm_lock = threading.Lock()
        ejecutor._almacen_sitios_web = (
            lambda: sitios_web.crear_almacen_sitios_web(ruta=self.ruta))
        return ejecutor

    def _abre(self, consulta):
        with patch("herramientas.internas.ejecutor.webbrowser.open",
                   return_value=True) as abrir:
            mensaje = self._ejecutor().abrir_en_navegador(consulta)
        return abrir, mensaje

    def test_abre_la_tabla_y_nada_mas(self):
        ejecutor = self._ejecutor()
        with patch("herramientas.internas.ejecutor.webbrowser.open",
                   return_value=True) as abrir:
            mensaje = ejecutor.abrir_en_navegador("YouTube")
        abrir.assert_called_once_with("https://www.youtube.com")
        self.assertIn("YouTube", mensaje)
        ejecutor._llm_provider.complete.assert_not_called()

    def test_un_desconocido_abre_la_busqueda_con_el_nombre_intacto(self):
        abrir, _ = self._abre("taller de bicicletas cerca de casa")
        abierta = abrir.call_args[0][0]
        self.assertTrue(abierta.startswith("https://www.google.com/search?q="))
        self.assertIn("taller%20de%20bicicletas%20cerca%20de%20casa", abierta)

    def test_una_url_escrita_se_abre_como_esta(self):
        abrir, _ = self._abre("https://example.com/a")
        abrir.assert_called_once_with("https://example.com/a")

    def test_un_esquema_prohibido_no_llega_al_navegador(self):
        abrir, _ = self._abre("javascript:alert(1)")
        abierta = abrir.call_args[0][0]
        self.assertTrue(abierta.startswith("https://www.google.com/search?q="))

    def test_sin_destino_no_abre_nada(self):
        with patch("herramientas.internas.ejecutor.webbrowser.open",
                   return_value=True) as abrir:
            mensaje = self._ejecutor().abrir_en_navegador("   ")
        abrir.assert_not_called()
        self.assertIn("navegador", mensaje)

    def test_si_el_navegador_no_responde_lo_dice(self):
        with patch("herramientas.internas.ejecutor.webbrowser.open",
                   return_value=False):
            mensaje = self._ejecutor().abrir_en_navegador("YouTube")
        self.assertIn("No pude", mensaje)

    def test_el_sitio_del_usuario_manda_sobre_la_tabla(self):
        """La capa que decide el dueño: lo que el usuario guardó es la URL que
        se abre, y el espejo tiene que leer el mismo almacén que el núcleo."""
        # `.test` no pasa la política de direcciones: el almacén no guarda nada
        # que luego no se pueda abrir, así que se escribe un dominio normal.
        self._ejecutor()._almacen_sitios_web().guardar(
            "YouTube", "https://mi-espejo.com")
        abrir, _ = self._abre("YouTube")
        abrir.assert_called_once_with("https://mi-espejo.com")


class PruebasHerramientaEnElBanco(unittest.TestCase):
    """La herramienta está declarada al modelo y la ejecuta el dueño nuevo.

    La ruta de resolución sigue diciendo `nucleo`: para el banco los dos dueños
    sin prefijo son el mismo camino (nombre pelado). Lo que separa quién ejecuta
    es el dueño de la montada, y es lo que se comprueba aquí.
    """

    class CapacidadesFalsas:
        def __init__(self, abierto):
            self.abierto = abierto

        def abrir_en_navegador(self, consulta):
            self.abierto.append(consulta)
            return f"Abriendo {consulta}."

    def test_declarada_al_modelo(self):
        self.assertIn("abrir_en_navegador", tm.tool_names_set())

    def test_la_ejecuta_el_dueo_de_capacidades_sin_prefijo(self):
        abierto = []
        banco = crear_banco(especialistas={},
                            capacidades=self.CapacidadesFalsas(abierto))
        self.assertEqual(banco.resolver("abrir_en_navegador").fuente, "nucleo")
        self.assertEqual(banco.montada("abrir_en_navegador").dueño, "capacidades")
        resultado = banco.ejecutar("abrir_en_navegador",
                                   {"consulta": "YouTube"})
        self.assertEqual(abierto, ["YouTube"])
        self.assertEqual(resultado, "Abriendo YouTube.")

    def test_el_parametro_no_suena_a_ruta(self):
        """`destino` sería normalizado como ruta por el banco; `consulta`, no."""
        abierto = []
        banco = crear_banco(
            especialistas={}, capacidades=self.CapacidadesFalsas(abierto),
            normalizador=lambda v: "C:\\Users\\samue\\Desktop\\YouTube")
        banco.ejecutar("abrir_en_navegador", {"consulta": "YouTube"})
        self.assertEqual(abierto, ["YouTube"])


if __name__ == "__main__":
    unittest.main()
