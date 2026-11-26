import ast
import json
import os
import queue
import sys
import tempfile
import threading
import unittest
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.especialista import (  # noqa: E402
    HERRAMIENTAS_CODIGO,
    HERRAMIENTAS_COMUNICACION,
    HERRAMIENTAS_TAREAS,
    HERRAMIENTAS_TERMINAL,
)
from contratos.herramienta import (  # noqa: E402
    CONFIRMACION_NO,
    CONFIRMACION_SIEMPRE,
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
)
from especialistas.especialista_conversacional import (  # noqa: E402
    EspecialistaConversacional,
)
from herramientas.fabrica import crear_banco  # noqa: E402
from herramientas.internas.model_broker import broker  # noqa: E402
from nucleo.confirmacion import AlmacenConfirmacion  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402


class _HerramientasFalsas:
    def __init__(self):
        self.llamadas = []

    def _ejecutar_falsa(self, nombre, kwargs):
        self.llamadas.append((nombre, dict(kwargs)))
        return f"ejecutada:{nombre}"

    @staticmethod
    def _resolver_ruta(ruta):
        return os.path.abspath(ruta)


def _handler_falso(nombre):
    def ejecutar(self, **kwargs):
        return self._ejecutar_falsa(nombre, kwargs)
    return ejecutar


def _dueño_falso(nombre, herramientas):
    miembros = {
        f"tool_{tool}": _handler_falso(tool)
        for tool in herramientas
    }
    return type(nombre, (_HerramientasFalsas,), miembros)()


def _herramientas_falsas_nucleo():
    miembros = {
        tool: _handler_falso(tool)
        for tool in HERRAMIENTAS_DEL_NUCLEO
    }
    return type("NucleoFalso", (_HerramientasFalsas,), miembros)()


_ARBOL_NUCLEO = None


def _arbol_nucleo():
    global _ARBOL_NUCLEO
    if _ARBOL_NUCLEO is None:
        fuente = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
            encoding="utf-8")
        _ARBOL_NUCLEO = ast.parse(fuente)
    return _ARBOL_NUCLEO


def _rama_de_intencion_usa_el_banco(accion):
    """True si la rama `action == accion` despacha por `_ejecutar_herramienta`.

    Es la forma de atar que el gate del banco se consulta por voz: si la rama
    llama al ejecutable a mano, la política del descriptor nunca se mira.
    """
    for func in ast.walk(_arbol_nucleo()):
        if (isinstance(func, ast.FunctionDef)
                and func.name == "_despachar_intencion"):
            break
    else:
        raise AssertionError("_despachar_intencion no está en el núcleo")
    for nodo in func.body:
        if not isinstance(nodo, ast.If) or not isinstance(nodo.test, ast.Compare):
            continue
        comp = nodo.test
        if not (isinstance(comp.left, ast.Name) and comp.left.id == "action"
                and len(comp.ops) == 1 and isinstance(comp.ops[0], ast.Eq)
                and isinstance(comp.comparators[0], ast.Constant)
                and comp.comparators[0].value == accion):
            continue
        llamadas = {
            h.func.attr for h in ast.walk(nodo)
            if isinstance(h, ast.Call) and isinstance(h.func, ast.Attribute)
        }
        return "_ejecutar_herramienta" in llamadas
    raise AssertionError(f"no encontré la rama action == {accion!r}")


class PruebasGateConfirmacionHerramientas(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ruta_existente = os.path.join(self.tmp.name, "existente.txt")
        with open(self.ruta_existente, "w", encoding="utf-8") as salida:
            salida.write("original")

        self.nucleo = DarkNucleo.__new__(DarkNucleo)
        self.nucleo.confirmaciones = AlmacenConfirmacion()
        self.nucleo._tracer = NullTracer()
        self.nucleo._pasos_originales = {
            "tarea-codigo": [{"tool": "escribir_codigo"}],
        }
        self.nucleo._avisos_pendientes = queue.Queue()
        self.nucleo._tareas_bg = queue.Queue()
        self.nucleo._cliente_manager = Mock()
        self.nucleo.intencion = Mock()
        self.nucleo._completar_paso = Mock()
        self.nucleo._pausar_tarea_por_fallo = Mock()
        self.nucleo._narrar_resultado = lambda texto, _intencion: texto
        # El picker reserva RAM en el núcleo antes de preguntar. Sobre un núcleo
        # a medio construir el gate devuelve False y el turno muere en `None`
        # sin llegar al proveedor: la prueba del picker necesita que sí pregunte.
        self.nucleo._preparar_modelo_de_trabajo = Mock(return_value=True)
        self.nucleo.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))

        self.codigo = _dueño_falso("Codigo", HERRAMIENTAS_CODIGO)
        self.comunicacion = _dueño_falso(
            "Comunicacion", HERRAMIENTAS_COMUNICACION)
        self.tareas = _dueño_falso("Tareas", HERRAMIENTAS_TAREAS)
        self.terminal = _dueño_falso("Terminal", HERRAMIENTAS_TERMINAL)
        self.nucleo_herramientas = _herramientas_falsas_nucleo()
        self.nucleo.esp_codigo = self.codigo
        self.nucleo.esp_comunicacion = self.comunicacion
        self.nucleo.esp_tareas = self.tareas
        self.nucleo.esp_terminal = self.terminal
        self.nucleo._banco = crear_banco(
            especialistas={
                "codigo": self.codigo,
                "comunicacion": self.comunicacion,
                "tareas": self.tareas,
                "terminal": self.terminal,
            },
            núcleo=self.nucleo_herramientas,
            normalizador=self.nucleo._normalizar_arg_ruta,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _argumentos(self, nombre):
        if nombre == "cerrar_aplicacion":
            return {"nombre": "Editor"}
        if nombre == "editar_archivo":
            return {"ruta": self.ruta_existente, "contenido_nuevo": "nuevo"}
        if nombre == "crear_recurso":
            return {
                "ruta": self.ruta_existente,
                "tipo": "archivo",
                "contenido": "nuevo",
            }
        if nombre == "guardar_sitio_web":
            return {"nombre": "mi banco", "url": "https://banco-propio.com"}
        if nombre == "cambiar_nombre_archivo":
            return {"ruta": self.ruta_existente, "nuevo_nombre": "renombrado"}
        return {}

    def _todos_los_dueños(self):
        return [
            self.codigo,
            self.comunicacion,
            self.tareas,
            self.terminal,
            self.nucleo_herramientas,
        ]

    def _llamadas(self, nombre):
        return sum(
            1 for dueño in self._todos_los_dueños()
            for llamada, _kwargs in dueño.llamadas
            if llamada == nombre
        )

    def _conversacional(self):
        conversacional = EspecialistaConversacional.__new__(
            EspecialistaConversacional)
        conversacional.router = self.nucleo
        conversacional._lock = threading.Lock()
        conversacional._speak = Mock()
        conversacional._dar_forma = lambda texto: texto
        conversacional._iniciar_traza_inferencia = Mock(return_value=None)
        conversacional._registrar_llm = Mock()
        conversacional._medir_contexto = Mock()
        conversacional._chat_model = "test"
        conversacional._chat_opts = {}
        conversacional._keep_alive = "0"
        conversacional._llm_lock = threading.Lock()
        conversacional._chat_provider = Mock()
        conversacional.cerebro = SimpleNamespace(
            responder=Mock(return_value="De inmediato."))
        return conversacional

    def _esperar_pregunta(self, conversacional):
        self.assertTrue(conversacional._speak.called)
        pregunta = conversacional._speak.call_args.args[0]
        self.assertIn("¿Confirma", pregunta)
        self.assertTrue(self.nucleo.confirmaciones.hay_pendiente())

    def test_politicas_de_confirmacion_recubren_los_36_descriptores(self):
        descriptores = self.nucleo._banco.descriptores()
        # 37 desde `planificar_proyecto`, que no pide confirmación: solo guarda el plan.
        self.assertEqual(len(descriptores), 37)
        nombres_protegidos = set()

        for descriptor in descriptores:
            with self.subTest(herramienta=descriptor.nombre):
                antes = self._llamadas(descriptor.nombre)
                self.nucleo._ejecutar_herramienta(
                    descriptor.nombre,
                    self._argumentos(descriptor.nombre),
                    {"tarea_id": "tarea-codigo", "paso_id": "p1"},
                )
                if descriptor.confirmacion != CONFIRMACION_NO:
                    nombres_protegidos.add(descriptor.nombre)
                    self.assertEqual(
                        self._llamadas(descriptor.nombre), antes,
                        "una herramienta protegida se ejecutó antes de confirmar",
                    )
                    self.assertEqual(
                        self.nucleo.confirmaciones._pendiente.accion,
                        descriptor.nombre,
                    )
                    self.nucleo.confirmaciones.resolver("no")

        self.assertEqual(
            nombres_protegidos,
            {"cerrar_aplicacion", "editar_archivo", "crear_recurso",
             "guardar_sitio_web", "cambiar_nombre_archivo"},
        )

    def test_crear_recurso_solo_confirma_si_sobrescribe_archivo(self):
        nueva = os.path.join(self.tmp.name, "nuevo.txt")
        paso = self.nucleo._ejecutar_herramienta(
            "crear_recurso",
            {"ruta": nueva, "tipo": "archivo", "contenido": "nuevo"},
        )
        self.assertTrue(paso.ok)
        self.assertEqual(self._llamadas("crear_recurso"), 1)

        carpeta = os.path.join(self.tmp.name, "carpeta")
        os.mkdir(carpeta)
        paso = self.nucleo._ejecutar_herramienta(
            "crear_recurso", {"ruta": carpeta, "tipo": "carpeta"})
        self.assertTrue(paso.ok)
        self.assertFalse(self.nucleo.confirmaciones.hay_pendiente())
        self.assertEqual(self._llamadas("crear_recurso"), 2)

    def test_comando_estructurado_confirma_cierre_y_reemplazo_total(self):
        for nombre in ("cerrar_aplicacion", "editar_archivo"):
            with self.subTest(herramienta=nombre):
                conversacional = self._conversacional()
                self.assertEqual(conversacional._ejecutar_comando({
                    "tool": nombre,
                    "args": self._argumentos(nombre),
                }), "")
                self._esperar_pregunta(conversacional)
                self.assertEqual(self._llamadas(nombre), 0)
                self.nucleo.confirmaciones.resolver("no")

    def test_picker_llm_confirma_cierre_y_reemplazo_total(self):
        for nombre in ("cerrar_aplicacion", "editar_archivo"):
            with self.subTest(herramienta=nombre):
                conversacional = self._conversacional()
                conversacional._chat_provider.complete.return_value = (
                    SimpleNamespace(
                        finished=True,
                        content=json.dumps({
                            "tool": nombre,
                            "args": self._argumentos(nombre),
                        }),
                        metrics={},
                        status_code=200,
                    )
                )
                with patch.object(broker, "asegurar", return_value=True):
                    self.assertEqual(
                        conversacional._llm_elegir_tool("hazlo"), "")
                self._esperar_pregunta(conversacional)
                self.assertEqual(self._llamadas(nombre), 0)
                self.nucleo.confirmaciones.resolver("no")

    def test_picker_llm_es_fallback_sin_clasificador(self):
        conversacional = EspecialistaConversacional.__new__(
            EspecialistaConversacional)
        conversacional.router = self.nucleo
        conversacional.cerebro = SimpleNamespace(
            procesar_texto_usuario=Mock(return_value=None),
            ctx=SimpleNamespace(registrar_pedido=Mock()),
        )
        conversacional.temas = SimpleNamespace(procesar=Mock())
        conversacional._esperando_tarea = False
        conversacional._parece_comando_desconocido = Mock(return_value=True)
        conversacional._llm_elegir_tool = Mock(return_value="resuelto")
        conversacional._speak = Mock()

        self.assertFalse(hasattr(self.nucleo, "clasificar"))
        self.assertEqual(
            conversacional.procesar_turno("abre una aplicación nueva"),
            "resuelto",
        )
        conversacional._llm_elegir_tool.assert_called_once_with(
            "abre una aplicación nueva", desde_modulo=False)

    def test_fallo_al_procesar_estilo_no_corta_el_turno(self):
        conversacional = EspecialistaConversacional.__new__(
            EspecialistaConversacional)
        conversacional.router = self.nucleo
        conversacional.cerebro = SimpleNamespace(
            procesar_texto_usuario=Mock(side_effect=RuntimeError("fallo")),
            ctx=SimpleNamespace(registrar_pedido=Mock()),
        )
        conversacional.temas = SimpleNamespace(procesar=Mock())
        conversacional._esperando_tarea = False
        conversacional._parece_comando_desconocido = Mock(return_value=False)
        conversacional._llm_chat = Mock(return_value="respuesta")

        self.assertEqual(conversacional.procesar_turno("hola"), "respuesta")

    def test_fallthrough_de_intencion_confirma_cierre_y_reemplazo_total(self):
        for nombre in ("cerrar_aplicacion", "editar_archivo"):
            with self.subTest(herramienta=nombre):
                intencion = SimpleNamespace(
                    action=nombre,
                    relaciones=[],
                    params_planos=lambda nombre=nombre: self._argumentos(nombre),
                )
                pregunta = self.nucleo._despachar_intencion(intencion)
                self.assertIn("¿Confirma", pregunta)
                self.assertEqual(self._llamadas(nombre), 0)
                self.nucleo.confirmaciones.resolver("no")

    def test_plan_de_tarea_pausa_y_reanuda_solo_tras_confirmar(self):
        pasos_restantes = [{"id": "p2", "tool": "listar_tareas", "args": {}}]
        for nombre in ("cerrar_aplicacion", "editar_archivo"):
            with self.subTest(herramienta=nombre):
                self.nucleo._completar_paso.reset_mock()
                paso = self.nucleo._ejecutar_paso_con_reintentos(
                    "tarea-1",
                    {"id": "p1", "tool": nombre,
                     "args": self._argumentos(nombre)},
                    contexto={
                        "pasos_restantes": pasos_restantes,
                        "descripcion_tarea": "plan protegido",
                    },
                )
                self.assertEqual(paso.estado, "esperando_confirmacion")
                self.assertEqual(self._llamadas(nombre), 0)
                self.assertIn("¿Confirma", self.nucleo._avisos_pendientes.get_nowait())
                self.nucleo._completar_paso.assert_not_called()

                self.nucleo.confirmaciones.resolver("sí")
                self.assertEqual(self._llamadas(nombre), 1)
                self.nucleo._completar_paso.assert_called_with(
                    "tarea-1", "p1", f"ejecutada:{nombre}")
                reanudacion = self.nucleo._tareas_bg.get_nowait()
                self.assertEqual(reanudacion["pasos"], pasos_restantes)

    def test_aceptar_confirmacion_de_capacidad_no_vuelve_a_preguntar(self):
        for nombre in ("cerrar_aplicacion", "editar_archivo"):
            with self.subTest(herramienta=nombre):
                intencion = SimpleNamespace(
                    id="intencion-1",
                    action=nombre,
                    relaciones=[],
                    params_planos=lambda nombre=nombre: self._argumentos(nombre),
                )
                pregunta = self.nucleo._pedir_confirmacion_intencion(
                    intencion, "¿Confirma la acción?")
                self.assertIn("¿Confirma", pregunta)
                self.nucleo.confirmaciones.resolver("sí")
                self.assertEqual(self._llamadas(nombre), 1)
                self.assertFalse(self.nucleo.confirmaciones.hay_pendiente())

    def test_modulo_no_puede_pedir_ni_aceptar_confirmaciones(self):
        conversacional = self._conversacional()
        resultado = conversacional._ejecutar_comando(
            {"tool": "editar_archivo", "args": self._argumentos("editar_archivo")},
            desde_modulo=True,
        )
        self.assertEqual(resultado, "")
        self.assertIn(
            "solo se puede hacer desde el equipo",
            conversacional._speak.call_args.args[0],
        )
        self.assertFalse(self.nucleo.confirmaciones.hay_pendiente())
        self.assertEqual(self._llamadas("editar_archivo"), 0)

        self.nucleo._ejecutar_herramienta(
            "cerrar_aplicacion",
            self._argumentos("cerrar_aplicacion"),
        )
        self.nucleo._command_lock = threading.Lock()
        self.nucleo.speak = Mock()
        self.nucleo._es_comando_terminal_destructivo = Mock(return_value=False)
        self.nucleo._cambio_contrasena_pendiente = False
        self.nucleo._es_peticion_cambio_contrasena = Mock(return_value=False)
        atendido = self.nucleo.handle_command("sí", desde_modulo=True)
        self.assertTrue(atendido)
        self.assertIn(
            "solo se puede hacer desde el equipo",
            self.nucleo.speak.call_args.args[0],
        )
        self.assertTrue(self.nucleo.confirmaciones.hay_pendiente())
        self.assertEqual(self._llamadas("cerrar_aplicacion"), 0)
        self.nucleo.confirmaciones.resolver("no")

        resultado_paso = self.nucleo._ejecutar_paso_con_reintentos(
            None,
            {"id": "p1", "tool": "editar_archivo",
             "args": self._argumentos("editar_archivo")},
            contexto={"desde_modulo": True},
        )
        self.assertFalse(resultado_paso.ok)
        self.assertIn(
            "solo se puede hacer desde el equipo", resultado_paso.mensaje)
        self.assertFalse(self.nucleo.confirmaciones.hay_pendiente())
        self.assertEqual(self._llamadas("editar_archivo"), 0)

    def test_despachador_pide_confirmacion_antes_de_cerrar(self):
        pregunta = self.nucleo.ejecutar_comando(
            "cerrar_aplicacion", self._argumentos("cerrar_aplicacion"))
        self.assertIn("¿Confirma", pregunta)
        self.assertEqual(self._llamadas("cerrar_aplicacion"), 0)

    def test_renombrar_es_herramienta_de_banco_y_pregunta_antes(self):
        """`cambiar_nombre_archivo` deja de ser alcanzable solo por la intención.

        Escribir en disco sin descriptor era el hueco que ETAPA 2 dejó abierto
        (residuo #1): el picker del LLM y cualquier caller del banco no tenían
        puerta. La política manda `siempre`, así que ni el banco monta la
        herramienta sin preguntar.
        """
        self.assertIn("cambiar_nombre_archivo", HERRAMIENTAS_DEL_NUCLEO
                      + HERRAMIENTAS_DE_CAPACIDADES)
        descriptor = self.nucleo._banco.resolver("cambiar_nombre_archivo")
        self.assertIsNotNone(descriptor, "renombrar no tiene descriptor de banco")
        self.assertEqual(descriptor.confirmacion, CONFIRMACION_SIEMPRE)

        self.nucleo._pregunta_confirmacion_herramienta = Mock(
            return_value="¿Confirma?")
        self.nucleo.speak = Mock()
        self.nucleo._ejecutar_herramienta(
            "cambiar_nombre_archivo",
            self._argumentos("cambiar_nombre_archivo"),
            {"origen": "intencion"},
        )
        self.assertEqual(
            self._llamadas("cambiar_nombre_archivo"), 0,
            "el banco renombró sin pedir confirmación",
        )
        self.assertEqual(
            self.nucleo.confirmaciones._pendiente.accion,
            "cambiar_nombre_archivo")
        self.nucleo.confirmaciones.resolver("no")

    def test_la_intencion_de_renombrar_pasa_por_el_banco(self):
        """La rama de `_despachar_intencion` ya no llama al ejecutable a mano.

        Mientras llamara directo a `_cambiar_nombre_archivo_intencion`, la
        política del descriptor no se consultaba nunca por voz: el `peligrosa`
        de la capacidad era la única puerta y el gate del banco quedaba
        decorado.
        """
        self.assertTrue(_rama_de_intencion_usa_el_banco(
            "cambiar_nombre_archivo"))


if __name__ == "__main__":
    unittest.main()
