"""El clúster de wallpaper e imágenes se pregunta al dueño; el núcleo lo suelta.

Es la guarda del escalón 3 del paso 3. La voz sigue teniendo sus dos puertas —
`_despachar_accion_imagenes` y `_poner_wallpaper_intencion`— pero ya no ejecutan:
preguntan al dueño de capacidades y traducen su contrato a cadena.

Lo que se rompe aquí no es un mensaje feo. `_despachar_intencion` hace
`" ".join(avisos_undo + [msg])` con lo que devuelven esas dos puertas, y
`handle_command` es `try:` … `finally:` sin `except`: un cuerpo borrado con un
call site sin conmutar lanza `AttributeError`, y un `ToolResult` que se cuele por
el adaptador lanza `TypeError`. Las dos cosas matan el turno sin haber hablado.
Por eso este archivo mide el cable (AST) y el contrato (cadena).
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.ejecutor import ToolResult  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402

RUTA_NUCLEO = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
RUTA_DUEÑO = DARK_PYTHON / "herramientas" / "internas" / "ejecutor.py"

#: Lo que el núcleo deja de definir: se ejecuta en el dueño.
CUERPOS_DEL_CORTE = (
    "_normalizar_url_imagen", "_ampliar_imagenes", "_buscar_similares_a_indice",
    "_extension_imagen_desde_url", "_descargar_imagen",
    "_descargar_todas_las_imagenes", "_instalar_wallpaper_indice",
    "_aplicar_wallpaper_desde_ruta", "instalar_wallpaper",
    "_ocultar_resultados_visuales", "_preguntar_tema_wallpaper",
)

#: Las dos puertas de la voz: siguen en el núcleo, pero solo traducen.
ADAPTADORES = ("_despachar_accion_imagenes", "_poner_wallpaper_intencion")

#: Lo que se queda a propósito. `overlay` y `speak` son del núcleo: una utilidad
#: lee el suyo y la otra dice en voz alta lo que buscó el dueño.
SE_QUEDAN_EN_EL_NUCLEO = ("_hay_imagenes_visibles", "_decir_wallpapers")

#: Cuántas veces le pregunta el núcleo a cada hoja: el recuento del cable. Las que
#: no aparecen se llamaban solo desde los dos cuerpos que también se van.
DELEGACIONES_ESPERADAS = {
    "_ocultar_resultados_visuales": 5,
    "_ampliar_imagenes": 1,
    "_buscar_similares_a_indice": 1,
    "_aplicar_wallpaper_desde_ruta": 1,
}

#: Sentencias que admite un adaptador, sin contar el docstring.
LIMITE_ADAPTADOR = 5


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


def _sentencias(func):
    cuerpo = list(func.body)
    if (cuerpo and isinstance(cuerpo[0], ast.Expr)
            and isinstance(cuerpo[0].value, ast.Constant)
            and isinstance(cuerpo[0].value.value, str)):
        cuerpo.pop(0)
    return cuerpo


def _receptor_es_el_dueño(receptor):
    return (isinstance(receptor, ast.Call)
            and isinstance(receptor.func, ast.Attribute)
            and receptor.func.attr == "_capacidades_herramientas")


def _accesos_a(nombre_hoja, raiz, *, con_dueño):
    """Líneas que tocar una hoja del cluster, con el dueño o sin él.

    Cuenta también la forma suelta —`self._accion_ui(self._ocultar_...)` pasa el
    método sin llamarlo—, que es justo la que se escapa de un censo de llamadas.
    """
    encontradas = []
    for nodo in ast.walk(raiz):
        if not isinstance(nodo, ast.Attribute) or nodo.attr != nombre_hoja:
            continue
        if _receptor_es_el_dueño(nodo.value) != con_dueño:
            continue
        encontradas.append(nodo.lineno)
    return sorted(encontradas)


# --------------------------------------------------------------------------------
# 1. El cable: qué define el núcleo y a quién le pregunta
# --------------------------------------------------------------------------------

class PruebaNucleoSinLosCuerpos(unittest.TestCase):
    def setUp(self):
        self.metodos_nucleo = _metodos_de_la_clase(NUCLEO_AST, "DarkNucleo")
        self.metodos_dueño = {n.name for n in ast.walk(DUEÑO_AST)
                              if isinstance(n, ast.FunctionDef)}

    def test_el_nucleo_no_define_ninguna_hoja_del_cluster(self):
        quedan = [m for m in CUERPOS_DEL_CORTE if m in self.metodos_nucleo]
        self.assertEqual([], quedan,
                         "escalón 3: estas capacidades se ejecutan en el dueño")

    def test_el_dueño_si_define_todas(self):
        faltan = [m for m in CUERPOS_DEL_CORTE if m not in self.metodos_dueño]
        self.assertEqual([], faltan)

    def test_las_dos_puertas_de_la_voz_siguen_en_el_nucleo(self):
        """Borrarlas del todo sería borrar la traducción de contrato."""
        for nombre in ADAPTADORES:
            self.assertIn(nombre, self.metodos_nucleo, nombre)

    def test_los_adaptadores_miden_una_llamada_no_una_capacidad(self):
        for nombre in ADAPTADORES:
            with self.subTest(adaptador=nombre):
                utile = len(_sentencias(_funcion(NUCLEO_AST, nombre)))
                self.assertLessEqual(
                    utile, LIMITE_ADAPTADOR,
                    f"{nombre} volvió a {utile} sentencias: la capacidad está "
                    f"regresando al núcleo")

    def test_cada_adaptador_pregunta_al_dueño_una_sola_vez(self):
        for nombre in ADAPTADORES:
            with self.subTest(adaptador=nombre):
                dentro = _accesos_a(nombre, _funcion(NUCLEO_AST, nombre),
                                     con_dueño=True)
                self.assertEqual(1, len(dentro))

    def test_lo_que_se_queda_por_decision_sigue_estando(self):
        """Nombra las dos excepciones: si una se va sin decirlo, esto la llama."""
        for nombre in SE_QUEDAN_EN_EL_NUCLEO:
            self.assertIn(nombre, self.metodos_nucleo, nombre)

    def test_el_nucleo_pregunta_cada_hoja_las_veces_acordadas(self):
        preguntadas = {
            nombre: len(_accesos_a(nombre, NUCLEO_AST, con_dueño=True))
            for nombre in CUERPOS_DEL_CORTE
        }
        self.assertEqual(DELEGACIONES_ESPERADAS,
                         {n: c for n, c in preguntadas.items() if c})

    def test_nadie_llama_a_una_hoja_sin_pasar_por_el_dueño(self):
        """La valla del silencio: `self._descargar_imagen(...)` ya no existe."""
        sueltas = [(n, l) for n in CUERPOS_DEL_CORTE
                   for l in _accesos_a(n, NUCLEO_AST, con_dueño=False)]
        self.assertEqual([], sorted(sueltas))


# --------------------------------------------------------------------------------
# 2. El contrato: la voz recibe cadena, nunca un paso
# --------------------------------------------------------------------------------

def _dueño_falso(**respuestas):
    """El dueño con las hojas dobladas: lo que devuelve cada una."""
    return SimpleNamespace(**{
        nombre: Mock(return_value=respuestas.get(nombre, ""))
        for nombre in set(CUERPOS_DEL_CORTE) | set(ADAPTADORES)
    })


def _nucleo_de_turno(dueño):
    nucleo = object.__new__(DarkNucleo)
    nucleo._capacidades = dueño
    nucleo.speak = Mock()
    nucleo.overlay = SimpleNamespace(estado=Mock(return_value="showing_results"))
    return nucleo


class PruebaElContratoDelAdaptador(unittest.TestCase):
    """Lo que consume `_despachar_intencion` tiene que ser `str`."""

    def test_el_paso_del_dueño_se_vuelve_silencio(self):
        """`_ya_hablado` trae el mensaje vacío: la voz no lo repite narrándolo."""
        dueño = _dueño_falso(_despachar_accion_imagenes=ToolResult(True, "", None))
        nucleo = _nucleo_de_turno(dueño)
        msg = nucleo._despachar_accion_imagenes({"accion": "limpiar"})
        self.assertIsInstance(msg, str)
        self.assertEqual("", msg)

    def test_la_frase_del_url_sigue_viajando_como_texto(self):
        """La rama `url` no habla: la narra el turno, así que no se pierde."""
        dueño = _dueño_falso(
            _poner_wallpaper_intencion="Fondo de pantalla actualizado.")
        nucleo = _nucleo_de_turno(dueño)
        msg = nucleo._poner_wallpaper_intencion({"url": "https://x.test/1.jpg"})
        self.assertEqual("Fondo de pantalla actualizado.", msg)

    def test_un_paso_con_detalle_no_se_cuela_en_el_join_del_turno(self):
        """El TypeError aquí es el turno muerto: `_despachar_intencion` hace join.

        `avisos_undo + [msg]` solo acepta cadenas y `handle_command` no tiene
        `except`: si el adaptador devuelve el `ToolResult` crudo, Dark se calla.
        """
        dueño = _dueño_falso(_despachar_accion_imagenes=ToolResult(
            False, "", "precondition:accion_imagenes sin tarjetas visibles"))
        nucleo = _nucleo_de_turno(dueño)
        msg = nucleo._despachar_accion_imagenes({"accion": "descargar"})
        avisos_undo = ["Deshice el fondo anterior."]
        self.assertEqual("Deshice el fondo anterior. ",
                         " ".join(avisos_undo + [msg]))

    def test_el_adaptador_entrega_el_dict_como_kwargs(self):
        """La firma del dueño es `**params`; la del turno es un dict plano."""
        dueño = _dueño_falso(_despachar_accion_imagenes=ToolResult(True, "", None))
        nucleo = _nucleo_de_turno(dueño)
        nucleo._despachar_accion_imagenes(
            {"accion": "descargar", "indices": [1], "count": 2})
        dueño._despachar_accion_imagenes.assert_called_once_with(
            accion="descargar", indices=[1], count=2)

    def test_el_wallpaper_del_turno_pasa_el_dict_plano(self):
        dueño = _dueño_falso(_poner_wallpaper_intencion="")
        nucleo = _nucleo_de_turno(dueño)
        nucleo._poner_wallpaper_intencion({"tema": "gatos"})
        dueño._poner_wallpaper_intencion.assert_called_once_with(tema="gatos")

    def test_un_none_del_dueño_no_rompe_el_join(self):
        dueño = _dueño_falso(_poner_wallpaper_intencion=None)
        nucleo = _nucleo_de_turno(dueño)
        self.assertEqual("", nucleo._poner_wallpaper_intencion({"tema": ""}))


# --------------------------------------------------------------------------------
# 3. La delegación que no toca ninguna prueba de voz
# --------------------------------------------------------------------------------

class PruebaLaRevisionDelFondoPreguntaAlDueño(unittest.TestCase):
    def test_deshacer_un_fondo_aplica_su_ruta_el_dueño(self):
        dueño = _dueño_falso(_aplicar_wallpaper_desde_ruta="Fondo restaurado")
        nucleo = _nucleo_de_turno(dueño)
        previa = SimpleNamespace(action="poner_wallpaper",
                                 estado_previo="C:\\fondo-anterior.bmp",
                                 params_planos=Mock(return_value={}))
        resultado = DarkNucleo._ejecutar_undo(nucleo, previa)
        dueño._aplicar_wallpaper_desde_ruta.assert_called_once_with(
            "C:\\fondo-anterior.bmp")
        self.assertEqual("", resultado)


if __name__ == "__main__":
    unittest.main()
