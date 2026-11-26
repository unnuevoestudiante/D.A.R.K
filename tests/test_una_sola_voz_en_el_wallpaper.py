"""El wallpaper se dice una sola vez, y lo dice la copia que lo ejecuta.

Medido en HEAD con la cadena real (banco → `EspecialistaComunicacion`), sin
mockear el banco:

  1. `tool_instalar_wallpaper_indice` habla su frase de identidad por el
     `speak_cb` que el núcleo cablea en `dark_nucleo.py:785` y **además**
     devuelve la frase canónica (`_decir_frase` + `return`, tres ramas:
     sin imagen, éxito y fallo).
  2. La vía del clic (`_seleccionar_resultado_ui`) narraba ese retorno con
     `hablar=True`. La de la voz detectada (`_ejecutar_accion_imagenes`) lo
     narraba con su propio `self.speak(msg)`. Dos voces, dos redacciones para
     el mismo hecho: «Ya quedó el nuevo fondo señor…» y
     «Fondo de pantalla actualizado.».
  3. La vía del modelo (`accion_imagenes` → dueño de capacidades) habla una:
     su hoja llama a `speak()` y el paso se arma con `_ya_hablado`, que deja el
     mensaje vacío. Esa es la política que se copia aquí.

Lo elegido: se queda la frase de identidad, que es la que tiene voz propia, y
el núcleo deja de narrar ese retorno. El texto canónico **sigue viajando** en
`paso.mensaje` porque las puertas de ocultar las tarjetas lo miran con
`startswith("Fondo de pantalla actualizado")`.

Las cuatro reglas que vigila este archivo:

  * una voz por ruta, y es una de `FRASES`, no la frase del sistema;
  * el retorno sigue siendo el canónico (la puerta de las tarjetas no se cae);
  * la rama de descarga no pierde su única voz — allí la copia calla y quien
    narra es el núcleo, así que bajarle el `hablar` sería silenciarla;
  * sin `speak_cb` no hay voces, pero el texto no se pierde: está en el paso.

Ref: especialistas/especialista_comunicacion.py, nucleo/dark_nucleo.py,
nucleo/identidades/frases.py.
"""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from especialistas.especialista_comunicacion import (  # noqa: E402
    EspecialistaComunicacion,
)
from herramientas.fabrica import crear_banco  # noqa: E402
from nucleo import sesion_resultados  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402
from nucleo.identidades.frases import FRASES  # noqa: E402
FRASE_WALLPAPER_OK = FRASES["wallpaper_ok"]
FRASE_WALLPAPER_ERROR = FRASES["wallpaper_error"]
FRASE_IMAGEN_NO_VALIDA = FRASES["imagen_no_valida"]

FRASE_CANONICA = "Fondo de pantalla actualizado."
TARJETA = {"url": "https://x.test/1.jpg", "title": "uno",
           "thumbnail": "https://x.test/1.jpg"}
TARJETA_SIN_URL = {"url": "", "title": "vacia", "thumbnail": ""}


class HttpSinRed:
    """Corta la red de la sonda: cualquier descarga es un fallo con texto."""

    def get(self, url, **kwargs):
        raise RuntimeError("sin red en la sonda")


class PruebaUnaSolaVoz(unittest.TestCase):
    def setUp(self):
        self.voces = []
        self.sesion = sesion_resultados.crear_sesion_resultados()
        self.sesion.resultados_visuales = [dict(TARJETA)]
        self.sesion.intencion_imagenes = "wallpaper"
        self.esp = EspecialistaComunicacion(
            http_session=HttpSinRed(),
            speak_cb=self.voces.append,
            sesion=self.sesion,
        )
        self.banco = crear_banco(
            especialistas={"comunicacion": self.esp},
            núcleo=SimpleNamespace(),
        )
        self.capacidades = Mock()

        n = DarkNucleo.__new__(DarkNucleo)
        n._sesion_cache = self.sesion
        n.speak = lambda texto: self.voces.append(texto)
        n._modo_bloqueado = False
        n._banco_herramientas = lambda: self.banco
        n._capacidades_herramientas = lambda: self.capacidades
        n._puede_usar = Mock(return_value=None)
        n._herramienta_requiere_confirmacion = Mock(return_value=False)
        n.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))
        n._tracer = NullTracer()
        self.nucleo = n

    def instalar_ok(self):
        return patch.object(self.esp, "instalar_wallpaper",
                            Mock(return_value={"ok": True,
                                               "mensaje": FRASE_CANONICA}))

    # -- la vía del clic -------------------------------------------------
    def test_el_clic_de_wallpaper_habla_una_sola_vez(self):
        with self.instalar_ok(), patch("builtins.print"):
            paso = DarkNucleo._seleccionar_resultado_ui(
                self.nucleo, 0, "wallpaper")

        self.assertEqual(1, len(self.voces),
                         f"el clic de wallpaper habló {len(self.voces)} veces: "
                         f"{self.voces}")
        self.assertIn(self.voces[0], FRASE_WALLPAPER_OK)

    def test_el_clic_de_wallpaper_devuelve_la_frase_canonica(self):
        """La puerta de las tarjetas mira el retorno, no la voz."""
        with self.instalar_ok(), patch("builtins.print"):
            paso = DarkNucleo._seleccionar_resultado_ui(
                self.nucleo, 0, "wallpaper")

        self.assertTrue(paso.mensaje.startswith("Fondo de pantalla actualizado"))
        self.capacidades._ocultar_resultados_visuales.assert_called_once_with()

    def test_el_fallo_del_clic_habla_una_sola_vez(self):
        with patch("builtins.print"):
            paso = DarkNucleo._seleccionar_resultado_ui(self.nucleo, 0,
                                                        "wallpaper")

        self.assertEqual(1, len(self.voces),
                         f"el fallo habló {len(self.voces)} veces: {self.voces}")
        self.assertIn(self.voces[0], FRASE_WALLPAPER_ERROR)
        self.assertEqual("fallo", paso.estado)
        self.capacidades._ocultar_resultados_visuales.assert_not_called()

    # -- la vía de la voz detectada --------------------------------------
    def test_la_voz_detectada_de_wallpaper_habla_una_sola_vez(self):
        accion = {"tipo": "wallpaper", "indices": [0],
                  "descargar_tambien": False}
        with self.instalar_ok(), patch("builtins.print"):
            msg = DarkNucleo._ejecutar_accion_imagenes(self.nucleo, accion)

        self.assertEqual(1, len(self.voces),
                         f"la voz detectada habló {len(self.voces)} veces: "
                         f"{self.voces}")
        self.assertIn(self.voces[0], FRASE_WALLPAPER_OK)
        self.assertEqual(FRASE_CANONICA, msg)

    def test_la_voz_detectada_sin_nada_que_poner_habla_una_sola_vez(self):
        """El índice ya no está en la lista: lo dice la copia, una vez."""
        self.sesion.resultados_visuales = [dict(TARJETA_SIN_URL)]
        accion = {"tipo": "wallpaper", "indices": [0],
                  "descargar_tambien": False}
        with patch("builtins.print"):
            DarkNucleo._ejecutar_accion_imagenes(self.nucleo, accion)

        self.assertEqual(1, len(self.voces),
                         f"sin nada que poner habló {len(self.voces)} veces: "
                         f"{self.voces}")
        self.assertIn(self.voces[0], FRASE_IMAGEN_NO_VALIDA)

    # -- lo que NO hay que tocar -----------------------------------------
    def test_la_descarga_por_clic_sigue_hablando_una_vez(self):
        """La copia de `descargar_imagen` calla y devuelve: si aquí se baja el
        `hablar`, la rama se queda muda."""
        self.sesion.resultados_visuales = [dict(TARJETA_SIN_URL)]
        with patch("builtins.print"):
            DarkNucleo._seleccionar_resultado_ui(self.nucleo, 0, "download")

        self.assertEqual(1, len(self.voces),
                         f"la descarga habló {len(self.voces)} veces: "
                         f"{self.voces}")

    def test_la_descarga_por_voz_detectada_sigue_hablando_una_vez(self):
        accion = {"tipo": "descargar", "indices": [0],
                  "descargar_tambien": False}
        self.sesion.resultados_visuales = [dict(TARJETA_SIN_URL)]
        with patch("builtins.print"):
            DarkNucleo._ejecutar_accion_imagenes(self.nucleo, accion)

        self.assertEqual(1, len(self.voces),
                         f"la descarga por voz habló {len(self.voces)} veces: "
                         f"{self.voces}")

    def test_sin_callback_el_texto_sigue_viajando_en_el_paso(self):
        """Sin voz propia no hay audio, pero el mensaje no se pierde: viaja en
        el paso para el frente y la traza."""
        self.esp._speak_cb = None
        with self.instalar_ok(), patch("builtins.print"):
            paso = DarkNucleo._seleccionar_resultado_ui(
                self.nucleo, 0, "wallpaper")

        self.assertEqual([], self.voces)
        self.assertTrue(paso.mensaje.startswith("Fondo de pantalla actualizado"))


if __name__ == "__main__":
    unittest.main()
