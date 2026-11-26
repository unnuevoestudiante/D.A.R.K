"""`investigar` no puede servir su propio fallo como material de síntesis.

`investigar` busca, y con los mismos resultados de esa búsqueda pide el
contenido extendido (V11: reutilizar las fuentes en vez de repetir la
consulta). Lo pide por `investigar_a_fondo`, que es la versión pensada para el
dispatcher: cuando `_investigar_interno` no saca ni una fuente, esa versión
devuelve la cadena `"No encontré resultados."` —y con razón, porque un paso que
devuelve `""` el normalizador lo lee como éxito.

Pero dentro de `investigar` ese valor no es un paso: es **material**. La
secuencia, en la ruta viva de «busca X»:

  1. `_buscar_resultados_web` devuelve tres resultados.
  2. `_investigar_interno` descarta los tres (ningún título comparte palabra con
     la consulta) y devuelve `None`: sin fuentes no hay contenido extendido.
  3. `investigar_a_fondo` convierte el `None` en `"No encontré resultados."`.
  4. `if investigacion:` es verdadero, así que el prompt lleva
     `Contenido investigado:\nNo encontré resultados.`

O sea: se le dice al modelo que no hay resultados, y encima como dato. El
sistema le pide que no invente y que trate las fuentes como datos.

Las cinco reglas que vigila este archivo:

  * **el `None` no se convierte en texto**: `investigar` llama a
    `_investigar_interno`, cuya ausencia de material es ausencia.
  * **el material verdadero sí entra**: cuando las fuentes coinciden con el
    tema, el prompt sigue llevando el contenido extendido; el corte no es un
    modo silencio.
  * **la reutilización de V11 se mantiene**: una sola `_buscar_resultados_web`
    por turno y el contenido se forma con las tres primeras, pasadas por
    argumento.
  * **la envoltura del dispatcher no se desarma**: `investigar_a_fondo` sigue
    devolviendo un fallo legible, no `""`.
  * **las fuentes ya traídas no se recompran**: con `resultados` por argumento,
    `_buscar_resultados_web` no se llama y el texto se pide con esa URL.

Ref: herramientas/internas/ejecutor.py.
"""
from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402

FALLO = "No encontré resultados."


class FakeProvider:
    """Captura el prompt y responde, para poder leer qué se le dio al modelo."""

    def __init__(self, contenido="Una síntesis breve."):
        self.peticiones = []
        self._contenido = contenido

    def complete(self, request, timeout=None):
        self.peticiones.append(request)
        return SimpleNamespace(status_code=200, content=self._contenido)

    @property
    def prompt(self):
        return self.peticiones[-1].messages[1]["content"]


def _fuente(n, titulo):
    return {"title": titulo, "body": f"Fragmento {n}",
            "href": f"https://ejemplo.test/{n}"}


class _Base(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.e = EjecutorHerramientas(servicios=Servicios(
            llm=self.provider,
            hablar=lambda texto: None,
            estado_overlay=lambda: "idle",
        ))

    def con_resultados(self, resultados):
        self.e._buscar_resultados_web = Mock(return_value=resultados)
        return self.e

    def sintetiza(self, query):
        self.e.investigar(query)
        return self.provider.prompt


class PruebaFalloNoEsMaterial(_Base):
    def test_el_prompt_no_lleva_el_fallo_como_material(self):
        """Tres títulos sin ninguna palabra en común con la consulta: `_investigar_interno`
        devuelve None y no hay contenido extendido que añadir."""
        self.con_resultados([_fuente(n, f"Página {n}") for n in (1, 2, 3)])
        prompt = self.sintetiza("perros")

        self.assertNotIn(FALLO, prompt)
        self.assertNotIn("Contenido investigado:", prompt)

    def test_sin_coincidencia_no_se_busca_dos_veces(self):
        """El descarte ocurre dentro de `_investigar_interno`, que recibe las
        fuentes ya traídas: pedir la consulta otra vez sería el bug de V11."""
        self.con_resultados([_fuente(n, f"Página {n}") for n in (1, 2, 3)])
        self.sintetiza("perros")

        self.e._buscar_resultados_web.assert_called_once_with(
            "perros", max_results=5)


class PruebaMaterialQueSiEntra(_Base):
    def test_el_contenido_extendido_sigue_llegando_al_modelo(self):
        """Con títulos que coinciden con el tema hay material: el corte no puede
        silenciarlo, o la síntesis perdería justo lo que la hace valer."""
        self.con_resultados([_fuente(n, f"perros de agua {n}")
                             for n in (1, 2, 3)])
        with patch.object(self.e, "_obtener_texto_pagina",
                          return_value="Texto de la página."):
            prompt = self.sintetiza("perros")

        self.assertIn("Contenido investigado:", prompt)
        self.assertIn("Texto de la página.", prompt)
        self.assertNotIn(FALLO, prompt)

    def test_el_material_se_forma_con_las_tres_primeras(self):
        resultados = [_fuente(n, f"perros {n}") for n in range(1, 6)]
        self.con_resultados(resultados)
        interno = Mock(return_value="Material.")
        with patch.object(self.e, "_investigar_interno", interno):
            self.sintetiza("perros")

        interno.assert_called_once_with("perros", num_fuentes=3,
                                       resultados=resultados[:3])


class PruebaEnvolturaDelDispatcher(_Base):
    def test_sin_fuentes_la_envoltura_devuelve_un_fallo_legible(self):
        """`investigar_a_fondo` es la cara que ve quien normaliza el resultado:
        ahí `""` sería éxito, así que el `None` sigue traduciéndose."""
        self.con_resultados([])
        self.assertEqual(FALLO, self.e.investigar_a_fondo("perros"))

    def test_con_material_la_envoltura_lo_devuelve_inalterado(self):
        self.con_resultados([_fuente(1, "perros de agua")])
        with patch.object(self.e, "_obtener_texto_pagina",
                          return_value="Texto."):
            self.assertIn("Texto.", self.e.investigar_a_fondo("perros"))


class PruebaFuentesYaTraidas(unittest.TestCase):
    """El otro lado de V11: cuando las fuentes ya vienen por argumento, nadie
    repite la consulta. Esta prueba vivía sobre la copia del núcleo
    (`test_pipeline.py`); con la isla web borrada, el ejecutor es el único sitio
    donde puede romperse."""

    def setUp(self):
        self.e = EjecutorHerramientas(servicios=Servicios(
            hablar=lambda texto: None, estado_overlay=lambda: "idle"))

    def test_con_fuentes_traidas_no_se_vuelve_a_buscar(self):
        self.e._buscar_resultados_web = Mock()
        self.e._obtener_texto_pagina = Mock(return_value="Texto de la página")

        material = self.e.investigar_a_fondo(
            "biografía de Einstein", num_fuentes=3, resultados=[{
                "title": "Biografía de Einstein",
                "href": "https://ejemplo.test/einstein",
                "body": "Fragmento de respaldo",
            }])

        self.assertIn("Texto de la página", material)
        self.e._buscar_resultados_web.assert_not_called()
        self.e._obtener_texto_pagina.assert_called_once_with(
            "https://ejemplo.test/einstein")


if __name__ == "__main__":
    unittest.main()
