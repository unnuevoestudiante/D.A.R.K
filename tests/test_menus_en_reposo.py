"""El reposo no cierra un menú que el usuario abrió.

Lo que pasó en caja real: «dark, quiero agregar un sitio nuevo» se interpretó
(`[INTENT_TRACE] action=abrir_pagina_sitios confidence=1.000`), el Núcleo metió
`sitiosVisible` en el payload y D.A.R.K contestó, y sin embargo no se pintó nada.
El culpable es una regla del puente anterior al panel de sitios:
`set(..., state="idle")` limpia `menuData`. Como el reposo diferido
(`overlay/config.py`, `REPOSO_DIFERIDO_SEG`) dispara un `pintar("idle")` a los
pocos segundos de cada turno, cualquier menú abierto se borraba solo: con
recursos y tareas el latido de 5 s los volvía a pintar, así que era un parpadeo;
el panel de sitios no tiene latido —su lista solo cambia cuando se escribe—, así
que era un apagón.

Un menú abierto es una superficie donde el usuario va a escribir. Cerrarlo porque
nadie dijo nada durante unos segundos es lo contrario de lo que significa
abrirlo. Desde aquí la regla es: idle limpia resultados, texto y nivel, y limpia
el menú **salvo que el propio payload diga que hay uno abierto**. Cerrarlo sigue
siendo explícito —`_esconder_menu_*` pinta las banderas en falso, y `silenciar()`
(apagar la interfaz) barre el payload entero—.

Solo stdlib: el puente se construye con `__new__`, sin abrir puertos ni hilos.
"""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from modulos.dark_overlay_bridge import OverlayBridge  # noqa: E402

MENU_VACIO = {
    "recursosVisible": False,
    "tareasVisible": False,
    "sitiosVisible": False,
    "recursosData": None,
    "tareasData": None,
    "sitiosData": None,
}


def puente_inerte():
    """`OverlayBridge` sin servidor: solo el diccionario de estado y el emisor."""
    b = OverlayBridge.__new__(OverlayBridge)
    b._state = {
        "state": "idle", "text": None, "menuData": None,
        "resultsData": None, "progress": None, "level": 0.0,
    }
    b._silenciado = False
    b._destino_ui = "pc"
    b._tv_ui_state = None
    b._tv_ui_ts = 0.0
    b._tv_cerrar_tras_speak = False
    b.emitidos = []
    b._broadcast = lambda: b.emitidos.append(b._state.get("menuData"))
    return b


def menu_con(bandera):
    payload = dict(MENU_VACIO)
    payload[bandera] = True
    return payload


class PruebasReposoConMenuAbierto(unittest.TestCase):
    def test_idle_con_menu_nuevo_no_borra_el_panel_de_sitios(self):
        b = puente_inerte()
        b.set("idle", menu_data=menu_con("sitiosVisible"))
        self.assertTrue(b._state["menuData"]["sitiosVisible"])

    def test_idle_con_menu_nuevo_no_borra_los_otros_dos(self):
        for bandera in ("recursosVisible", "tareasVisible"):
            with self.subTest(bandera=bandera):
                b = puente_inerte()
                b.set("idle", menu_data=menu_con(bandera))
                self.assertTrue(b._state["menuData"][bandera])

    def test_el_reposo_llega_despues_de_abrir_y_deja_el_menu_vivo(self):
        """El menú se pinta con el estado del turno y el reposo llega después,
        como un `set("idle")` suelto. Era el caso que mataba el panel."""
        b = puente_inerte()
        b.set("thinking", menu_data=menu_con("sitiosVisible"))
        b.set("speaking", text="Aquí tienes tus sitios.")
        b.set("idle")
        self.assertTrue(b._state["menuData"]["sitiosVisible"])

    def test_idle_sigue_limpiando_lo_demas(self):
        """El reposo sigue siendo reposo: resultados, texto y nivel se van."""
        b = puente_inerte()
        b.set("showing_results", results_data={"items": [{"url": "x"}]})
        b.set("speaking", text="mira", level=0.8,
              menu_data=menu_con("sitiosVisible"))
        b.set("idle")
        self.assertIsNone(b._state["resultsData"])
        self.assertIsNone(b._state["text"])
        self.assertEqual(b._state["level"], 0.0)
        self.assertEqual(b._state["state"], "idle")


class PruebasCerrarEsExplicito(unittest.TestCase):
    def test_el_payload_sin_ningun_menu_abierto_si_se_borra_en_idle(self):
        b = puente_inerte()
        b.set("speaking", menu_data=dict(MENU_VACIO))
        b.set("idle")
        self.assertIsNone(b._state["menuData"])

    def test_cerrar_el_menu_deja_de_estar_abierto_aun_sin_reposo(self):
        """`_esconder_menu_sitios` pinta las banderas en falso: eso es cerrar.

        Con el puente ya en reposo el payload se va a None —nada abierto es nada
        que pintar—, así que la prueba mira la señal, no el continente.
        """
        b = puente_inerte()
        b.set("listening", menu_data=menu_con("sitiosVisible"))
        b.set("listening", menu_data=dict(MENU_VACIO))
        self.assertFalse(bool((b._state["menuData"] or {}).get("sitiosVisible")))
        b.set("idle")
        self.assertIsNone(b._state["menuData"])

    def test_un_menu_heredado_se_borra_al_pintar_idle_sin_payload(self):
        """Si el payload que queda dice que no hay nada abierto, idle limpia."""
        b = puente_inerte()
        b.set("idle", menu_data=dict(MENU_VACIO))
        b.set("idle")
        self.assertIsNone(b._state["menuData"])

    def test_silenciar_si_barre_el_menu_abierto(self):
        """Apagar la interfaz no es reposar: ahí el menú sí se va."""
        b = puente_inerte()
        b.set("idle", menu_data=menu_con("sitiosVisible"))
        b.silenciar()
        self.assertIsNone(b._state["menuData"])


class PruebasFormatosQueNoSonMenu(unittest.TestCase):
    def test_un_menuData_que_no_es_dict_no_rompe_el_reposo(self):
        b = puente_inerte()
        b._state["menuData"] = "basura"
        b.set("idle")
        self.assertIsNone(b._state["menuData"])

    def test_un_dict_sin_banderas_se_considera_menu_cerrado(self):
        b = puente_inerte()
        b._state["menuData"] = {"sitiosData": [{"nombre": "Banco"}]}
        b.set("idle")
        self.assertIsNone(b._state["menuData"])

    def test_el_estado_del_reposo_no_depende_de_que_haya_navegador(self):
        """Que el menú sobreviva no cambia en qué estado queda el puente."""
        b = puente_inerte()
        b.set("idle", menu_data=menu_con("tareasVisible"))
        self.assertEqual(b.estado(), "idle")
        self.assertTrue(b._state["menuData"]["tareasVisible"])


class PruebasLaListaDeMenus(unittest.TestCase):
    """El puente decide qué es «menú abierto» por una lista de tres claves. Si el
    Núcleo añade una cuarta y el puente no se entera, ese menú nuevo morirá en
    cada reposo igual que murió el de sitios: la prueba ata las dos vistas."""

    def test_todo_menu_del_payload_esta_en_la_lista_del_puente(self):
        from modulos.dark_overlay_bridge import MENUS_ABIERTOS
        from nucleo.dark_nucleo import DarkNucleo

        nucleo = DarkNucleo.__new__(DarkNucleo)
        import threading

        nucleo._menu_lock = threading.Lock()
        nucleo._menu_recursos_visible = False
        nucleo._menu_recursos_data = None
        nucleo._menu_tareas_visible = False
        nucleo._menu_tareas_data = None
        nucleo._menu_sitios_visible = False
        nucleo._menu_sitios_data = None
        banderas = [
            clave
            for clave in DarkNucleo._menu_payload(nucleo)
            if clave.endswith("Visible")
        ]
        self.assertTrue(banderas)
        for bandera in banderas:
            with self.subTest(bandera=bandera):
                self.assertIn(bandera, MENUS_ABIERTOS)


class PruebasElPactoEsteEscrito(unittest.TestCase):
    """La política de idle vive en el contrato del puerto: si se cambia aquí y
    no allí, la siguiente capa que lea `contratos/overlay.py` la va a negar."""

    def test_el_contrato_declara_que_un_menu_abierto_sobrevive(self):
        fuente = (DARK_PYTHON / "contratos" / "overlay.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("un menú abierto", fuente)
