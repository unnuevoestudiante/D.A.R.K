"""El dueño de capacidades no duplica lo que el núcleo ya hace mejor.

Guarda del escalón 4. `detectar_accion_imagenes` y `ejecutar_accion_imagenes`
vivían en `ejecutor.py` como copia del par `_detectar_accion_imagenes` /
`_ejecutar_accion_imagenes` del núcleo, y la copia estaba muerta: el manifiesto
declaraba `accion_imagenes` y esa ruta iba a `_despachar_accion_imagenes`, mientras
el turno de voz llamaba al par del núcleo. Nadie las invocaba salvo
`tests/test_ejecutor.py`. (El manifiesto y la tabla de despachos se fueron después,
en el escalón que borró el dispatcher del dueño; la ruta viva es la del núcleo).

Se borran las copias en vez de migrar la capacidad porque el original es el que
tiene lo que la copia no:
- el detector pregunta `_hay_imagenes_visibles()` al overlay del núcleo, y la copia
  miraba su propia lista (viva después de un `esconder`);
- el ejecutor baja y pone fondo a través de `_ejecutar_herramienta_visual_ui`, que
  es la puerta con candado; la copia llamaba a las hojas directamente;
- el detector usa `es_limpieza_imagenes`, el predicado compartido del router, en
  lugar de una lista propia de frases negativas que ya se había separado del resto.

Por qué esto es una guarda y no una limpieza: `handle_command` es `try:` …
`finally:` sin `except`, así que un llamador que quede apuntando a un cuerpo
borrado no lanza un error visible — mata el turno de voz en silencio. El censo de
atributos sobre todo el proyecto es lo que cierra esa puerta.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.ejecutor import EjecutorHerramientas  # noqa: E402

RUTA_NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
RUTA_DUEÑO = DARK_PYTHON / "herramientas" / "internas" / "ejecutor.py"

#: Las dos copias que se van del dueño.
COPIAS_MUERTAS = ("detectar_accion_imagenes", "ejecutar_accion_imagenes")

#: La pareja viva: se queda en el núcleo por las tres razones del docstring.
PAREJA_VIVA = ("_detectar_accion_imagenes", "_ejecutar_accion_imagenes")

#: El turno de texto plano es el único consumidor de la pareja.
RUTA_DEL_TURNO = "_encolar_texto_manual"

#: Hojas del dueño que en el núcleo solo se rozan por la puerta de la UI.
HOJAS_BAJO_CANDADO = ("_descargar_imagen", "_descargar_todas_las_imagenes",
                      "_instalar_wallpaper_indice")

#: La hoja del dueño a la que apunta la ruta viva del núcleo.
DUEÑO_DE_ACCION_IMAGENES = "_despachar_accion_imagenes"


def _arbol(ruta):
    return ast.parse(ruta.read_text(encoding="utf-8"))


NUCLEO_AST = _arbol(RUTA_NUCLEO)
DUEÑO_AST = _arbol(RUTA_DUEÑO)


def _metodos_de_la_clase(raiz, clase):
    cuerpo = next(n for n in ast.walk(raiz)
                  if isinstance(n, ast.ClassDef) and n.name == clase).body
    return [nodo.name for nodo in cuerpo if isinstance(nodo, ast.FunctionDef)]


def _funcion(raiz, nombre):
    return next(n for n in ast.walk(raiz)
                if isinstance(n, ast.FunctionDef) and n.name == nombre)


def _accesos(nombre, raiz):
    return sorted(n.lineno for n in ast.walk(raiz)
                  if isinstance(n, ast.Attribute) and n.attr == nombre)


def _llamadas_a(nombre, raiz):
    return [n for n in ast.walk(raiz)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == nombre]


def _llamadas_a_funcion_libre(nombre, raiz):
    """Llamadas a un nombre suelto: `es_limpieza_imagenes` entra por `import`.

    Un censo de `Attribute` lo pasaría por alto y afirmaría «no se usa» sobre un
    sitio que sí lo usa.
    """
    return [n for n in ast.walk(raiz)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == nombre]


def _rutinas_del_proyecto():
    """Todo `.py` de `dark_python` y `tests`, parseado de verdad.

        Un fichero que no parsea se apunta como fallo en lugar de colarse como
    «sin referencias»: si no lo podemos leer, no podemos afirmar que no llama.
    """
    rutas = sorted(list((DARK_PYTHON).rglob("*.py"))
                   + list((ROOT / "tests").rglob("*.py")))
    arboles, rotos = [], []
    for ruta in rutas:
        try:
            arboles.append((ruta.relative_to(ROOT), _arbol(ruta)))
        except SyntaxError:
            rotos.append(str(ruta.relative_to(ROOT)))
    return arboles, rotos


# --------------------------------------------------------------------------------
# 1. El dueño queda sin las copias y sin nadie que las eche de menos
# --------------------------------------------------------------------------------

class PruebaElDueñoSinLasCopias(unittest.TestCase):
    def test_el_dueño_no_define_las_dos_copias(self):
        definidas = [n for n in COPIAS_MUERTAS
                     if n in _metodos_de_la_clase(DUEÑO_AST,
                                                   "EjecutorHerramientas")]
        self.assertEqual([], definidas,
                         "escalón 4: la pareja del núcleo es la viva")

    def test_la_interfaz_del_dueño_no_expresa_esas_dos_utilidades(self):
        """Lo que comprobaría producción con un `getattr` antes de lanzar."""
        asomadas = [n for n in COPIAS_MUERTAS if hasattr(EjecutorHerramientas, n)]
        self.assertEqual([], asomadas)

    def test_el_manifiesto_no_declara_las_copias(self):
        """Ni por tabla de despachos ni por constante de texto del fichero."""
        constantes = {n.value for n in ast.walk(DUEÑO_AST)
                      if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertEqual(set(), constantes & set(COPIAS_MUERTAS))

    def test_la_ruta_de_accion_imagenes_sigue_viva_en_el_nucleo(self):
        """Sin la tabla del dueño, la ruta que queda es la del núcleo: su método
        `_despachar_accion_imagenes` llama a la hoja del dueño por la puerta
        `_capacidades_herramientas()`, y es la única llamada que hay dentro.
        """
        cuerpo = _funcion(NUCLEO_AST, DUEÑO_DE_ACCION_IMAGENES)
        hojas = [n.func.attr for n in _llamadas_a(DUEÑO_DE_ACCION_IMAGENES, cuerpo)
                 if isinstance(n.func.value, ast.Call)
                 and isinstance(n.func.value.func, ast.Attribute)
                 and n.func.value.func.attr == "_capacidades_herramientas"]
        self.assertEqual([DUEÑO_DE_ACCION_IMAGENES], hojas)
        self.assertTrue(callable(getattr(EjecutorHerramientas,
                                         DUEÑO_DE_ACCION_IMAGENES, None)),
                        "el núcleo llama a una hoja que el dueño ya no tiene")

    def test_ningun_fichero_del_proyecto_invoca_a_las_copias(self):
        arboles, rotos = _rutinas_del_proyecto()
        self.assertEqual([], rotos)
        usos = [(str(ruta), linea, nombre)
                for ruta, arbol in arboles
                for nombre in COPIAS_MUERTAS
                for linea in _accesos(nombre, arbol)]
        self.assertEqual([], usos)


# --------------------------------------------------------------------------------
# 2. La pareja viva: el turno de texto la sigue usando una vez cada una
# --------------------------------------------------------------------------------

class PruebaLaParejaVivaDelNúcleo(unittest.TestCase):
    def setUp(self):
        self.metodos_nucleo = _metodos_de_la_clase(NUCLEO_AST, "DarkNucleo")

    def test_el_núcleo_sigue_definiendo_las_dos(self):
        faltan = [n for n in PAREJA_VIVA if n not in self.metodos_nucleo]
        self.assertEqual([], faltan)

    def test_el_turno_de_texto_usa_cada_una_una_sola_vez(self):
        turno = _funcion(NUCLEO_AST, RUTA_DEL_TURNO)
        self.assertEqual(1, len(_llamadas_a(PAREJA_VIVA[0], turno)),
                         "el detector se llama una vez por turno")
        ejecutor = [llamada for llamada in _llamadas_a("_accion_ui", turno)
                    if any(isinstance(arg, ast.Attribute)
                           and arg.attr == PAREJA_VIVA[1]
                           for arg in llamada.args)]
        self.assertEqual(1, len(ejecutor),
                         "la ejecución sigue pasando por `_accion_ui`")


# --------------------------------------------------------------------------------
# 3. Las tres razones por las que el original es el que se queda
# --------------------------------------------------------------------------------

class PruebaElCandadoQueMotivaLaDecisión(unittest.TestCase):
    def test_el_detector_pregunta_a_su_overlay(self):
        detector = _funcion(NUCLEO_AST, PAREJA_VIVA[0])
        self.assertEqual(1, len(_llamadas_a("_hay_imagenes_visibles", detector)))

    def test_el_detector_comparte_el_predicado_de_limpieza(self):
        """La copia traía su propia lista de frases negativas, ya separada."""
        detector = _funcion(NUCLEO_AST, PAREJA_VIVA[0])
        self.assertEqual(1, len(_llamadas_a_funcion_libre(
            "es_limpieza_imagenes", detector)))

    def test_el_ejecutor_baja_y_pone_fondo_solo_por_la_puerta_ui(self):
        ejecutor = _funcion(NUCLEO_AST, PAREJA_VIVA[1])
        sueltas = [(nombre, linea) for nombre in HOJAS_BAJO_CANDADO
                   for linea in _accesos(nombre, ejecutor)]
        self.assertEqual([], sorted(sueltas))
        self.assertGreaterEqual(
            len(_llamadas_a("_ejecutar_herramienta_visual_ui", ejecutor)), 2)


if __name__ == "__main__":
    unittest.main()
