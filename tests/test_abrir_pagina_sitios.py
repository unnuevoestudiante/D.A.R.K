"""#43 y #46 — la puerta de texto al panel de sitios del overlay.

El panel donde el usuario escribe sus enlaces no tenía cómo alcanzarse: ninguna
capacidad lo nombraba. Esta capacidad es la puerta de texto, y vive dentro del
matcher de siempre —`_VOCABULARIO_AJUSTES` puntuando la frase y `patrones`
extrayendo los parámetros—, no por un atajo fuera de él.

Lo que abre es el overlay, no el navegador. La primera versión (`86eedb11`)
mandaba `http://…/sitios` a `webbrowser.open` y el usuario la retiró: «esa página
debe ser parte de el overlay, no algo que se abre en el navegador». `PruebasPagina`
afirmaba lo contrario (que el destino era `/sitios` en la misma máquina y puerto
del overlay, y que `webbrowser.open` se llamaba una vez con esa URL); esa
afirmación ya no aplica y abajo está `PruebasPanel`, que afirma el `menuData`.

El veto semántico de ONNX (`intenciones/clasificador_semantico.py`) no elige
capacidades: solo puede apagarlas (`nucleo/dark_nucleo.py:2682`), así que la
familia de frases se resuelve aquí, con el gestor de siempre y sin modelo.

Ninguna prueba toca la red: el almacén y el overlay se parchean y el proveedor de
chat es un Mock que no tiene que verse llamado.
"""
import inspect
import pathlib
import sys
import threading
import unittest
from unittest.mock import Mock, patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import MENU_COMANDOS, DarkNucleo  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    CAP_ABRIR_PAGINA_SITIOS,
    GestorIntenciones,
    _VOCABULARIO_AJUSTES,
)

ACCION = "abrir_pagina_sitios"

#: La familia que pidió el usuario, tal cual se diría en voz alta.
FRASES_DE_LA_PUERTA = (
    "quiero agregar un nuevo link",
    "agrega un enlace",
    "añade una url nueva",
    "necesito agregar un enlace",
    "me apetece añadir una url",
    "quiero que agregues un enlace",
    "dark, agrega un sitio nuevo",
)

#: Frases que se parecen pero tienen dueño: esta capacidad no las invade.
FRASES_CON_OTRO_DUEÑO = {
    "guardar_sitio_web": (
        "guarda que mi banco es https://mi-banco.com",
        "agrega que mi foro es foro-x.net",
    ),
    "abrir_en_navegador": (
        "abre la página de Python",
        "abre la página de mis sitios",
    ),
}


def _intencion(texto):
    return GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(texto)


def _nucleo_de_menues(**banderas):
    """Un Núcleo recién nacido sin puente, overlay vivo ni LLM.

    `__new__` evita levantar servidores; lo que se pone a mano es exactamente el
    estado que `_menu_payload` lee, y `_set_overlay` queda como Mock para poder
    mirar el `menu_data` que se mandó.
    """
    nucleo = DarkNucleo.__new__(DarkNucleo)
    nucleo._menu_lock = threading.Lock()
    nucleo._menu_recursos_visible = bool(banderas.get("recursos_visible", False))
    nucleo._menu_recursos_data = banderas.get("recursos_data")
    nucleo._menu_tareas_visible = bool(banderas.get("tareas_visible", False))
    nucleo._menu_tareas_data = banderas.get("tareas_data")
    nucleo._menu_sitios_visible = bool(banderas.get("sitios_visible", False))
    nucleo._menu_sitios_data = banderas.get("sitios_data")
    nucleo.overlay = Mock()
    nucleo.overlay.estado.return_value = "idle"
    nucleo._set_overlay = Mock()
    return nucleo


def _ultimo_payload(nucleo):
    """El `menu_data` con el que el Núcleo llamó al overlay por última vez."""
    return nucleo._set_overlay.call_args.kwargs["menu_data"]


def _almacen(sitios):
    return Mock(listar=Mock(return_value=sitios))


class PruebasFrase(unittest.TestCase):
    """La familia de «agregar un link» acaba en la página, sin preguntas."""

    def test_cada_frase_abre_la_pagina(self):
        for frase in FRASES_DE_LA_PUERTA:
            with self.subTest(frase=frase):
                self.assertEqual(_intencion(frase).action, ACCION)

    def test_no_pide_ningun_parametro(self):
        #: No hay destino que preguntar: la página es fija. Si esta capacidad
        #: declarara un requerido, el Núcleo devolvería una pregunta en vez de
        #: abrir, que es justo lo que se quiso evitar.
        for frase in FRASES_DE_LA_PUERTA:
            with self.subTest(frase=frase):
                intencion = _intencion(frase)
                self.assertEqual(intencion.faltantes, [])
                self.assertTrue(intencion.completa())

    def test_no_es_peligrosa(self):
        self.assertFalse(CAP_ABRIR_PAGINA_SITIOS.peligrosa)


class PruebasNoInvasora(unittest.TestCase):
    """El corte fino: con dirección en la frase, la página no se cuela."""

    def test_las_frases_con_direccion_tienen_dueno(self):
        for accion, frases in FRASES_CON_OTRO_DUEÑO.items():
            for frase in frases:
                with self.subTest(frase=frase):
                    self.assertEqual(_intencion(frase).action, accion)

    def test_sin_empate_que_pregunte(self):
        #: Un empate entre dos capacidades que capturan parámetros hace que el
        #: Núcleo pregunte cuál («gestor.py:3111»), y la puerta dejaría de ser
        #: una frase para convertirse en dos. El desempate se mira en el mismo
        #: gestor que interpretó: `_ultimas_candidatas` es su memoria.
        for frase in FRASES_DE_LA_PUERTA:
            with self.subTest(frase=frase):
                gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
                gestor.interpretar(frase)
                self.assertFalse(gestor._hay_empate())

    def test_el_vocabulario_declara_la_familia(self):
        verbos, objetos, _mod, _ex = _VOCABULARIO_AJUSTES[ACCION]
        self.assertIn("agregar", verbos)
        self.assertIn("añadir", verbos)
        self.assertIn("enlace", objetos)
        self.assertIn("link", objetos)


class PruebasCapacidadEnLaLista(unittest.TestCase):
    def test_es_veintiseis(self):
        self.assertEqual(len(CAPACIDADES_NUCLEO), 26)  # + conexiones: conectar, desconectar y estado

    def test_esta_junto_a_su_hermana_de_escritura(self):
        orden = [c.nombre for c in CAPACIDADES_NUCLEO]
        self.assertIn(ACCION, orden)
        self.assertEqual(orden.index(ACCION),
                         orden.index("guardar_sitio_web") + 1)

    def test_no_es_herramienta_del_banco(self):
        #: Es una puerta de navegación, no una herramienta que el modelo deba
        #: conocer: el banco sigue en sus 36 descriptores.
        from contratos.herramienta import HERRAMIENTAS_DEL_NUCLEO
        from herramientas.internas import manifest_tools as tm
        self.assertNotIn(ACCION, HERRAMIENTAS_DEL_NUCLEO)
        self.assertNotIn(ACCION,
                         {entrada["name"] for entrada in tm.MANIFEST})


class PruebasPanel(unittest.TestCase):
    """La puerta ya no es un navegador: es el `menuData` del overlay."""

    SITIOS = [{"nombre": "Banco", "url": "https://mi-banco.com"}]

    def test_levantar_el_panel_manda_la_lista_al_overlay(self):
        nucleo = _nucleo_de_menues()
        nucleo._almacen_sitios_web = Mock(return_value=_almacen(self.SITIOS))
        DarkNucleo._mostrar_menu_sitios(nucleo)
        payload = _ultimo_payload(nucleo)
        self.assertTrue(payload["sitiosVisible"])
        self.assertEqual(payload["sitiosData"], self.SITIOS)

    def test_la_lista_se_relee_en_cada_apertura(self):
        #: No hay caché: lo que se guardó hace un minuto tiene que aparecer sin
        #: reiniciar el Núcleo.
        nucleo = _nucleo_de_menues()
        almacen = Mock()
        almacen.listar.side_effect = [[], self.SITIOS]
        nucleo._almacen_sitios_web = Mock(return_value=almacen)
        DarkNucleo._mostrar_menu_sitios(nucleo)
        DarkNucleo._mostrar_menu_sitios(nucleo)
        self.assertEqual(_ultimo_payload(nucleo)["sitiosData"], self.SITIOS)
        self.assertEqual(almacen.listar.call_count, 2)

    def test_abrir_sitios_no_apaga_los_otros_dos_menues(self):
        #: Los tres viajan en el mismo payload. Con un mostrador que escribiera su
        #: diccionario a mano, abrir sitios habría borrado recursos y tareas.
        nucleo = _nucleo_de_menues(recursos_visible=True,
                                   recursos_data={"discos": []},
                                   tareas_visible=True, tareas_data=[])
        nucleo._almacen_sitios_web = Mock(return_value=_almacen(self.SITIOS))
        DarkNucleo._mostrar_menu_sitios(nucleo)
        payload = _ultimo_payload(nucleo)
        self.assertTrue(payload["recursosVisible"])
        self.assertEqual(payload["recursosData"], {"discos": []})
        self.assertTrue(payload["tareasVisible"])
        self.assertEqual(payload["tareasData"], [])
        self.assertTrue(payload["sitiosVisible"])

    def test_esconder_sitios_deja_los_otros_dos_levantados(self):
        nucleo = _nucleo_de_menues(recursos_visible=True,
                                   recursos_data={"discos": []},
                                   sitios_visible=True, sitios_data=self.SITIOS)
        DarkNucleo._esconder_menu_sitios(nucleo)
        payload = _ultimo_payload(nucleo)
        self.assertIsNone(payload["sitiosData"])
        self.assertFalse(payload["sitiosVisible"])
        #: El flag interno también: si no, el siguiente latido revivaría el panel.
        self.assertFalse(nucleo._menu_sitios_visible)
        self.assertTrue(payload["recursosVisible"])

    def test_sin_bandera_no_viaja_la_lista(self):
        #: Un latido con el panel cerrado no puede llevar la lista vieja: el frente
        #: pintaría sitios que el usuario ya no está viendo.
        nucleo = _nucleo_de_menues(sitios_data=self.SITIOS)
        self.assertIsNone(nucleo._menu_payload()["sitiosData"])

    def test_el_payload_lleva_los_tres_menues(self):
        nucleo = _nucleo_de_menues()
        self.assertEqual(
            set(nucleo._menu_payload()),
            {"recursosVisible", "tareasVisible", "sitiosVisible",
             "rostroVisible", "recursosData", "tareasData", "sitiosData",
             "rostroData", "centroVisible", "centroData"})

    def test_la_accion_llama_al_panel_y_no_al_navegador(self):
        nucleo = _nucleo_de_menues()
        nucleo._mostrar_menu_sitios = Mock()
        # El núcleo ya no importa `webbrowser`: lo parcheado es el módulo, que
        # es el mismo objeto que usa el dueño de capacidades.
        with patch("webbrowser.open", return_value=True) as abrir:
            mensaje = DarkNucleo.abrir_pagina_sitios(nucleo)
        nucleo._mostrar_menu_sitios.assert_called_once_with()
        abrir.assert_not_called()
        self.assertIn("sitios", mensaje)

    def test_el_navegador_no_sale_en_el_lector_de_sitios(self):
        fuente = inspect.getsource(DarkNucleo.abrir_pagina_sitios)
        self.assertNotIn("webbrowser", fuente)

    def test_la_url_de_la_pagina_desaparecio_del_nucleo(self):
        #: `86eedb11` publicó `PAGINA_SITIOS_URL` y esta prueba la importaba. Se
        #: retiró a propósito, así que se pina su ausencia en vez de su valor.
        fuente = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
            encoding="utf-8")
        self.assertNotIn("PAGINA_SITIOS_URL", fuente)

    def test_guardar_con_el_panel_abierto_lo_relee(self):
        nucleo = _nucleo_de_menues(sitios_visible=True)
        nucleo._almacen_sitios_web = Mock(
            return_value=Mock(guardar=Mock(return_value="config/sitios_web.json")))
        nucleo._mostrar_menu_sitios = Mock()
        DarkNucleo._accion_sitio_web(
            nucleo, {"nombre": "Banco", "url": "https://mi-banco.com"}, "127.0.0.1")
        nucleo._mostrar_menu_sitios.assert_called_once_with()

    def test_guardar_con_el_panel_cerrado_no_lo_levanta(self):
        nucleo = _nucleo_de_menues()
        nucleo._almacen_sitios_web = Mock(
            return_value=Mock(guardar=Mock(return_value="config/sitios_web.json")))
        nucleo._mostrar_menu_sitios = Mock()
        DarkNucleo._accion_sitio_web(
            nucleo, {"nombre": "Banco", "url": "https://mi-banco.com"}, "127.0.0.1")
        nucleo._mostrar_menu_sitios.assert_not_called()

    def test_desde_otra_maquina_no_se_levanta_nada(self):
        #: La compuerta sigue siendo el origen: un `sitio_web` remoto se descarta
        #: sin tocar el almacén ni el overlay.
        nucleo = _nucleo_de_menues(sitios_visible=True)
        nucleo._almacen_sitios_web = Mock()
        nucleo._mostrar_menu_sitios = Mock()
        guardado = DarkNucleo._accion_sitio_web(
            nucleo, {"nombre": "X", "url": "https://x.com"}, "192.168.1.9")
        self.assertIsNone(guardado)
        nucleo._almacen_sitios_web.assert_not_called()
        nucleo._mostrar_menu_sitios.assert_not_called()


class PruebasComandoDelOverlay(unittest.TestCase):
    """El panel se abre y se cierra con las frases del menú, sin modelo."""

    def setUp(self):
        #: `_match_comando_menu` solo lee `MENU_COMANDOS`: no necesita Núcleo vivo.
        self.nucleo = DarkNucleo.__new__(DarkNucleo)

    def test_las_frases_de_abrir_y_esconder(self):
        for frase, esperado in (
            ("mis sitios", "sitios"),
            ("panel de sitios", "sitios"),
            ("abre sitios", "sitios"),
            ("dime mis sitios", "sitios"),
            ("esconde sitios", "esconder_sitios"),
            ("ocultar sitios", "esconder_sitios"),
            ("cerrar sitios", "esconder_sitios"),
            ("esconder mis sitios", "esconder_sitios"),
        ):
            with self.subTest(frase=frase):
                self.assertEqual(self.nucleo._match_comando_menu(frase), esperado)

    def test_la_frase_larga_gana_a_la_corta(self):
        #: «esconder mis sitios» contiene «mis sitios». Sin el desempate por
        #: longitud, esconder el panel lo volvería a abrir.
        self.assertEqual(
            self.nucleo._match_comando_menu("esconder mis sitios"),
            "esconder_sitios")

    def test_ejecutar_lleva_el_comando_al_panel(self):
        nucleo = _nucleo_de_menues()
        nucleo._mostrar_menu_sitios = Mock()
        nucleo._esconder_menu_sitios = Mock()
        DarkNucleo._ejecutar_comando_menu(nucleo, "sitios")
        nucleo._mostrar_menu_sitios.assert_called_once_with()
        DarkNucleo._ejecutar_comando_menu(nucleo, "esconder_sitios")
        nucleo._esconder_menu_sitios.assert_called_once_with()

    def test_esconder_todo_apaga_tambien_los_sitios(self):
        nucleo = _nucleo_de_menues(recursos_visible=True, tareas_visible=True,
                                   sitios_visible=True)
        DarkNucleo._esconder_todos_menus(nucleo)
        payload = _ultimo_payload(nucleo)
        for bandera in ("recursosVisible", "tareasVisible", "sitiosVisible"):
            self.assertFalse(payload[bandera], bandera)

    def test_una_busqueda_no_levanta_el_panel(self):
        #: «sitios» a secas está fuera de la tabla a propósito: `_corregir_difuso`
        #: perdona la corrección difusa a TODO texto que contenga una frase de
        #: MENU_COMANDOS, y una sola palabra se habría comido «busca sitios de
        #: camping».
        self.assertIsNone(
            self.nucleo._match_comando_menu("busca sitios de camping"))
        for frase in MENU_COMANDOS["sitios"] + MENU_COMANDOS["esconder_sitios"]:
            self.assertGreaterEqual(len(frase.split()), 2, frase)

    def test_el_despachador_conoce_la_accion(self):
        fuente = inspect.getsource(DarkNucleo._despachar_intencion)
        self.assertIn(ACCION, fuente)


if __name__ == "__main__":
    unittest.main()
