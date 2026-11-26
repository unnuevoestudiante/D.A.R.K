"""El velo: la oscuridad del fondo del overlay se baja con una frase del usuario.

Ref: `dark_python/overlay/fachada.py::velo`, `modulos/dark_overlay_bridge.py::set_veil_bajado`,
`nucleo/intenciones/gestor.py::_RE_VELO_*`, `nucleo/dark_nucleo.py::MENU_COMANDOS`.

Lo que se prueba aquí es la cadena entera, porque el corte se puede romper en
cualquiera de los cuatro tramos: la frase no llega a `tipo_menu`, el comando no
llama al puerto, el puente no publica la clave, o la publica y `/tv` se la lleva
a la tele, que no tiene escritorio detrás.

Y se prueba el vecino incómodo: «sube el velo» es hoy una orden de música
(`ajustar_volumen_musica`, confianza 1,0). El velo no le roba esa frase, así que
la vuelta a la oscuridad se pide con «levanta el velo» y sus pares.

Solo stdlib más el puente construido con `__new__` (sin puertos ni hilos).
"""
from __future__ import annotations

import inspect
import pathlib
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from modulos.dark_overlay_bridge import OverlayBridge  # noqa: E402
from nucleo.dark_nucleo import MENU_COMANDOS, DarkNucleo  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
)
from overlay.fachada import FachadaOverlay  # noqa: E402

BAJAR = (
    "dejame ver el escritorio",
    "déjame ver el escritorio",
    "quiero ver el escritorio",
    "que vea el escritorio",
    "que pueda ver el escritorio",
    "dejame ver el desktop",
    "baja el velo",
    "quita el velo",
)

SUBIR = (
    "levanta el velo",
    "vuelve el velo",
    "regresa el velo",
    "oscurece el fondo",
    "oscurece el velo",
    "tapa el escritorio",
)


def nucleo_doble():
    """DarkNucleo con `__new__`: solo lo que toca el comando del velo."""
    nucleo = DarkNucleo.__new__(DarkNucleo)
    nucleo.overlay = SimpleNamespace(velo=Mock(), estado=Mock(return_value="idle"))
    nucleo.speak = Mock()
    return nucleo


class PruebasFrases(unittest.TestCase):
    def test_el_camino_literal_lleva_al_comando_correcto(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        for frase in BAJAR:
            with self.subTest(frase=frase):
                self.assertEqual(
                    DarkNucleo._match_comando_menu(nucleo, frase), "velo_bajado"
                )
        for frase in SUBIR:
            with self.subTest(frase=frase):
                self.assertEqual(
                    DarkNucleo._match_comando_menu(nucleo, frase), "velo_subido"
                )

    def test_el_engine_tambien_las_reconoce_sin_la_tabla(self):
        """Las frases `parecido` no están todas en `MENU_COMANDOS`; el patrón de
        la capacidad las tiene que tomar igualmente, o la orden se quedaría en
        comentario."""
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        casos = {
            "dark, dejame ver el escritorio de una vez": "velo_bajado",
            "ahora quiero ver el escritorio completo": "velo_bajado",
            "baja el velo y ya": "velo_bajado",
            "vuelve el velo por favor": "velo_subido",
            "tapa otra vez el escritorio": "velo_subido",
        }
        for frase, esperado in casos.items():
            with self.subTest(frase=frase):
                intencion = gestor.interpretar(frase)
                self.assertEqual(intencion.action, "menu")
                valor = intencion.parametros["tipo_menu"].valor
                self.assertEqual(valor, esperado)

    def test_sube_el_velo_sigue_siendo_de_musica(self):
        """La colisión medida: esta frase ya era de `ajustar_volumen_musica` con
        confianza 1,0 antes del velo y ahí se queda."""
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        self.assertIsNone(
            DarkNucleo._match_comando_menu(DarkNucleo.__new__(DarkNucleo),
                                           "sube el velo")
        )
        self.assertEqual(
            gestor.interpretar("sube el velo").action, "ajustar_volumen_musica"
        )
        self.assertNotIn("sube el velo", MENU_COMANDOS["velo_subido"])
        self.assertNotIn("sube el velo", MENU_COMANDOS["velo_bajado"])

    def test_bajar_el_volumen_no_baja_el_velo(self):
        """Las dos frases comparten verbo y estructura; si el patrón del velo se
        afloja, la música pierde su orden más usada."""
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        for frase in ("baja el volumen", "sube el volumen", "cambia el fondo"):
            with self.subTest(frase=frase):
                self.assertNotIn(
                    DarkNucleo._match_comando_menu(
                        DarkNucleo.__new__(DarkNucleo), frase
                    ),
                    ("velo_bajado", "velo_subido"),
                )
                self.assertNotEqual(
                    gestor.interpretar(frase).action, "menu"
                )


class PruebasEjecucion(unittest.TestCase):
    def test_bajar_el_velo_llama_al_puerto_con_true(self):
        nucleo = nucleo_doble()

        DarkNucleo._ejecutar_comando_menu(nucleo, "velo_bajado", "baja el velo")

        nucleo.overlay.velo.assert_called_once_with(True)
        nucleo.speak.assert_called_once()

    def test_subir_el_velo_llama_al_puerto_con_false(self):
        nucleo = nucleo_doble()

        DarkNucleo._ejecutar_comando_menu(nucleo, "velo_subido", "levanta el velo")

        nucleo.overlay.velo.assert_called_once_with(False)

    def test_ningun_estado_del_overlay_toca_el_velo(self):
        """Lo escribe una orden del usuario o no lo escribe nadie. Un `pintar`, un
        reposo o un `idle` que lo subiera devolvería el negro encima de alguien
        que está mirando el escritorio."""
        origen = inspect.getsource(OverlayBridge)
        self.assertEqual(
            len(re.findall(r'self\._state\["veilLowered"\] =', origen)),
            1,
            "hay más de un sitio del puente que escribe el velo",
        )
        # La fachada no pinta: delega. Si algún día decide acompañar el velo con
        # un `pintar`, ahí estaría el robo de la decisión al usuario.
        fuente_velo = inspect.getsource(FachadaOverlay.velo)
        self.assertIn("self.bridge.set_veil_bajado(bajado)", fuente_velo)
        self.assertEqual(
            fuente_velo.count("self.bridge."),
            1,
            "la fachada hace más cosas además de delegar el velo",
        )


class PruebasPuente(unittest.TestCase):
    def bridge_inerte(self):
        puente = OverlayBridge.__new__(OverlayBridge)
        puente._state = {
            "state": "idle",
            "text": None,
            "menuData": None,
            "resultsData": None,
            "level": 0.0,
            "desktopShown": False,
            "veilLowered": False,
        }
        puente._emitidos = 0
        puente._broadcast = lambda: setattr(puente, "_emitidos", puente._emitidos + 1)
        return puente

    def test_nace_con_el_velo_subido(self):
        """Sin orden del usuario el campo es opaco: el `False` tiene que estar en
        el estado inicial, no ausente."""
        origen = inspect.getsource(OverlayBridge.__init__)
        self.assertIn('"veilLowered": False', origen)

    def test_la_guarda_de_cambio_emite_una_vez(self):
        puente = self.bridge_inerte()

        puente.set_veil_bajado(True)
        puente.set_veil_bajado(True)

        self.assertTrue(puente._state["veilLowered"])
        self.assertEqual(puente._emitidos, 1)

        puente.set_veil_bajado(False)
        self.assertEqual(puente._emitidos, 2)

    def test_tv_no_recibe_el_velo(self):
        """La tele no tiene un escritorio detrás de su ventana: bajarle el fondo
        por esta señal sería aclararle la interfaz sin nada que aclarar."""
        for activa in (False, True):
            with self.subTest(senal=activa):
                puente = self.bridge_inerte()
                puente.senal_tv_activa = lambda: activa
                puente._destino_ui = "pc"
                puente._tv_ui_state = "listening"
                puente._tv_ui_ts = 0.0
                puente._silenciado = False

                estado = puente.estado_para_tv()

                self.assertNotIn("veilLowered", estado)
                self.assertNotIn("desktopShown", estado)


class PruebasFachada(unittest.TestCase):
    def test_el_velo_de_la_fachada_delega_en_el_puente(self):
        puente = Mock()
        fachada = FachadaOverlay(puente)

        fachada.velo(True)
        fachada.velo(False)

        self.assertEqual(
            puente.set_veil_bajado.call_args_list,
            [((True,), {}), ((False,), {})],
        )


if __name__ == "__main__":
    unittest.main()
