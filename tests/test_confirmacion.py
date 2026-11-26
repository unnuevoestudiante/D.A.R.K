import ast
import sys
import threading
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.externas.terminal import DarkTerminal  # noqa: E402
from nucleo.confirmacion import (  # noqa: E402
    AlmacenConfirmacion,
    CONFIRMACION_TTL_SEGUNDOS,
    confirmacion_caducada,
    interpretar_respuesta,
)
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
)


def _neutralizar_compuertas_tv(nucleo):
    """Apaga las cuatro compuertas de tele en el dueño de capacidades.

    `handle_command` ya no las decide: las pregunta a `_capacidades`, y sobre un
    núcleo montado a mano ese dueño ejecutaría la frase de verdad —una escritura
    de configuración o una orden de canal— en pruebas que van de otra cosa. El
    dueño se construye por la vía de producción (`_capacidades_herramientas`,
    que cachea en `_capacidades`), así que lo que se tapa son sus manejadores.
    """
    dueño = nucleo._capacidades_herramientas()
    for nombre in ("_manejar_config_tv", "_manejar_destino_ui",
                   "_manejar_netflix_tv", "_manejar_control_tv"):
        setattr(dueño, nombre, Mock(return_value=None))
    return nucleo


_ARBOLES = {}


def _arbol(relativa):
    """Analiza un fichero del núcleo una sola vez: son más de 7000 líneas."""
    if relativa not in _ARBOLES:
        fuente = (DARK_PYTHON / relativa).read_text(encoding="utf-8")
        _ARBOLES[relativa] = ast.parse(fuente)
    return _ARBOLES[relativa]


def _funciones_con_literal_de_sino(relativa):
    """Nombres de método que vuelven a escribir su propio vocabulario."""
    raiz = _arbol(relativa)
    marcadas = set()
    for func in (n for n in ast.walk(raiz) if isinstance(n, ast.FunctionDef)):
        for nodo in ast.walk(func):
            if isinstance(nodo, ast.Set) and any(
                    isinstance(elto, ast.Constant)
                    and isinstance(elto.value, str)
                    and elto.value in {"dale", "olvídalo"}
                    for elto in nodo.elts):
                marcadas.add(func.name)
                break
    return marcadas


_AFIRMATIVAS_ANTIGUAS = {
    "sí", "si", "claro", "dale", "hazlo", "ejecuta", "ejecútalo",
    "ejecutalo", "adelante", "ok", "vale", "confirmo", "ejecutalas",
    "ejecutalos", "hazlas", "yes", "yep", "confirmar", "ejecútala",
    "ejecutala", "autoriza", "autorizo",
}
_NEGATIVAS_ANTIGUAS = {
    "no", "cancela", "cancelalo", "cancélalo", "para", "detente",
    "olvidalo", "olvídalo", "mejor", "nada", "cancelalas", "nope",
    "cancelar", "detén", "deten",
}


class PruebasVocabularioConfirmacion(unittest.TestCase):
    def test_union_de_vocabularios_anteriores(self):
        for frase in _AFIRMATIVAS_ANTIGUAS:
            with self.subTest(frase=frase):
                self.assertEqual(interpretar_respuesta(frase), "afirmativo")
        for frase in _NEGATIVAS_ANTIGUAS:
            with self.subTest(frase=frase):
                self.assertEqual(interpretar_respuesta(frase), "negativo")
        self.assertEqual(interpretar_respuesta("sí, no"), "neutro")
        self.assertEqual(interpretar_respuesta("sí,"), "afirmativo")
        self.assertEqual(interpretar_respuesta("no,"), "negativo")
        self.assertEqual(interpretar_respuesta("quizá luego"), "neutro")
        self.assertEqual(interpretar_respuesta("mejor"), "negativo")
        self.assertEqual(
            interpretar_respuesta("mejor abre la calculadora"), "neutro")

    def test_formas_singular_y_plural_se_interpretan_igual(self):
        self.assertEqual(interpretar_respuesta("ejecútalo"), "afirmativo")
        self.assertEqual(interpretar_respuesta("ejecútalas"), "afirmativo")

    def test_caducidad_incluye_el_limite_de_30_segundos(self):
        self.assertEqual(CONFIRMACION_TTL_SEGUNDOS, 30)
        self.assertFalse(confirmacion_caducada(100, ahora=129.999))
        self.assertTrue(confirmacion_caducada(100, ahora=130))


class PruebasCaducidadAlmacenes(unittest.TestCase):
    def test_intencion_acepta_antes_del_limite_y_descarta_despues(self):
        almacen = AlmacenConfirmacion()
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = almacen
        nucleo.intencion = gestor
        nucleo._despachar_intencion = Mock(return_value="cerrada")
        nucleo._narrar_resultado = Mock(side_effect=lambda texto, _intencion: texto)
        nucleo._armar_ventana_bg = Mock()
        intencion = gestor.interpretar("cierra chrome")
        with patch("nucleo.confirmacion.time.monotonic", return_value=100):
            nucleo._pedir_confirmacion_intencion(intencion, "¿Cierro Chrome?")
        with patch("nucleo.confirmacion.time.monotonic", return_value=129.999):
            resultado = almacen.resolver("sí")
        self.assertEqual(resultado.mensaje, "cerrada")
        nucleo._despachar_intencion.assert_called_once_with(
            intencion, ya_confirmado=True)

        intencion = gestor.interpretar("cierra edge")
        with patch("nucleo.confirmacion.time.monotonic", return_value=130):
            nucleo._pedir_confirmacion_intencion(intencion, "¿Cierro Edge?")
        with patch("nucleo.confirmacion.time.monotonic", return_value=160):
            self.assertIsNone(almacen.resolver("sí"))
        self.assertIsNone(gestor.confirmacion_pendiente())

    def test_tarea_acepta_antes_del_limite_y_descarta_despues(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = AlmacenConfirmacion()
        nucleo._cliente_manager = Mock()
        nucleo._ejecutar_tareas = Mock()
        nucleo.speak = Mock()
        with patch("nucleo.confirmacion.time.monotonic", return_value=129.999):
            nucleo._pedir_confirmacion_tareas([])
        self.assertEqual(nucleo.confirmaciones._pendiente.origen, "tareas")
        with patch("nucleo.confirmacion.time.monotonic", return_value=129.999):
            resultado = nucleo.confirmaciones.resolver("sí")
        self.assertTrue(resultado.atendida)
        nucleo._ejecutar_tareas.assert_called_once_with([])
        with patch("nucleo.confirmacion.time.monotonic", return_value=200):
            nucleo._pedir_confirmacion_tareas([])
        with patch("nucleo.confirmacion.time.monotonic", return_value=230):
            self.assertIsNone(nucleo.confirmaciones.resolver("sí"))
        self.assertFalse(nucleo.confirmaciones.hay_pendiente())
        nucleo._ejecutar_tareas.assert_called_once_with([])

    def test_terminal_acepta_antes_del_limite_y_descarta_despues(self):
        with tempfile.TemporaryDirectory() as directorio:
            almacen = AlmacenConfirmacion()
            terminal = DarkTerminal(
                raiz_workspace=directorio,
                almacen_confirmaciones=almacen,
            )
            ejecutar = Mock(return_value={"ok": True, "mensaje": "hecho"})
            terminal._ejecutar_comando = ejecutar
            with patch("nucleo.confirmacion.time.monotonic", return_value=100):
                terminal.ejecutar_operacion(
                    "crear_directorio", {"ruta": "nuevo"}, "coder")
            self.assertEqual(almacen._pendiente.origen, "terminal")
            with patch("nucleo.confirmacion.time.monotonic", return_value=129.999):
                self.assertTrue(terminal.hay_confirmacion_pendiente())
            with patch("nucleo.confirmacion.time.monotonic", return_value=130):
                self.assertIsNone(almacen.resolver("sí"))
            ejecutar.assert_not_called()
            self.assertFalse(terminal.hay_confirmacion_pendiente())


class PruebasAlmacenConfirmacion(unittest.TestCase):
    def _crear_nucleo_completo(self, almacen):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = almacen
        nucleo._command_lock = threading.Lock()
        nucleo._es_comando_terminal_destructivo = Mock(return_value=False)
        nucleo._actualizar_perfil_conductual = Mock()
        nucleo.cerebro = SimpleNamespace(
            procesar_texto_usuario=Mock(return_value=None),
            ctx=SimpleNamespace(registrar_pedido=Mock()),
        )
        nucleo._temas_registrar_accion = Mock()
        nucleo._registrar_menciones_apps = Mock()
        nucleo._cancelar_idle_diferido = Mock()
        nucleo._chequear_correccion_cache = Mock()
        nucleo._chequear_pendiente_bg = Mock(return_value=False)
        nucleo._chequear_pendiente_rapida = Mock()
        nucleo._respuesta_casual_rapida = Mock(return_value=None)
        nucleo._temas_turno = Mock(return_value=None)
        _neutralizar_compuertas_tv(nucleo)
        nucleo.esp_comunicacion = SimpleNamespace(
            hay_aviso_pendiente=Mock(return_value=False))
        nucleo._manejar_diagnostico_terminal = Mock(return_value=False)
        #: El turno de cambio de contraseña va delante del almacén.
        nucleo._cambio_contrasena_pendiente = False
        nucleo._es_peticion_cambio_contrasena = Mock(return_value=False)
        nucleo._tracer = SimpleNamespace(
            measure=Mock(return_value=nullcontext()))
        nucleo.esp_conversacion = SimpleNamespace(temas=None)
        nucleo._silenciar_local = SimpleNamespace(activo=False)
        nucleo.intencion = GestorIntenciones(CAPACIDADES_NUCLEO)
        nucleo.entidades = None
        #: Sin filtro semántico: la degradación que `__init__` aplica si el ONNX no carga.
        nucleo.clasificador_semantico = None
        nucleo._requiere_cautela_por_horario = Mock(return_value=False)
        nucleo._es_accion_rapida = Mock(return_value=False)
        nucleo._despachar_intencion = Mock(return_value="Acción completada.")
        nucleo._narrar_resultado = Mock(
            side_effect=lambda mensaje, _intencion: mensaje)
        nucleo._marcar_resultado_intencion = Mock()
        nucleo.speak = Mock()
        return nucleo

    def test_no_y_no_gracias_cancelan_pendiente(self):
        for respuesta in ("no", "no gracias"):
            with self.subTest(respuesta=respuesta):
                almacen = AlmacenConfirmacion()
                rechazar = Mock(return_value="Cancelado.")
                ejecutar_pendiente = Mock()
                almacen.solicitar(
                    ejecutar=ejecutar_pendiente,
                    rechazar=rechazar,
                    pregunta="¿Cierro Chrome?",
                    origen="herramienta",
                    accion="cerrar_aplicacion",
                    argumentos={"nombre": "chrome"},
                )
                nucleo = self._crear_nucleo_completo(almacen)

                self.assertTrue(nucleo.handle_command(respuesta))

                self.assertFalse(almacen.hay_pendiente())
                rechazar.assert_called_once_with()
                ejecutar_pendiente.assert_not_called()
                nucleo.speak.assert_called_once_with("Cancelado.")

    def test_no_mejor_orden_nueva_se_procesa(self):
        almacen = AlmacenConfirmacion()
        rechazar = Mock(return_value="Cancelado.")
        ejecutar_pendiente = Mock()
        almacen.solicitar(
            ejecutar=ejecutar_pendiente,
            rechazar=rechazar,
            pregunta="¿Cierro Chrome?",
            origen="herramienta",
            accion="cerrar_aplicacion",
            argumentos={"nombre": "chrome"},
        )
        nucleo = self._crear_nucleo_completo(almacen)

        self.assertTrue(
            nucleo.handle_command("no, mejor abre la calculadora"))

        self.assertFalse(almacen.hay_pendiente())
        rechazar.assert_called_once_with()
        ejecutar_pendiente.assert_not_called()
        nucleo._despachar_intencion.assert_called_once()
        self.assertEqual(
            nucleo._despachar_intencion.call_args.args[0].action,
            "abrir_aplicacion",
        )
        nucleo.speak.assert_called_once_with("Acción completada.")

    def test_no_cierra_chrome_cancela_y_pide_confirmacion_nueva(self):
        almacen = AlmacenConfirmacion()
        rechazar = Mock(return_value="Cancelado.")
        ejecutar_pendiente = Mock()
        almacen.solicitar(
            ejecutar=ejecutar_pendiente,
            rechazar=rechazar,
            pregunta="¿Cierro Edge?",
            origen="herramienta",
            accion="cerrar_aplicacion",
            argumentos={"nombre": "edge"},
        )
        nucleo = self._crear_nucleo_completo(almacen)

        self.assertTrue(nucleo.handle_command("no, cierra chrome"))

        self.assertTrue(almacen.hay_pendiente())
        self.assertEqual(almacen._pendiente.origen, "intencion")
        self.assertEqual(almacen._pendiente.accion, "cerrar_aplicacion")
        self.assertEqual(
            almacen._pendiente.argumentos["nombre"], "chrome")
        rechazar.assert_called_once_with()
        ejecutar_pendiente.assert_not_called()
        nucleo._despachar_intencion.assert_not_called()
        nucleo.speak.assert_called_once()

    def test_respuesta_neutra_descarta_pendientes_de_todos_los_origenes(self):
        for origen in ("intencion", "tareas", "terminal"):
            with self.subTest(origen=origen):
                almacen = AlmacenConfirmacion()
                ejecutar = Mock()
                descartar = Mock()
                almacen.solicitar(
                    ejecutar=ejecutar,
                    pregunta="¿Ejecuto?",
                    origen=origen,
                    al_descartar=descartar,
                )

                self.assertIsNone(almacen.resolver("texto irrelevante"))
                self.assertFalse(almacen.hay_pendiente())
                descartar.assert_called_once_with()
                ejecutar.assert_not_called()

    def test_si_confirma_y_no_cancela_sin_ejecutar(self):
        aceptar = AlmacenConfirmacion()
        ejecutar = Mock(return_value="hecho")
        aceptar.solicitar(
            ejecutar=ejecutar, pregunta="¿Ejecuto?", origen="intencion")
        self.assertEqual(aceptar.resolver("sí").mensaje, "hecho")
        ejecutar.assert_called_once_with()

        cancelar = AlmacenConfirmacion()
        ejecutar_cancelado = Mock()
        cancelar.solicitar(
            ejecutar=ejecutar_cancelado, pregunta="¿Ejecuto?",
            origen="tareas")
        resultado = cancelar.resolver("no")
        self.assertEqual(resultado.mensaje, "Cancelado.")
        ejecutar_cancelado.assert_not_called()
        self.assertFalse(cancelar.hay_pendiente())

    def test_texto_nuevo_cancela_confirmacion_y_llega_a_intencion(self):
        almacen = AlmacenConfirmacion()
        ejecutar_pendiente = Mock()
        descartar = Mock()
        almacen.solicitar(
            ejecutar=ejecutar_pendiente,
            pregunta="¿Cierro Chrome?",
            origen="herramienta",
            accion="cerrar_aplicacion",
            al_descartar=descartar,
        )
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = almacen
        nucleo._command_lock = threading.Lock()
        nucleo._es_comando_terminal_destructivo = Mock(return_value=False)
        nucleo._actualizar_perfil_conductual = Mock()
        nucleo.cerebro = SimpleNamespace(
            procesar_texto_usuario=Mock(return_value=None),
            ctx=SimpleNamespace(registrar_pedido=Mock()),
        )
        nucleo._temas_registrar_accion = Mock()
        nucleo._registrar_menciones_apps = Mock()
        nucleo._cancelar_idle_diferido = Mock()
        nucleo._chequear_correccion_cache = Mock()
        nucleo._chequear_pendiente_bg = Mock(return_value=False)
        nucleo._chequear_pendiente_rapida = Mock()
        nucleo._respuesta_casual_rapida = Mock(return_value=None)
        nucleo._temas_turno = Mock(return_value=None)
        _neutralizar_compuertas_tv(nucleo)
        nucleo.esp_comunicacion = SimpleNamespace(
            hay_aviso_pendiente=Mock(return_value=False))
        nucleo._manejar_diagnostico_terminal = Mock(return_value=False)
        #: El turno de cambio de contraseña va delante del almacén.
        nucleo._cambio_contrasena_pendiente = False
        nucleo._es_peticion_cambio_contrasena = Mock(return_value=False)
        nucleo._tracer = SimpleNamespace(
            measure=Mock(return_value=nullcontext()))
        nucleo.esp_conversacion = SimpleNamespace(temas=None)
        nucleo._silenciar_local = SimpleNamespace(activo=False)
        nucleo.intencion = GestorIntenciones(CAPACIDADES_NUCLEO)
        nucleo.entidades = None
        #: Sin filtro semántico: la degradación que `__init__` aplica si el ONNX no carga.
        nucleo.clasificador_semantico = None
        nucleo._requiere_cautela_por_horario = Mock(return_value=False)
        nucleo._es_accion_rapida = Mock(return_value=False)
        nucleo._despachar_intencion = Mock(return_value="Calculadora abierta.")
        nucleo._narrar_resultado = Mock(side_effect=lambda mensaje, _intencion: mensaje)
        nucleo._marcar_resultado_intencion = Mock()
        nucleo.speak = Mock()

        self.assertTrue(nucleo.handle_command("mejor abre la calculadora"))

        self.assertFalse(almacen.hay_pendiente())
        descartar.assert_called_once_with()
        ejecutar_pendiente.assert_not_called()
        nucleo._despachar_intencion.assert_called_once()
        self.assertEqual(
            nucleo._despachar_intencion.call_args.args[0].action,
            "abrir_aplicacion",
        )
        nucleo.speak.assert_called_once_with("Calculadora abierta.")

    def test_nueva_pendiente_sustituye_y_avisa(self):
        almacen = AlmacenConfirmacion()
        vieja = Mock()
        nueva = Mock(return_value="hecho")
        descartada = Mock()
        almacen.solicitar(
            ejecutar=vieja,
            pregunta="¿Ejecuto la primera?",
            origen="intencion",
            al_descartar=descartada,
        )
        pregunta = almacen.solicitar(
            ejecutar=nueva,
            pregunta="¿Ejecuto la segunda?",
            origen="herramienta",
            accion="cerrar_aplicacion",
            argumentos={"nombre": "Chrome"},
        )

        self.assertIn("La confirmación anterior fue sustituida", pregunta)
        descartada.assert_called_once_with()
        self.assertEqual(almacen._pendiente.origen, "herramienta")
        self.assertEqual(almacen._pendiente.accion, "cerrar_aplicacion")
        self.assertEqual(almacen._pendiente.argumentos, {"nombre": "Chrome"})
        self.assertEqual(almacen.resolver("sí").mensaje, "hecho")
        vieja.assert_not_called()
        nueva.assert_called_once_with()

    def test_pendiente_caducada_no_se_anuncia_como_sustituida(self):
        almacen = AlmacenConfirmacion()
        descartada = Mock()
        with patch("nucleo.confirmacion.time.monotonic", return_value=100):
            almacen.solicitar(
                ejecutar=Mock(),
                pregunta="¿Ejecuto la primera?",
                origen="intencion",
                al_descartar=descartada,
            )
        with patch("nucleo.confirmacion.time.monotonic", return_value=130):
            pregunta = almacen.solicitar(
                ejecutar=Mock(),
                pregunta="¿Ejecuto la segunda?",
                origen="herramienta",
            )
        self.assertEqual(pregunta, "¿Ejecuto la segunda?")
        descartada.assert_called_once_with()

    def test_respuesta_caducada_no_ejecuta_y_limpia(self):
        almacen = AlmacenConfirmacion()
        ejecutar = Mock()
        descartada = Mock()
        with patch("nucleo.confirmacion.time.monotonic", return_value=100):
            almacen.solicitar(
                ejecutar=ejecutar,
                pregunta="¿Ejecuto?",
                origen="test",
                al_descartar=descartada,
            )
        with patch("nucleo.confirmacion.time.monotonic", return_value=130):
            self.assertIsNone(almacen.resolver("sí"))
        ejecutar.assert_not_called()
        descartada.assert_called_once_with()
        self.assertFalse(almacen.hay_pendiente())

    def test_handle_command_consulta_el_almacen_en_un_solo_gate(self):
        almacen = AlmacenConfirmacion()
        ejecutar = Mock(return_value="confirmada")
        almacen.solicitar(
            ejecutar=ejecutar,
            pregunta="¿Ejecuto?",
            origen="test",
        )
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = almacen
        nucleo._command_lock = threading.Lock()
        nucleo._es_comando_terminal_destructivo = Mock(return_value=False)
        nucleo._cambio_contrasena_pendiente = False
        nucleo._es_peticion_cambio_contrasena = Mock(return_value=False)
        nucleo._temas_registrar_accion = Mock()
        nucleo._registrar_menciones_apps = Mock()
        nucleo.speak = Mock()

        self.assertTrue(nucleo.handle_command("sí"))
        nucleo.speak.assert_called_once_with("confirmada")
        ejecutar.assert_called_once_with()


class PruebasVocabularioUnicoEnElNucleo(unittest.TestCase):
    """El sí/no se lee una sola vez, y la única excepción es la que se declaró.

    La ETAPA 1a unificó los tres vocabularios de la auditoría (§3.2). Sobrevivió
    el método muerto de la cola de tareas con el suyo, y el del cambio de
    contraseña queda como excepción deliberada del usuario: es el flujo de acceso,
    sensible, y no se toca. Este pin admite esa excepción y ninguna más.
    """

    def test_la_cola_de_tareas_no_procesa_su_propia_confirmacion(self):
        nombres = {
            n.name for n in ast.walk(_arbol("nucleo/dark_nucleo.py"))
            if isinstance(n, ast.FunctionDef)
        }
        self.assertNotIn("_procesar_confirmacion_pendiente", nombres)

    def test_el_unico_literal_de_sino_que_queda_es_el_del_acceso(self):
        self.assertEqual(
            _funciones_con_literal_de_sino("nucleo/dark_nucleo.py"),
            {"_procesar_confirmacion_cambio_contrasena"},
        )


def _funciones(relativa, clase):
    for nodo in ast.walk(_arbol(relativa)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
            return {n.name: n for n in nodo.body if isinstance(n, ast.FunctionDef)}
    raise AssertionError(f"{relativa} no tiene la clase {clase}")


def _tipos_resueltos_por_comparacion(relativa, clase, metodos):
    """Cadenas contra las que estos métodos comparan la variable `tipo`."""
    funcs = _funciones(relativa, clase)
    resueltas = set()
    for nombre in metodos:
        for nodo in ast.walk(funcs[nombre]):
            if not isinstance(nodo, ast.Compare):
                continue
            if not (isinstance(nodo.left, ast.Name) and nodo.left.id == "tipo"):
                continue
            for operador, comparador in zip(nodo.ops, nodo.comparators):
                if (isinstance(operador, (ast.Eq, ast.NotEq))
                        and isinstance(comparador, ast.Constant)
                        and isinstance(comparador.value, str)):
                    resueltas.add(comparador.value)
    return resueltas


class PruebasConfirmacionFueraDelConversacional(unittest.TestCase):
    """El turno de charla no decide confirmaciones: las decide `handle_command`.

    Desde que se retiró el clasificador, el conversacional lleva fijado
    `clasificacion = {"tipo": "charla"}` (ec:488), así que sus ramas de
    `confirmacion`, `comando`, `tarea_larga`, `menu` y `orden_modulo` son
    inalcanzables. La de confirmación era un agujero: llamaba a
    `router.procesar_confirmacion`, que resuelve el almacén sin `bloquear`, y
    dejaría que un peer de módulo respondiera un sí que solo procede del
    equipo. Se borran las ramas y este pin no deja que vuelvan.
    """

    CONVERSACIONAL = "especialistas/especialista_conversacional.py"

    def test_el_turno_de_charla_no_resuelve_ninguna_confirmacion(self):
        conversacional = _funciones(
            self.CONVERSACIONAL, "EspecialistaConversacional")["procesar_turno"]
        llamadas = {
            n.func.attr for n in ast.walk(conversacional)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "router"
        }
        self.assertNotIn("procesar_confirmacion", llamadas)

    def test_ningun_turno_del_conversacional_vuelve_a_ramificarse_por_tipo(self):
        for metodo in ("procesar_turno", "_turno_en_espera"):
            with self.subTest(metodo=metodo):
                self.assertEqual(
                    _tipos_resueltos_por_comparacion(
                        self.CONVERSACIONAL, "EspecialistaConversacional",
                        (metodo,)),
                    set(),
                    f"{metodo} sigue bifurcándose por un `tipo` que ya no se calcula",
                )
