"""Corte de conmutación: `investigar` y `buscar_imagenes` ya no se ejecutan en el núcleo.

Es el último par que quedaba en `HERRAMIENTAS_DEL_NUCLEO`, así que después de este
corte la lista está vacía: el núcleo no ejecuta ninguna herramienta, solo decide
cuándo y con qué permiso. El banco cambia de dueño sin cambiar de nombre, de
esquema ni de frase oída.

Las cuatro reglas que vigila este archivo:

  * **la lista se vacía por el lado correcto**: los dos nombres pasan a
    `HERRAMIENTAS_DE_CAPACIDADES` y el banco monta contra `dueño == "capacidades"`;
    si el nombre se hubiera duplicado en las dos tuplas, el orden de registro
    ganaría y el corte sería invisible en producción pero roto en el inventario.
  * **el cuerpo del núcleo desaparece**: no basta con desreclamar la herramienta.
    Mientras `dark_nucleo.py` defina `investigar`, quedan dos implementaciones y
    la que se ejecuta depende de quién llegue antes.
  * **cero cambio de voz**: la ruta vieja hablaba dentro del dispatcher y
    devolvía `""` para que la narración no repitiera. La nueva devolución es el
    contrato `_ya_hablado`, así que la frase sigue sonando VERBATIM y el mensaje
    del paso queda vacío. `buscar_imagenes_texto` es la entrada que NO habla: la
    usan los llamadores internos que ya hablan por su cuenta.
  * **la política de intención se queda donde se decide**: el forzado a
    `"wallpaper"` cuando la frase original decía «fondo de pantalla» mira
    `intencion.texto_origen`, y `texto_origen` es del orquestador. Vive en el
    núcleo como una línea de política, no como ejecución.

Ref: contratos/herramienta.py, herramientas/fabrica.py,
herramientas/internas/ejecutor.py, nucleo/dark_nucleo.py.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import herramientas.internas.manifest_tools as tm  # noqa: E402
from contratos.herramienta import (  # noqa: E402
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
)
from herramientas.fabrica import crear_banco  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas,
    Servicios,
    ToolResult,
)
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.identidades.frases import FRASES  # noqa: E402

RUTA_NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
CONMUTADAS = ("investigar", "buscar_imagenes")
MARCA = "la frase de prueba del catalogo de imagenes"


class FakeDDGS:
    """Cuatro imágenes deterministas; el ejecutor llama a `DDGS()`, así que se
    pasa la clase y no una instancia."""

    def __init__(self, *a, **k):
        pass

    def images(self, query, max_results=15):
        return [
            {"title": f"paisaje {i}", "image": f"https://x.test/{i}.jpg",
             "thumbnail": f"https://x.test/{i}_t.jpg", "url": "https://origen"}
            for i in range(4)
        ]


def _ejecutor(estado="showing_results"):
    hablado = []
    servicios = Servicios(
        hablar=lambda texto: hablado.append(texto),
        estado_overlay=lambda: estado,
    )
    return EjecutorHerramientas(servicios=servicios), hablado


def _catalogo_de_imagenes(valores):
    anterior = FRASES.get("imagenes_opciones")
    FRASES["imagenes_opciones"] = valores

    def recuperar():
        if anterior is None:
            FRASES.pop("imagenes_opciones", None)
        else:
            FRASES["imagenes_opciones"] = anterior
    return recuperar


def _funciones_de(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(arbol)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _comparados_con_accion(funcion):
    """Los literales con los que el despachador compara `action`."""
    salida = set()
    for nodo in ast.walk(funcion):
        if isinstance(nodo, ast.Compare) and isinstance(nodo.left, ast.Name) \
                and nodo.left.id == "action":
            for comparador in nodo.comparators:
                if isinstance(comparador, ast.Constant) \
                        and isinstance(comparador.value, str):
                    salida.add(comparador.value)
    return salida


class _Dueno:
    """Doble con los métodos exactos que su lista reclama."""

    def __init__(self, nombres):
        for nombre in nombres:
            # `nombre` se congela como default: si no, los seis métodos devuelven
            # el último de la tupla.
            setattr(self, nombre, (lambda *a, _n=nombre: _n))


class PruebaListaVacia(unittest.TestCase):
    def test_el_nucleo_no_reclama_ninguna_herramienta(self):
        self.assertEqual((), tuple(HERRAMIENTAS_DEL_NUCLEO),
                         "el núcleo sigue ejecutando algo por su cuenta")

    def test_los_dos_nombres_son_del_dueno_de_capacidades(self):
        for nombre in CONMUTADAS:
            self.assertIn(nombre, HERRAMIENTAS_DE_CAPACIDADES, nombre)

    def test_ningun_nombre_viaja_en_las_dos_listas(self):
        self.assertEqual(set(), set(HERRAMIENTAS_DEL_NUCLEO)
                         & set(HERRAMIENTAS_DE_CAPACIDADES))

    def test_las_seis_siguen_siendo_seis(self):
        """El corte mueve dueños, no añade herramientas al modelo."""
        self.assertEqual(6, len(HERRAMIENTAS_DE_CAPACIDADES))


class PruebaBanco(unittest.TestCase):
    def setUp(self):
        self.banco = crear_banco(
            especialistas={},
            núcleo=_Dueno([]),
            capacidades=_Dueno(HERRAMIENTAS_DE_CAPACIDADES),
        )

    def test_el_banco_monta_los_dos_nombres_contra_capacidades(self):
        for nombre in CONMUTADAS:
            montada = self.banco.montada(nombre)
            self.assertIsNotNone(montada, f"{nombre} quedó sin ejecutable")
            self.assertEqual("capacidades", montada.dueño,
                             f"{nombre} la sigue ejecutando {montada.dueño}")

    def test_los_dos_nombres_siguen_publicados_al_modelo(self):
        for nombre in CONMUTADAS:
            self.assertIn(nombre, self.banco.nombres_del_router())

    def test_el_despachador_puede_seguir_preguntando_por_el_nombre(self):
        """`tm.tool_names_set()` es lo que mira `_despachar_intencion` para entrar
        por la puerta genérica: si los dos nombres cayeran de ahí, la intención
        contestaría «no tengo handler»."""
        for nombre in CONMUTADAS:
            self.assertIn(nombre, tm.tool_names_set())


class PruebaNucleoSinCuerpos(unittest.TestCase):
    def test_el_nucleo_no_define_los_dos_cuerpos(self):
        vistas = set(_funciones_de(RUTA_NUCLEO))
        for nombre in CONMUTADAS:
            self.assertNotIn(nombre, vistas,
                             f"dark_nucleo.py sigue definiendo {nombre}")

    def test_el_nucleo_no_llama_a_los_dos_metodos(self):
        fuente = RUTA_NUCLEO.read_text(encoding="utf-8")
        for nombre in CONMUTADAS:
            self.assertNotIn("self.%s(" % nombre, fuente,
                             f"queda un llamador de {nombre} en el núcleo")

    def test_la_rama_temprana_de_investigar_desaparecio(self):
        despachador = _funciones_de(RUTA_NUCLEO)["_despachar_intencion"]
        comparados = _comparados_con_accion(despachador)
        self.assertNotIn("investigar", comparados,
                         "`investigar` sigue teniendo una rama propia en el despacho")

    def test_la_rama_de_imagenes_solo_aplica_la_politica(self):
        """La rama que queda no ejecuta: fuerza la intención y deja pasar el turno
        por la puerta genérica. Si volviera a llamar a un cuerpo propio, el corte
        se deshace sin que falle nada más."""
        despachador = _funciones_de(RUTA_NUCLEO)["_despachar_intencion"]
        self.assertIn("buscar_imagenes", _comparados_con_accion(despachador))
        llamadas = [n.func.attr for n in ast.walk(despachador)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and isinstance(n.func.value, ast.Name)
                    and n.func.value.id == "self"]
        self.assertIn("_forzar_intencion_wallpaper", llamadas)
        for nombre in CONMUTADAS:
            self.assertNotIn(nombre, llamadas,
                             f"el despacho volvió a ejecutar {nombre} en el núcleo")


class PruebaEntradaDeBanco(unittest.TestCase):
    """El contrato de mensajes de la herramienta montada: habla y marca «ya habló»."""

    def test_buscar_imagenes_habla_la_frase_verbatim_y_deja_el_mensaje_vacio(self):
        self.addCleanup(_catalogo_de_imagenes([MARCA]))
        e, hablado = _ejecutor()
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            resultado = e.buscar_imagenes("perros", count=3)

        self.assertIsInstance(resultado, ToolResult)
        self.assertTrue(resultado.ok)
        self.assertEqual("", resultado.mensaje)
        self.assertEqual([MARCA], hablado)
        self.assertEqual(3, len(e.resultados_visuales))

    def test_la_entrada_de_texto_devuelve_la_frase_sin_hablar(self):
        self.addCleanup(_catalogo_de_imagenes([MARCA]))
        e, hablado = _ejecutor()
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            msg = e.buscar_imagenes_texto("perros", count=3)

        self.assertEqual(MARCA, msg)
        self.assertEqual([], hablado)

    def test_el_fallo_del_buscador_sigue_siendo_fallo_en_la_entrada_de_banco(self):
        """La ruta vieja hablaba también el fallo, así que la nueva lo habla igual.

        Sin el prefijo de fallo, la cadena vacía del «ya habló» se leería como
        éxito: un paso imposible pasaría por bueno.
        """
        e, hablado = _ejecutor()
        with patch("herramientas.internas.ejecutor.DDGS", None):
            resultado = e.buscar_imagenes("perros", count=3)

        self.assertIsInstance(resultado, ToolResult)
        self.assertFalse(resultado.ok)
        self.assertEqual("", resultado.mensaje)
        self.assertEqual(1, len(hablado))
        self.assertIn("No pude buscar imágenes", hablado[0])
        self.assertIn("No pude buscar imágenes", resultado.detalle_error or "")

    def test_carrusel_habla_su_frase_y_tambien_marca_ya_hablo(self):
        self.addCleanup(_catalogo_de_imagenes([MARCA]))
        e, hablado = _ejecutor()
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            resultado = e.buscar_imagenes("perros", count=4)

        self.assertIsInstance(resultado, ToolResult)
        self.assertEqual("", resultado.mensaje)
        self.assertIn("carrusel", hablado[0])
        self.assertNotIn(MARCA, hablado)

    def test_poner_wallpaper_por_tematica_solo_dice_la_frase_una_vez(self):
        """El llamador interno habla y luego marca: si usara la entrada del banco
        la frase sonaría dos veces."""
        self.addCleanup(_catalogo_de_imagenes([MARCA]))
        e, hablado = _ejecutor()
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            resultado = e._poner_wallpaper_intencion(tema="flores")

        self.assertEqual([MARCA], hablado)
        self.assertIsInstance(resultado, ToolResult)
        self.assertEqual("", resultado.mensaje)

    def test_buscar_similares_devuelve_texto_para_quien_lo_habla(self):
        """`_buscar_similares_a_indice` devuelve el texto: lo habla quien lo pidió.

        Con count 6 sobre cuatro tarjetas el carrusel es la frase esperada; lo que
        se mide aquí es la forma (texto, y silencio), no el catálogo.
        """
        self.addCleanup(_catalogo_de_imagenes([MARCA]))
        e, hablado = _ejecutor()
        e._resultados_visuales = [
            {"title": f"t{i}", "url": f"https://x.test/{i}.jpg",
             "thumbnail": f"https://x.test/{i}_t.jpg", "source": "https://origen"}
            for i in range(3)
        ]
        e._ultima_query_imagenes = "perros"
        with patch("herramientas.internas.ejecutor.DDGS", FakeDDGS):
            msg = e._buscar_similares_a_indice(0)

        self.assertIsInstance(msg, str)
        self.assertIn("carrusel", msg)
        self.assertEqual([], hablado)


class PruebaPoliticaDeIntencion(unittest.TestCase):
    """El forzado a wallpaper mira `texto_origen`, que es dato del orquestador."""

    def nucleo(self):
        from nucleo import sesion_resultados
        n = DarkNucleo.__new__(DarkNucleo)
        n._sesion_cache = sesion_resultados.crear_sesion_resultados()
        return n

    def forzar(self, texto_origen, intencion_inicial=None):
        n = self.nucleo()
        n._intencion_imagenes = intencion_inicial
        intencion = DarkNucleo.__new__(DarkNucleo)
        intencion.texto_origen = texto_origen
        DarkNucleo._forzar_intencion_wallpaper(n, intencion)
        return n._intencion_imagenes

    def test_las_dos_formas_que_el_pattern_acepta(self):
        for texto in ("ponme wallpapers de autos", "cambia el fondo de pantalla",
                      "quiero fondos de pantalla de gatos"):
            self.assertEqual("wallpaper", self.forzar(texto, "descargar"), texto)

    def test_de_fondo_suelto_no_es_una_de_las_dos_formas(self):
        """El patrón exige «fondo de pantalla»; «de fondo» suelto nunca lo forzó.

        No es un cambio de este corte: es la regex tal como estaba en la rama que
        se borra. Queda escrito para no descubrirlo dentro de tres cortes.
        """
        self.assertEqual("descargar",
                         self.forzar("ponme de fondo un gato", "descargar"))

    def test_sin_la_palabra_la_intencion_del_buscardor_manda(self):
        self.assertEqual("descargar", self.forzar("busca gatos", "descargar"))

    def test_una_frase_vacia_no_borra_la_intencion(self):
        self.assertEqual("descargar", self.forzar("", "descargar"))


if __name__ == "__main__":
    unittest.main()
