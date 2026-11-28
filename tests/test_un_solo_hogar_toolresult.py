"""Un solo hogar para `ToolResult` y `PasoResultado`.

Las dos clases estuvieron definidas tres veces: en `contratos/contratos.py` (donde
la casa dice que viven), en `nucleo/dark_nucleo.py` y en
`herramientas/internas/ejecutor.py`. Los cuerpos no diferían: medido con AST
ignorando el docstring, las tres copias eran el mismo código. Lo que sí difiere
es el objeto, y el contrato se comprueba con `isinstance`.

La secuencia que lo rompe es la ruta viva, no una hipótesis:

  1. `buscar_imagenes` la ejecuta el dueño de capacidades y devuelve un
     `ToolResult` **del ejecutor**. Es la única de las seis montadas que
     devuelve uno; por eso el resto del banco nunca notó la duplicación.
  2. `DarkNucleo._ejecutar_herramienta` pasa el crudo por su
     `_normalizar_resultado`, que abre con `isinstance(raw, ToolResult)` contra
     **su** clase: False.
  3. Tampoco es dict, así que cae al ramo de texto y `str(raw)` da
     `"ToolResult(ok=False, mensaje='')"`. Ningún prefijo lo reconoce.
  4. Sale `ToolResult(True, ese_repr)`: el paso que falló se reporta como éxito
     y el mensaje que recibe el orquestador es el repr de la clase.

Las cuatro reglas que vigila este archivo:

  * **un objeto**: la clase que ve cada módulo es la de `contratos`, no una copia
    con el mismo cuerpo. Desde que el dueño perdió su dispatcher, `PasoResultado`
    no asoma por `ejecutor.py`: allí solo se forman `ToolResult`.
  * **cero definiciones locales**: con dos copias vivas, cuál se ejecuta depende
    de quién llegue antes; añadir el `import` no basta si la clase sigue definida.
  * **el crudo del dueño llega intacto** a la normalización del núcleo, y un
    fallo del ejecutor sigue siendo fallo.
  * **la ruta viva completa** (banco real → `_ejecutar_herramienta`) no pronuncia
    el repr de ninguna clase.

`ResultadoCadena` queda como está: medido, tiene un solo constructor en el
núcleo y nadie más lo construye, así que su copia no puede cruzar una frontera.

Ref: contratos/contratos.py, nucleo/dark_nucleo.py,
herramientas/internas/ejecutor.py.
"""
from __future__ import annotations

import ast
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

import contratos  # noqa: E402
import herramientas.internas.ejecutor as ejecutor_mod  # noqa: E402
import nucleo.dark_nucleo as dark_nucleo_mod  # noqa: E402
from contratos.herramienta import HERRAMIENTAS_DE_CAPACIDADES  # noqa: E402
from herramientas.fabrica import crear_banco  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas,
    Servicios,
)
from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402

RUTA_NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
RUTA_EJECUTOR = DARK_PYTHON / "herramientas" / "internas" / "ejecutor.py"
CLASES = ("ToolResult", "PasoResultado")
#: Qué módulo ve cada clase tras borrar el dispatcher del dueño. `PasoResultado`
#: solo lo forma quien arma pasos: el núcleo, que todavía traduce intenciones.
QUIEN_VE = (
    ("nucleo", "ToolResult"),
    ("ejecutor", "ToolResult"),
    ("nucleo", "PasoResultado"),
)
MODULOS = {"nucleo": dark_nucleo_mod, "ejecutor": ejecutor_mod}
FALLO = "No pude buscar imágenes de perros."


def _clases_de(ruta):
    """Los nombres de las clases definidas a nivel de módulo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return {n.name for n in arbol.body if isinstance(n, ast.ClassDef)}


class FakeDDGS:
    """Cuatro imágenes deterministas: el éxito de la ruta viva necesita que el
    buscador responda, y la entrada del banco llama a `DDGS()` como clase."""

    def __init__(self, *a, **k):
        pass

    def images(self, query, max_results=15):
        return [
            {"title": f"paisaje {i}", "image": f"https://x.test/{i}.jpg",
             "thumbnail": f"https://x.test/{i}_t.jpg", "url": "https://origen"}
            for i in range(4)
        ]


def _ejecutor():
    hablado = []
    servicios = Servicios(
        hablar=lambda texto: hablado.append(texto),
        estado_overlay=lambda: "showing_results",
    )
    return EjecutorHerramientas(servicios=servicios), hablado


class PruebaObjetoUnico(unittest.TestCase):
    def test_la_clase_que_ve_cada_modulo_es_la_de_contratos(self):
        for ruta, nombre in QUIEN_VE:
            self.assertIs(
                getattr(MODULOS[ruta], nombre), getattr(contratos, nombre),
                f"la {nombre} del {ruta} no es la de contratos")

    def test_el_dueño_ya_no_ve_pasoresultado(self):
        """El dueño ya no forma pasos: sin su dispatcher no le queda nada que
        devolver en esa clase. Si el nombre vuelve a asomar, alguien lo importó
        para algo que todavía no tiene dueño."""
        self.assertIsNone(getattr(ejecutor_mod, "PasoResultado", None),
                          "ejecutor.py vuelve a ver PasoResultado")

    def test_el_nucleo_no_redefine_ninguna_de_dos(self):
        vistas = _clases_de(RUTA_NUCLEO)
        for nombre in CLASES:
            self.assertNotIn(nombre, vistas,
                             f"dark_nucleo.py sigue definiendo {nombre}")

    def test_el_ejecutor_no_redefine_ninguna_de_dos(self):
        vistas = _clases_de(RUTA_EJECUTOR)
        for nombre in CLASES:
            self.assertNotIn(nombre, vistas,
                             f"ejecutor.py sigue definiendo {nombre}")


class PruebaIsInstanceCruzado(unittest.TestCase):
    """El `ToolResult` del dueño tiene que ser reconocible por el núcleo."""

    def nucleo(self):
        n = DarkNucleo.__new__(DarkNucleo)
        n.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))
        return n

    def test_el_crudo_del_dueno_llega_intacto(self):
        e, _hablado = _ejecutor()
        crudo = e._ya_hablado(FALLO)
        self.assertFalse(crudo.ok, "el contrato del ejecutor ya no marca fallo")

        normalizado = self.nucleo()._normalizar_resultado(crudo)

        self.assertIs(normalizado, crudo,
                      "el núcleo no reconoció el ToolResult del dueño")
        self.assertFalse(normalizado.ok)

    def test_el_fallo_del_dueno_no_se_lee_como_exito(self):
        """Sin identidad de clase el repr del fallo se normaliza como texto nuevo
        y sale `ok=True`: el paso imposible pasa por bueno."""
        e, _hablado = _ejecutor()
        normalizado = self.nucleo()._normalizar_resultado(
            e._ya_hablado(FALLO))
        self.assertNotIn("ToolResult", normalizado.mensaje or "")

    def test_el_exito_ya_hablado_conserva_el_mensaje_vacio(self):
        """El caso hablado: la frase ya salió por `speak()`, así que el mensaje
        del paso es `""`. Un repr en ese campo es lo que el orquestador narraría.
        """
        e, _hablado = _ejecutor()
        crudo = e._ya_hablado("lista")
        self.assertTrue(crudo.ok)
        self.assertEqual("", crudo.mensaje)

        normalizado = self.nucleo()._normalizar_resultado(crudo)

        self.assertEqual("", normalizado.mensaje)


class PruebaRutaViva(unittest.TestCase):
    """Banco real → `_ejecutar_herramienta`: lo que ve el usuario en el turno."""

    def setUp(self):
        self.capacidades, self.hablado = _ejecutor()
        self.banco = crear_banco(
            especialistas={},
            núcleo=SimpleNamespace(),
            capacidades=self.capacidades,
        )
        for nombre in HERRAMIENTAS_DE_CAPACIDADES:
            self.assertTrue(callable(getattr(self.capacidades, nombre, None)),
                            f"el ejecutor no tiene {nombre}")
        n = DarkNucleo.__new__(DarkNucleo)
        n.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))
        n._tracer = NullTracer()
        n._banco_herramientas = lambda: self.banco
        n._puede_usar = Mock(return_value=None)
        n._herramienta_requiere_confirmacion = Mock(return_value=False)
        self.nucleo = n

    def paso(self):
        return self.nucleo._ejecutar_herramienta(
            "buscar_imagenes", {"query": "perros", "count": 3},
            contexto={"desde_modulo": False, "ya_confirmado": False})

    def test_el_fallo_del_buscador_sale_como_fallo(self):
        with patch.object(ejecutor_mod, "DDGS", None):
            paso = self.paso()

        self.assertFalse(paso.ok,
                         "un fallo del dueño llegó como éxito al orquestador")
        self.assertEqual("fallo", paso.estado)
        self.assertNotIn("ToolResult", paso.mensaje)

    def test_el_exito_hablado_no_llega_como_repr(self):
        """La otra mitad: cuando el dueño tuvo éxito, `mensaje` es `""` y el
        núcleo lo reconstruye con `str(raw)`. Lo que el usuario oye es el repr.
        """
        with patch.object(ejecutor_mod, "DDGS", FakeDDGS):
            paso = self.paso()

        self.assertTrue(paso.ok)
        self.assertEqual("", paso.mensaje)
        self.assertNotIn("ToolResult(", paso.mensaje)

    def test_los_datos_estructurados_del_fallo_llegan_al_paso(self):
        datos = {"etapa": "composicion", "errores": ["falta «titulo»"],
                 "especificacion": "C:/planes/app.md"}
        with patch.object(self.banco, "ejecutar", return_value={
                "ok": False, "mensaje": "No pude componer la app.",
                "error": "falta «titulo»", "datos": datos}):
            paso = self.nucleo._ejecutar_herramienta(
                "buscar_imagenes", {"query": "perros", "count": 3})

        self.assertFalse(paso.ok)
        self.assertEqual(paso.datos, datos)


if __name__ == "__main__":
    unittest.main()
