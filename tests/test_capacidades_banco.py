"""Fase D, corte 1: las capacidades ejecutan desde un dueño, no desde el núcleo.

El banco ya admite un dueño por especialista y uno que es el propio núcleo. Lo
que falta en el corte es que **las implementaciones dejen de vivir en
`dark_nucleo.py`**: el módulo de capacidades pasa a ser un segundo dueño sin
prefijo, y el núcleo solo conserva la puerta (`_ejecutar_herramienta`), los
permisos y los contadores.

Ref: herramientas/fabrica.py, herramientas/banco.py, contratos/herramienta.py,
herramientas/internas/ejecutor.py, nucleo/dark_nucleo.py.
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import herramientas.internas.manifest_tools as tm  # noqa: E402
from contratos.herramienta import HERRAMIENTAS_DEL_NUCLEO  # noqa: E402
from herramientas.banco import BancoHerramientas, Dueño  # noqa: E402
from herramientas.fabrica import crear_banco, dueños_de_registro  # noqa: E402

# Las herramientas que ya cambiaron de dueño. Con `investigar` y
# `buscar_imagenes` la lista está completa: no queda ninguna herramienta en el
# núcleo, que es justo lo que se propuso el corte de capacidades.
EXTRAIDAS = ("descargar_archivo", "cambiar_nombre_archivo",
             "abrir_en_navegador", "guardar_sitio_web",
             "investigar", "buscar_imagenes")

_TODAS = ("descargar_archivo", "cambiar_nombre_archivo", "investigar",
          "buscar_imagenes", "abrir_en_navegador", "guardar_sitio_web")


class _Núcleo:
    """El núcleo visto por el banco: tiene los métodos que aún le quedan."""

    def __init__(self, nombres):
        for nombre in nombres:
            setattr(self, nombre, (lambda *a, **k: "nucleo"))


class _Capacidades:
    def __init__(self, nombres):
        for nombre in nombres:
            setattr(self, nombre, (lambda *a, **k: "capacidades"))


def _banco(nombres_extraidas=EXTRAIDAS):
    return crear_banco(
        especialistas={},
        núcleo=_Núcleo([n for n in _TODAS if n not in nombres_extraidas]),
        capacidades=_Capacidades(nombres_extraidas),
    )


class PruebaDueñoDeCapacidades(unittest.TestCase):
    def test_la_fabrica_acepta_el_dueo_de_capacidades(self):
        dueños = dueños_de_registro({}, núcleo=_Núcleo(["investigar"]),
                                    capacidades=_Capacidades(EXTRAIDAS))
        self.assertEqual([d.nombre for d in dueños], ["nucleo", "capacidades"])

    def test_el_banco_resuelve_las_extraidas_contra_el_dueo_nuevo(self):
        banco = _banco()
        for nombre in EXTRAIDAS:
            montada = banco.montada(nombre)
            self.assertIsNotNone(montada, f"{nombre} quedó sin ejecutable")
            self.assertEqual(montada.dueño, "capacidades",
                             f"{nombre} la sigue ejecutando {montada.dueño}")

    def test_no_queda_ningun_nombre_en_la_lista_del_nucleo(self):
        """El corte se cierra vaciando la lista, no dejándola huérfana.

        Si quedara un nombre, el orden de registro lo pondría por delante del
        dueño de capacidades y el banco ejecutaría el cuerpo viejo del núcleo sin
        que ninguna otra prueba lo note.
        """
        self.assertEqual((), tuple(HERRAMIENTAS_DEL_NUCLEO))
        banco = _banco()
        for nombre in _TODAS:
            montada = banco.montada(nombre)
            self.assertIsNotNone(montada, f"{nombre} quedó sin montada")
            self.assertEqual("capacidades", montada.dueño,
                             f"{nombre} la sigue ejecutando otro dueño")

    def test_un_dueno_sin_prefijo_no_tapa_al_otro(self):
        """Con dos dueños sin prefijo, el ejecutable llamado es el del dueño hallado."""
        banco = _dos_dueños_sin_prefijo()
        self.assertEqual(
            banco.montada("descargar_archivo").ejecutar({"url": "x"}),
            "capacidades")
        self.assertEqual(
            banco.montada("buscar_imagenes").ejecutar({"query": "x"}), "nucleo")

    def test_dos_dueños_sin_prefijo_se_escanean_los_dos(self):
        """`_bind_exacto` no puede quedarse con el primer dueño sin prefijo.

        La política va en el `nombres` de cada dueño: aquí el núcleo sirve
        `buscar_imagenes` aunque en producción la lista esté vacía, porque lo que
        se mide es el barrido de los dos, no el reparto actual.
        """
        banco = _dos_dueños_sin_prefijo()
        for nombre in EXTRAIDAS + ("buscar_imagenes",):
            self.assertIsNotNone(banco.montada(nombre), f"{nombre} sin montada")
        self.assertEqual(banco.montada("buscar_imagenes").dueño, "nucleo")
        self.assertEqual(banco.montada("investigar").dueño, "capacidades")


def _dos_dueños_sin_prefijo():
    """El mismo barrido con dos dueños sin prefijo sirviendo cada uno lo suyo."""
    dueños = (Dueño.del_núcleo(_Núcleo(["buscar_imagenes"]),
                               nombres=("buscar_imagenes",)),
              Dueño("capacidades", _Capacidades(EXTRAIDAS), prefijo="",
                    nombres=EXTRAIDAS))
    return BancoHerramientas(tm.MANIFEST, dueños, mapa=_mapa_de_prueba())


def _mapa_de_prueba():
    from contratos.herramienta import HERRAMIENTAS_DE_CAPACIDADES
    mapa = {n: "nucleo" for n in HERRAMIENTAS_DEL_NUCLEO}
    mapa.update({n: "capacidades" for n in HERRAMIENTAS_DE_CAPACIDADES})
    return mapa


class PruebaContratoDeListas(unittest.TestCase):
    def test_los_dos_listados_no_se_solapan(self):
        from contratos import herramienta
        extraídas = getattr(herramienta, "HERRAMIENTAS_DE_CAPACIDADES", ())
        self.assertTrue(extraídas, "no hay listado de herramientas de capacidades")
        self.assertEqual(set(extraídas) & set(HERRAMIENTAS_DEL_NUCLEO), set())

    def test_las_extraidas_no_estan_en_el_listado_del_nucleo(self):
        for nombre in EXTRAIDAS:
            self.assertNotIn(nombre, HERRAMIENTAS_DEL_NUCLEO,
                             f"{nombre} sigue reclamada por el núcleo")


class PruebaNucleoSinCuerpos(unittest.TestCase):
    """El corte solo está cerrado si el método desapareció del núcleo."""

    def _funciones_del_núcleo(self):
        ruta = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        return {n.name for n in ast.walk(arbol)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    def test_el_nucleo_ya_no_define_las_capacidades_extraidas(self):
        vistas = self._funciones_del_núcleo()
        for nombre in EXTRAIDAS:
            self.assertNotIn(nombre, vistas,
                             f"dark_nucleo.py sigue definiendo {nombre}")


if __name__ == "__main__":
    unittest.main()
