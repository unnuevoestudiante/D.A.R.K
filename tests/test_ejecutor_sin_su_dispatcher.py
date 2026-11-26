"""El dueño de capacidades ya no despacha: el banco es la única puerta.

Guarda del corte que borra el dispatcher propio de
`herramientas/internas/ejecutor.py`: `ejecutar`/`_ejecutar`/`_resolver_handler`,
su catálogo (`MANIFEST_LOCAL`, `MANIFEST_COMPLETO`), su tabla de reflejos
(`_propias`, `TOOL_A_ESPECIALISTA`), sus registros (`registrar`,
`registrar_especialista`, `tools_disponibles`), sus traductores de paso
(`_paso_error`, `_tool_result_a_paso`) y los cuatro envoltorios
`herramienta_tv_*`.

Se mide por AST y no por texto por la misma razón que las guardas de los
escalones anteriores: `handle_command` es `try:` … `finally:` sin `except`, así
que un resto de despacho mal conmutado mata el turno de voz en silencio. La
primera clase está en rojo mientras el dispatcher exista; la segunda y la
tercera pasan antes y después, y son las que impiden que el corte se firme
borrando también las capacidades.

Medido, no intuido: el dispatcher del dueño no tenía ningún llamador de
producción. El núcleo entra a las herramientas por
`dark_nucleo.py:6178` (`banco.ejecutar`) y a las hojas de intención por
`_capacidades_herramientas()` con el método llamado a mano; el censo por AST de
los trece nombres muertos sobre `dark_python/` solo devuelve `montada.ejecutar`,
`pendiente.ejecutar`, `banco.ejecutar`, `cache.registrar`, `self._acceso.registrar`,
`self.entidades.registrar`, `ctx_entidades.registrar` y los usos internos del
propio dispatcher.

Las pruebas levantan el dueño SIN `DarkNucleo`.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.herramienta import (  # noqa: E402
    HERRAMIENTAS_DE_CAPACIDADES, INVISIBLES_AL_MODELO,
)
from herramientas import fabrica  # noqa: E402
from herramientas.internas import manifest_tools as tm  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas, Servicios,
)

RUTA_DUEÑO = "herramientas/internas/ejecutor.py"

#: Los trece nombres que forman el dispatcher y mueren con el corte.
METODOS_DEL_DISPATCHER = (
    "ejecutar", "_ejecutar", "_resolver_handler", "_paso_error",
    "_tool_result_a_paso", "registrar", "registrar_especialista",
    "tools_disponibles", "_herramienta_tv",
    "herramienta_tv_config", "herramienta_tv_control",
    "herramienta_tv_netflix", "herramienta_tv_destino_ui",
)

#: Datos de módulo que solo existían para que el dispatcher resolviera.
DATOS_DE_MODULO = (
    "MANIFEST_LOCAL", "MANIFEST_COMPLETO", "TOOL_A_ESPECIALISTA",
    "_TOOLS_DE_CODIGO",
)

#: Atributos de instancia que se ponían en el constructor para el despacho.
ATRIBUTOS_DE_DESPACHO = ("_propias", "_especialistas", "_handlers_externos")

#: Los dos servicios que solo consumía el guard de `terminal_desarrollo` y la
#: contabilidad de uso, ambas cosas dentro del dispatcher.
CAMPOS_MUERTOS_DE_SERVICIOS = ("plan_de_tarea", "registrar_uso")

#: Nombre pedido -> hoja del dueño a la que apuntaba `_propias`. Son las dieciséis
#: del catálogo local, de las diecinueve salidas de la tabla: las tres que faltan
#: (`descargar_archivo`, `investigar`, `buscar_imagenes`) sí están declaradas fuera
#: y las mide `test_los_seis_nombres_del_contrato_sigue_sirviendolos_el_banco`.
#: El catálogo se va; la capacidad no. Las cuatro de tele son los `_manejar_*`.
HOJAS_DEL_CATALOGO_LOCAL = (
    ("fecha_hora", "_respuesta_fecha"),
    ("abrir_archivo", "_abrir_archivo_intencion"),
    ("cambiar_nombre_archivo", "cambiar_nombre_archivo"),
    ("instalar_wallpaper", "instalar_wallpaper"),
    ("poner_wallpaper", "_poner_wallpaper_intencion"),
    ("accion_imagenes", "_despachar_accion_imagenes"),
    ("ampliar_imagenes", "_ampliar_imagenes"),
    ("buscar_similares", "_buscar_similares_a_indice"),
    ("descargar_imagen", "_descargar_imagen"),
    ("seleccionar_resultado_web", "_seleccionar_resultado"),
    ("investigar_a_fondo", "investigar_a_fondo"),
    ("ocultar_resultados", "_ocultar_resultados_visuales"),
    ("tv_config", "_manejar_config_tv"),
    ("tv_control", "_manejar_control_tv"),
    ("tv_netflix", "_manejar_netflix_tv"),
    ("tv_destino_ui", "_manejar_destino_ui"),
)

#: Lo que el dispatcher formaba antes de morir y que sigue haciendo falta: sin
#: estas tres la clasificación de errores pierde su única lectura de una hoja.
TRIO_CONSERVADO = (
    "_normalizar_resultado", "_clasificar_error", "_ya_hablado",
)

_ARBOLES: dict = {}


def _arbol(relativa: str) -> ast.Module:
    if relativa not in _ARBOLES:
        _ARBOLES[relativa] = ast.parse(
            (DARK_PYTHON / relativa).read_text(encoding="utf-8"))
    return _ARBOLES[relativa]


def _cuerpo_de_la_clase(clase: str) -> list:
    return next(n for n in ast.walk(_arbol(RUTA_DUEÑO))
                if isinstance(n, ast.ClassDef) and n.name == clase).body


def _metodos_de_la_clase(clase: str) -> set:
    return {n.name for n in _cuerpo_de_la_clase(clase)
            if isinstance(n, ast.FunctionDef)}


def _nombres_de_modulo() -> set:
    salida = set()
    for nodo in _arbol(RUTA_DUEÑO).body:
        if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
            blancos = nodo.targets if isinstance(nodo, ast.Assign) else [nodo.target]
            for b in blancos:
                if isinstance(b, ast.Name):
                    salida.add(b.id)
    return salida


def _asignaturas_en(nombre_de_funcion: str) -> set:
    """Atributos asignados a `self` dentro de un método del dueño."""
    func = next(n for n in ast.walk(_arbol(RUTA_DUEÑO))
                if isinstance(n, ast.FunctionDef) and n.name == nombre_de_funcion)
    puesta = set()
    for nodo in ast.walk(func):
        if not isinstance(nodo, ast.Assign):
            continue
        for b in nodo.targets:
            if isinstance(b, ast.Attribute) and isinstance(b.value, ast.Name) \
                    and b.value.id == "self":
                puesta.add(b.attr)
    return puesta


def _banco_sin_especialistas(capacidades):
    """El banco de producción menos los especialistas: solo el dueño de capacidades."""
    return fabrica.crear_banco(especialistas={}, capacidades=capacidades)


class PruebaElDuenoNoDespacha(unittest.TestCase):
    """El dispatcher ya no vive en el dueño. Rojo hasta el corte B."""

    def test_el_dueño_no_define_el_paso_de_diccionario(self):
        presentes = _metodos_de_la_clase("EjecutorHerramientas") & set(METODOS_DEL_DISPATCHER)
        self.assertEqual(
            presentes, set(),
            "el dueño vuelve a tener despacho propio: " + ", ".join(sorted(presentes)))

    def test_el_dueño_no_declara_su_propio_catalogo(self):
        presentes = _nombres_de_modulo() & set(DATOS_DE_MODULO)
        self.assertEqual(
            presentes, set(),
            "sin despacho estos datos son un vocabulario huérfano que nadie "
            "lee y que invita a un segundo camino: " + ", ".join(sorted(presentes)))

    def test_el_constructor_no_monta_tablas_de_reflejo(self):
        presentes = _asignaturas_en("__init__") & set(ATRIBUTOS_DE_DESPACHO)
        self.assertEqual(
            presentes, set(),
            "una tabla nombre->método es resolver por reflejo otra vez, y esa "
            "es la puerta que el banco cerró: " + ", ".join(sorted(presentes)))

    def test_el_constructor_no_pide_especialistas(self):
        parametros = inspect.signature(EjecutorHerramientas.__init__).parameters
        self.assertNotIn(
            "especialistas", parametros,
            "el dueño recibe servicios, nunca otros dueños: quien los reparte es "
            "`herramientas/fabrica.py`")

    def test_los_dos_servicios_del_dispatcher_no_viajan(self):
        presentes = {c.name for c in dataclasses.fields(Servicios)} & set(CAMPOS_MUERTOS_DE_SERVICIOS)
        self.assertEqual(
            presentes, set(),
            "son el guard de terminal_desarrollo y la contabilidad de uso del "
            "dispatcher; el orquestador ya no tiene que inyectarlos: "
            + ", ".join(sorted(presentes)))


class PruebaNadiePideEseDispatcher(unittest.TestCase):
    """El lado contrario a que vuelva: los nombres muertos no tienen llamadores.

    Pasa antes y después del corte. Sin ella, un módulo nuevo podría seguir
    escribiendo `self._capacidades_herramientas().ejecutar({...})` y el corte le
    dejaría un AttributeError en la ruta de voz sin que ninguna prueba lo avise.
    """

    def test_en_el_repo_nadie_le_pide_un_paso_al_dueño(self):
        colgados = []
        for ruta in sorted(list((DARK_PYTHON).rglob("*.py")) + list((RAIZ / "tests").glob("*.py"))):
            if ruta.name == "ejecutor.py" or "ejecutor_sin_su_dispatcher" in ruta.name:
                continue
            try:
                raiz = ast.parse(ruta.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            for nodo in ast.walk(raiz):
                if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                    continue
                if nodo.func.attr not in METODOS_DEL_DISPATCHER:
                    continue
                receptor = ast.unparse(nodo.func.value)
                if not any(p in receptor for p in
                           ("_capacidades", "capacidades_ej", "EjecutorHerramientas")):
                    continue
                colgados.append(f"{ruta.name}:{nodo.lineno} → {receptor[:40]}.{nodo.func.attr}")
        self.assertEqual(colgados, [],
                         "estos llamadores siguen pidiendo el paso de diccionario: "
                         + "; ".join(colgados))

    def test_el_dueño_sigue_sin_saber_pintar_ni_hablar_solo(self):
        """`speak` y el overlay se quedan: lo que muere es el paso, no la voz."""
        nombres = _metodos_de_la_clase("EjecutorHerramientas")
        self.assertTrue({"speak", "_set_overlay", "_estado_overlay"} <= nombres)


class PruebaLasHojasSiguenVivas(unittest.TestCase):
    """Borrar el catálogo no puede dejar una capacidad sin cuerpo.

    Es la guarda que impide firmar el corte con el `git rm` del archivo entero:
    los dieciséis nombres que el dispatcher resolvía por reflejo siguen teniendo
    su hoja en el dueño, y el banco sigue sirviendo los seis que declara.
    """

    def test_las_dieciseis_hojas_del_catalogo_local_siguen_existiendo(self):
        nombres = _metodos_de_la_clase("EjecutorHerramientas")
        faltan = [f"{pedida}->{hoja}" for pedida, hoja in HOJAS_DEL_CATALOGO_LOCAL
                  if hoja not in nombres]
        self.assertEqual(faltan, [], "el corte se llevó la hoja: " + ", ".join(faltan))

    def test_el_trio_de_clasificacion_se_conserva(self):
        nombres = _metodos_de_la_clase("EjecutorHerramientas")
        faltan = sorted(set(TRIO_CONSERVADO) - nombres)
        self.assertEqual(
            faltan, [],
            "sin estas tres la forma de un fallo de una hoja queda sin leer: "
            + ", ".join(faltan))

    def test_los_seis_nombres_del_contrato_sigue_sirviendolos_el_banco(self):
        banco = _banco_sin_especialistas(EjecutorHerramientas())
        sueltos = [n for n in HERRAMIENTAS_DE_CAPACIDADES if banco.montada(n) is None]
        self.assertEqual(
            sueltos, [],
            "el banco perdió la única puerta de estas capacidades: " + ", ".join(sueltos))
        for nombre in HERRAMIENTAS_DE_CAPACIDADES:
            with self.subTest(nombre=nombre):
                self.assertEqual(banco.montada(nombre).dueño, "capacidades")

    def test_doce_nombres_locales_nunca_fueron_pedibles(self):
        """El catálogo local era vocabulario del dispatcher, no capacidad nueva.

        De los dieciséis, cuatro existían también fuera: `cambiar_nombre_archivo`
        se declara al modelo en `tm.MANIFEST` y `ampliar_imagenes`,
        `descargar_imagen` e `instalar_wallpaper` están en `INVISIBLES_AL_MODELO`,
        donde el banco los monta contra el especialista de comunicación. Los doce
        restantes no están en ninguna de las tres listas: ni el modelo ni el router
        local podían pedirlos, así que borrar el catálogo no cierra ninguna salida.
        """
        locales = {pedida for pedida, _ in HOJAS_DEL_CATALOGO_LOCAL}
        self.assertEqual(16, len(locales))
        askables = ({e["name"] for e in tm.MANIFEST} | set(INVISIBLES_AL_MODELO)
                    | set(HERRAMIENTAS_DE_CAPACIDADES))
        compartidos = locales & askables
        self.assertEqual(
            {"cambiar_nombre_archivo", "ampliar_imagenes", "descargar_imagen",
             "instalar_wallpaper"}, compartidos,
            "la lista de locales dejó de ser catálogo puro del dispatcher: "
            + ", ".join(sorted(compartidos)))
        # De los cuatro, `cambiar_nombre_archivo` es el único cuyo ejecutable es
        # del dueño; los otros tres los monta el banco contra comunicación, y ese
        # dueño no se levanta aquí (lo mide `tests/test_especialista_contrato.py`).
        banco = _banco_sin_especialistas(EjecutorHerramientas())
        self.assertIsNotNone(banco.montada("cambiar_nombre_archivo"),
                             "el dueño perdió el único nombre local visible")

    def test_la_hoja_de_llegada_responde_sin_dispatcher(self):
        """El efecto, no el cable: una negativa real sale por el banco."""
        banco = _banco_sin_especialistas(EjecutorHerramientas())
        mensaje = banco.ejecutar("descargar_archivo", {"url": "file:///C:/x.txt"})
        self.assertIn("Solo puedo descargar desde", mensaje)


if __name__ == "__main__":
    unittest.main()
