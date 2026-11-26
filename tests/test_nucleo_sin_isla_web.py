"""La isla web del núcleo ya no existe: el único dueño es el ejecutor.

Siete cuerpos de `dark_nucleo.py` eran copia casi literal de siete del
ejecutor (136 líneas medidas sobre los rangos de definición). No los llamaba
nadie vivo: sus únicas referencias dentro del núcleo eran entre ellos mismos —
isla cerrada— y dos entradas del dict `helpers` que inyectaba en el
especialista de tareas.

Esa inyección era el peligro real del corte. `handle_command` nunca llegó a
estas funciones, pero el dict se construye en `_registro_especialistas`, que sí
corre al montar el núcleo: borrar los cuerpos y dejar la clave
`"buscar_resultados_web": self._buscar_resultados_web` habría lanzado
`AttributeError` en la construcción, antes de cualquier turno.

La secuencia, en la ruta viva de «investiga X»:

  1. La intención llega al banco de herramientas.
  2. El banco resuelve `investigar_a_fondo` contra el **ejecutor**
      (`HERRAMIENTAS_DEL_NUCLEO == ()`, así que el núcleo ya no registra la
      suya).
  3. La copia del núcleo solo la alcanzaban los tests.

Dónde está mejor la del ejecutor, medido cuerpo contra cuerpo:
`_resultados_ddg_html`, `_resultados_bing`, `_bloque_fuentes` y
`_resumen_titulos_web` son idénticos; `_buscar_resultados_web` y
`_obtener_texto_pagina` además comprueban `DDGS is not None` y
`BeautifulSoup is None` y devuelven el fallo vacío en vez de reventar;
`investigar_a_fondo` es la envoltura de ocho líneas sobre
`_investigar_interno`, que trae la convención del `None` (el arreglo de la
revisión: sin fuentes no puede devolver `""`, que el normalizador lee como
éxito).

Las cuatro reglas que vigila este archivo:

  * los siete nombres no vuelven a definirse en el núcleo;
  * siguen definidos en el ejecutor, para que borrar no se convierta en perder
    capacidad;
  * ninguna clave inyectada en `helpers` cuelga de un atributo que ya no está;
  * los cinco imports que solo usaba la isla no se quedan huérfanos.

Ref: nucleo/dark_nucleo.py, herramientas/internas/ejecutor.py.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
EJECUTOR = DARK_PYTHON / "herramientas" / "internas" / "ejecutor.py"

ISLA = ["_resultados_ddg_html", "_resultados_bing", "_buscar_resultados_web",
        "_bloque_fuentes", "_resumen_titulos_web", "_obtener_texto_pagina",
        "investigar_a_fondo"]

# Los nombres que la isla era la única forma de alcanzar desde este archivo.
IMPORTS_HUERFANOS = ["base64", "parse_qs", "BeautifulSoup", "ThreadPoolExecutor",
                     "as_completed"]


def _metodos(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    return {n.name for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)}


def _atributos_de_instancia(ruta):
    """Lo que `self.X = ...` deja atado al núcleo, junto a sus métodos.

    `llm_pedido_chat` y `tarea_bg_cancel` no son métodos: son dos
    `threading.Event()` de `__init__` que viajan por el mismo dict.
    """
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    atributos = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Attribute) and isinstance(nodo.ctx, ast.Store)\
                and isinstance(nodo.value, ast.Name) and nodo.value.id == "self":
            atributos.add(nodo.attr)
    return _metodos(ruta) | atributos


def _nombres_importados(ruta):
    """Lo que un `import` deja atado en el namespace del módulo."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                nombres.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            for alias in nodo.names:
                nombres.add(alias.asname or alias.name)
    return nombres


def _claves_helpers_inyectadas():
    """El dict `helpers` que el núcleo le pasa a la fábrica de tareas."""
    arbol = ast.parse(NUCLEO.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.keyword) or nodo.arg != "helpers":
            continue
        if not isinstance(nodo.value, ast.Dict):
            continue
        claves = {}
        for clave, valor in zip(nodo.value.keys, nodo.value.values):
            if isinstance(valor, ast.Attribute) and isinstance(valor.value, ast.Name):
                claves[ast.literal_eval(clave)] = valor.attr
        return claves
    raise AssertionError("el núcleo ya no inyecta un dict `helpers` literal")


class PruebaIslaFueraDelNucleo(unittest.TestCase):
    def setUp(self):
        self.metodos_nucleo = _metodos(NUCLEO)
        self.metodos_ejecutor = _metodos(EJECUTOR)

    def test_los_siete_cuerpos_no_estan_en_el_nucleo(self):
        presentes = [n for n in ISLA if n in self.metodos_nucleo]
        self.assertEqual([], presentes,
                         "la isla web sigue duplicada en el núcleo")

    def test_el_ejecutor_sigue_dando_las_siete(self):
        """El corte no puede convertirse en perder capacidad."""
        faltan = [n for n in ISLA if n not in self.metodos_ejecutor]
        self.assertEqual([], faltan,
                         "el dueño de las capacidades ya no tiene la isla")

    def test_la_envoltura_delegra_en_el_interno(self):
        self.assertIn("_investigar_interno", self.metodos_ejecutor)


class PruebaInyeccionSinColgados(unittest.TestCase):
    """Una clave de `helpers` es una promesa: el atributo tiene que existir."""

    def test_cada_clave_apunta_a_un_atributo_vivo_del_nucleo(self):
        vivos = _atributos_de_instancia(NUCLEO)
        cuelgan = {clave: attr for clave, attr in _claves_helpers_inyectadas().items()
                   if attr not in vivos}
        self.assertEqual({}, cuelgan,
                         "el núcleo inyecta capacidades que ya no define")

    def test_la_isla_ya_no_se_inyecta(self):
        for nombre in ("buscar_resultados_web", "obtener_texto_pagina"):
            self.assertNotIn(nombre, _claves_helpers_inyectadas())


class PruebaImportsSinHuerfanos(unittest.TestCase):
    def test_la_isla_no_deja_imports_colgados(self):
        importados = _nombres_importados(NUCLEO)
        huérfanos = [n for n in IMPORTS_HUERFANOS if n in importados]
        self.assertEqual([], huérfanos,
                         "estos nombres los usaba solo la isla borrada")

    def test_lo_que_comparte_con_el_resto_se_queda(self):
        importados = _nombres_importados(NUCLEO)
        for nombre in ("requests", "urlparse", "DDGS"):
            self.assertIn(nombre, importados,
                          f"{nombre} se usa fuera de la isla y no debió irse")


if __name__ == "__main__":
    unittest.main()
