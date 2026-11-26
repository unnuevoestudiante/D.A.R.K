"""`_generar_documento_directo` recibe la marca de origen, o el turno muere.

El cuerpo guarda `"desde_modulo": desde_modulo` en `_pendiente_bg`
(`dark_nucleo.py:2553`), pero la firma (`:2507`) no declara ese parámetro y el
único llamador (`:3501`) tampoco lo pasa. No es una stylista: es un `NameError`
en la ruta viva de «hazme un informe de X».

La secuencia, reproducida en vivo:

  1. `_despachar_intencion` llega a la rama `escribir_documento` (sin
     `crear_vacio`, con tema).
  2. `_generar_documento_directo` sanea el nombre, forma el paso, crea la tarea
     en el TaskManager y la **inicia**.
  3. Al escribir el slot de pendiente, evalúa `desde_modulo` → `NameError`.
  4. El aviso (`speak`) nunca sale y `_pendiente_bg` queda en `None`.

O sea: queda una tarea creada y arrancada en el TaskManager, sin pendiente que
la encole, sin ventana de corrección y sin una sola palabra al usuario. Y como
`NameError` no es `ErrorDeHerramienta`, lo traga el llamador de turno.

El dato tiene razón de ser: `_encolar_pendiente_bg` (`:7173`) reenvía
`pendiente.get("desde_modulo", False)` al worker, y el worker decide con él el
presupuesto del turno (el candado corto de 8 s es de voz; el módulo usa el suyo).
Perder la marca no es solo perder el aviso.

Las seis reglas que vigila este archivo:

  * la firma declara el parámetro;
  * el cuerpo termina y habla;
  * la marca viajó al slot;
  * sin marca, el slot registra `False` (la voz no se convierte en módulo);
  * la marca llega al worker al encolar, y la pasa el despachador;
  * y lo mismo en la otra rama que arma su propia pendiente: `escribir_codigo`.

Ref: nucleo/dark_nucleo.py.
"""
from __future__ import annotations

import inspect
import queue
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402

TEMA = "la histologia del hueso compacto"


def _nucleo_para_documento():
    """El mínimo que toca `_generar_documento_directo`: TaskManager de Mentira."""
    n = object.__new__(DarkNucleo)
    n._pendiente_bg = None
    n._pendiente_bg_lock = threading.Lock()
    n._pasos_originales = {}
    n._tareas_bg = queue.Queue()
    n._cancelar_ventana_bg = Mock()
    n.esp_tareas = Mock()
    n.esp_tareas.crear_tarea.return_value = "tarea-1"
    n._tracer = NullTracer()
    n.speak = Mock()
    return n


def _nucleo_para_codigo():
    """El mínimo que toca `_despachar_escribir_codigo` (sin pipeline).

    `_normalizar_arg_ruta` y `_crear_tarea` son las dos salidas del cuerpo hacia
    el disco y el TaskManager; lo que se mide es el slot, no lo que reserva.
    """
    n = object.__new__(DarkNucleo)
    n._pendiente_bg = None
    n._pendiente_bg_lock = threading.Lock()
    n._pasos_originales = {}
    n._tareas_bg = queue.Queue()
    n._cancelar_ventana_bg = Mock()
    n._normalizar_arg_ruta = Mock(return_value=r"C:\fake\proyecto")
    n._crear_tarea = Mock(return_value="tarea-2")
    n._tracer = NullTracer()
    n.speak = Mock()
    return n


class PruebaNombreQueFalta(unittest.TestCase):
    def setUp(self):
        self.n = _nucleo_para_documento()

    def test_la_firma_declara_la_marca_de_origen(self):
        parametros = inspect.signature(
            DarkNucleo._generar_documento_directo).parameters
        self.assertIn("desde_modulo", parametros,
                      "el cuerpo usa desde_modulo y la firma no lo declara")

    def test_el_documento_no_se_corta_antes_de_hablar(self):
        """Con HEAD esto lanza NameError: la tarea quedó creada y el aviso no."""
        aviso = self.n._generar_documento_directo("informe", TEMA,
                                                  intencion_id="i1")

        self.assertIsNotNone(aviso)
        self.n.speak.assert_called_once_with(aviso)
        self.assertIsNotNone(self.n._pendiente_bg,
                             "la pendiente se quedó en None: nadie encolará la tarea")

    def test_la_marca_viaja_hasta_el_slot(self):
        self.n._generar_documento_directo("informe", TEMA,
                                          intencion_id="i1",
                                          desde_modulo=True)

        self.assertTrue(self.n._pendiente_bg["desde_modulo"])

    def test_sin_marca_el_slot_registra_Falso(self):
        """La marca no puede caer como `True` por defecto: la voz no es módulo."""
        self.n._generar_documento_directo("informe", TEMA, intencion_id="i1")

        self.assertFalse(self.n._pendiente_bg["desde_modulo"])

    def test_al_encolar_la_marca_llega_al_worker(self):
        """Para esto existe el campo: el worker decide presupuesto con él."""
        self.n._generar_documento_directo("informe", TEMA,
                                          intencion_id="i1",
                                          desde_modulo=True)
        self.n._encolar_pendiente_bg(motivo="ventana vencida")

        tarea = self.n._tareas_bg.get_nowait()
        self.assertTrue(tarea["desde_modulo"])
        self.assertEqual("tarea-1", tarea["task_manager_id"])


class PruebaDespachador(unittest.TestCase):
    """El otro extremo del hilo: quien tiene la marca se la pasa a quien la usa."""

    def intencion(self):
        return SimpleNamespace(
            action="escribir_documento",
            params_planos=lambda: {"tema": TEMA, "tipo_documento": "informe"},
            relaciones=[],
            id="i1",
        )

    def test_el_despachador_pasa_la_marca_de_origen(self):
        n = Mock()

        mensaje = DarkNucleo._despachar_intencion(
            n, self.intencion(), desde_modulo=True)

        n._generar_documento_directo.assert_called_once()
        self.assertTrue(
            n._generar_documento_directo.call_args.kwargs.get("desde_modulo"),
            "el turno del módulo llegó al documento sin su marca")
        self.assertEqual(mensaje, n._INTENCION_EN_BG)


class PruebaMismaMarcaEnElCodigo(unittest.TestCase):
    """`escribir_codigo` arma su pendiente por su cuenta y se le caía la marca.

    La firma (`_despachar_escribir_codigo(self, intencion, desde_modulo=False)`) y
    el despachador ya la pasaban; el dict de `_pendiente_bg` no la guardaba, así
    que `_encolar_pendiente_bg` leía su `pendiente.get("desde_modulo", False)` y
    convertía el turno del módulo en un turno de voz —con el candado corto de 8 s
    en vez del presupuesto del módulo—. Sin `KeyError` y sin ruido: la marca
    simplemente dejaba de existir al encolarse.
    """

    def setUp(self):
        self.n = _nucleo_para_codigo()

    def intencion(self):
        return SimpleNamespace(
            id="i1",
            params_planos=lambda: {"tarea": "una pagina de prueba",
                                   "nombre_archivo": "index",
                                   "extension": "html"},
        )

    def test_la_pendiente_de_codigo_registra_la_marca(self):
        self.n._despachar_escribir_codigo(self.intencion(), desde_modulo=True)

        self.assertIn("desde_modulo", self.n._pendiente_bg,
                      "el turno del módulo pierde su marca al guardarse")
        self.assertTrue(self.n._pendiente_bg["desde_modulo"])

    def test_sin_marca_la_pendiente_registra_Falso(self):
        self.n._despachar_escribir_codigo(self.intencion())

        self.assertFalse(self.n._pendiente_bg["desde_modulo"])

    def test_al_encolar_el_worker_del_codigo_ve_la_marca(self):
        self.n._despachar_escribir_codigo(self.intencion(), desde_modulo=True)

        self.n._encolar_pendiente_bg(motivo="ventana vencida")

        tarea = self.n._tareas_bg.get_nowait()
        self.assertTrue(tarea["desde_modulo"],
                        "el worker va a usar el presupuesto de la voz")
        self.assertEqual("tarea-2", tarea["task_manager_id"])

    def test_el_despachador_pasa_la_marca_a_rama_de_codigo(self):
        n = Mock()
        n._despachar_escribir_codigo.return_value = n._INTENCION_EN_BG
        intencion = SimpleNamespace(
            action="escribir_codigo",
            params_planos=lambda: {"tarea": "una pagina"},
            relaciones=[], id="i1")

        mensaje = DarkNucleo._despachar_intencion(
            n, intencion, desde_modulo=True)

        n._despachar_escribir_codigo.assert_called_once_with(
            intencion, desde_modulo=True)
        self.assertEqual(mensaje, n._INTENCION_EN_BG)


if __name__ == "__main__":
    unittest.main()
