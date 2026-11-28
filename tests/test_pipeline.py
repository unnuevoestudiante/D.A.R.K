"""Pruebas de integración del router web, tareas y generación de código."""
import io
import json
import queue
import sys
import tempfile
import threading
import unittest
from collections import defaultdict
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from acceso import FachadaAcceso  # noqa: E402
from contratos.contratos import PasoResultado  # noqa: E402
from especialistas.especialista_codigo import EspecialistaCodigo  # noqa: E402
from especialistas.especialista_tareas import EspecialistaTareas  # noqa: E402
from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from herramientas.internas.tracer import TurnTracer  # noqa: E402
from nucleo.confirmacion import AlmacenConfirmacion  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402


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


class PruebasPipeline(unittest.TestCase):
    def _crear_nucleo_de_prueba(self, tareas=None, codigo=None):
        nucleo = object.__new__(DarkNucleo)
        nucleo.esp_tareas = tareas or Mock()
        nucleo.esp_codigo = codigo or Mock()
        nucleo.esp_comunicacion = Mock()
        nucleo.esp_terminal = Mock()
        nucleo.confirmaciones = AlmacenConfirmacion()
        nucleo.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))
        nucleo._tracer = NullTracer()
        nucleo._llm_lock = threading.Lock()
        nucleo._http = Mock()
        return nucleo

    def _crear_ejecutor_de_prueba(self):
        """El dueño de capacidades, montado sin arranque.

        La búsqueda web se fue del núcleo con el último corte, así que lo que
        compone el prompt y lo que elige entre síntesis y títulos ya no vive en
        `DarkNucleo`. Se construye por `__new__` a propósito: se mide el cuerpo
        de la herramienta, no el arranque del ejecutor.
        """
        e = EjecutorHerramientas.__new__(EjecutorHerramientas)
        e._s = Servicios()
        e._llm_lock = threading.Lock()
        e._http = Mock()
        e._ultimos_resultados = None
        return e

    def test_cierre_del_tracer_del_nucleo_es_idempotente_y_eventos_tardios_visibles(self):
        nucleo = self._crear_nucleo_de_prueba()
        tracer = TurnTracer(turn_id="cierre-core")
        nucleo._tracer = tracer
        salida = io.StringIO()

        with redirect_stdout(salida):
            nucleo._finalizar_tracer_turno()
            nucleo._finalizar_tracer_turno()
            tracer.record("worker_late", 2.0)

        self.assertIsInstance(nucleo._tracer, NullTracer)
        self.assertEqual(salida.getvalue().count("=== Turno cierre-core"), 1)
        self.assertIn("[DARK-STAGE-LATE]", salida.getvalue())

    def test_fin_de_peticion_modulo_no_reemplaza_un_tracer_de_voz_nuevo(self):
        nucleo = self._crear_nucleo_de_prueba()
        tracer_modulo = TurnTracer(turn_id="modulo")
        tracer_voz = TurnTracer(turn_id="voz-nuevo")
        nucleo._tracer = tracer_voz
        salida = io.StringIO()

        with redirect_stdout(salida):
            nucleo._finalizar_tracer_modulo(tracer_modulo, propio=True)

        self.assertIs(nucleo._tracer, tracer_voz)
        self.assertEqual(salida.getvalue().count("=== Turno modulo"), 1)
        self.assertNotIn("=== Turno voz-nuevo", salida.getvalue())

    def test_accion_pendiente_se_cierra_antes_de_respuesta_casual(self):
        nucleo = self._crear_nucleo_de_prueba()
        eventos = []
        nucleo._command_lock = threading.Lock()
        nucleo.esp_terminal = Mock()
        nucleo.esp_terminal.hay_confirmacion_pendiente.return_value = False
        nucleo._cambio_contrasena_pendiente = False
        nucleo._es_comando_terminal_destructivo = Mock(return_value=False)
        nucleo._actualizar_perfil_conductual = Mock()
        nucleo.cerebro.procesar_texto_usuario = Mock(return_value=None)
        nucleo.cerebro.ctx.registrar_pedido = Mock()
        nucleo._cancelar_idle_diferido = Mock()
        nucleo._chequear_correccion_cache = Mock()

        def cerrar_pendiente(_texto):
            eventos.append("pendiente_bg")
            return False

        nucleo._chequear_pendiente_bg = cerrar_pendiente
        nucleo._chequear_pendiente_rapida = Mock(
            side_effect=lambda _texto: eventos.append("pendiente_rapida"))
        nucleo._respuesta_casual_rapida = Mock(
            side_effect=lambda _texto: (eventos.append("casual") or "De nada."))
        nucleo.speak = Mock()
        nucleo._temas_turno = Mock(return_value=None)
        _neutralizar_compuertas_tv(nucleo)
        nucleo.esp_comunicacion.hay_aviso_pendiente.return_value = False
        nucleo._manejar_diagnostico_terminal = Mock(return_value=False)
        nucleo.cache_patrones = Mock()
        nucleo.cache_patrones.buscar.return_value = None
        nucleo.esp_conversacion = Mock()
        nucleo.esp_conversacion.procesar_turno.return_value = "respuesta normal"
        nucleo._registrar_menciones_apps = Mock()

        with patch("nucleo.dark_nucleo.USAR_INTERPRETACION", False), \
                patch("nucleo.dark_nucleo.presupuesto.turno_activo", return_value=True):
            resultado = nucleo.handle_command("gracias")

        self.assertTrue(resultado)
        self.assertEqual(eventos, ["pendiente_bg", "pendiente_rapida", "casual"])
        nucleo.speak.assert_called_once_with("De nada.")
        nucleo.esp_conversacion.procesar_turno.assert_not_called()

    def test_web_sintetiza_las_tres_fuentes_y_conecta_investigacion(self):
        resultados = [
            {"title": f"Fuente {i}", "body": f"Fragmento {i}",
             "href": f"https://ejemplo.test/{i}"}
            for i in range(1, 5)
        ]
        respuesta_http = Mock(status_code=200)
        respuesta_http.json.return_value = {
            "message": {"content": "Einstein desarrolló la teoría de la relatividad."}
        }
        e = self._crear_ejecutor_de_prueba()
        e._buscar_resultados_web = Mock(return_value=resultados)
        e._investigar_interno = Mock(return_value="Texto de páginas consultadas")
        e._http.post.return_value = respuesta_http
        e._llm_provider = crear_proveedor_chat(session=e._http)
        e._preparar_modelo_de_trabajo = Mock(return_value=True)

        with patch("webbrowser.open"):
            resumen = e.investigar("biografía de Einstein")

        # K.3.1: la síntesis ya no es toda la respuesta. Detrás van citadas las
        # tres fuentes usadas, con su URL, y el navegador sigue sin abrirse.
        self.assertTrue(
            resumen.startswith("Einstein desarrolló la teoría de la relatividad."))
        self.assertIn("Fuentes:", resumen)
        for fuente in resultados[:3]:
            self.assertIn(fuente["href"], resumen)
        self.assertNotIn(resultados[3]["href"], resumen)
        e._investigar_interno.assert_called_once_with(
            "biografía de Einstein", num_fuentes=3, resultados=resultados[:3])
        prompt = e._http.post.call_args.kwargs["json"]["messages"][1]["content"]
        for fuente in resultados[:3]:
            self.assertIn(fuente["title"], prompt)
            self.assertIn(fuente["body"], prompt)
            self.assertIn(fuente["href"], prompt)
        self.assertNotIn(resultados[3]["href"], prompt)

    def test_web_usa_titulos_si_el_modelo_no_esta_disponible(self):
        resultados = [
            {"title": f"Título {i}", "body": "", "href": ""}
            for i in range(5)
        ]
        e = self._crear_ejecutor_de_prueba()
        e._buscar_resultados_web = Mock(return_value=resultados)
        e.investigar_a_fondo = Mock(return_value="")
        # El seam del modelo residente es la preparación: si no deja el modelo en
        # casa, la síntesis no se intenta y manda el resumen de títulos.
        e._preparar_modelo_de_trabajo = Mock(return_value=False)

        resumen = e.investigar("consulta")

        self.assertIn("Encontré 5 resultados", resumen)
        self.assertIn("Título 0", resumen)
        self.assertIn("Título 2", resumen)
        self.assertNotIn("Título 3", resumen)

    def test_plan_directo_web_biografica_reutiliza_ruta_del_documento(self):
        nucleo = object.__new__(DarkNucleo)

        with patch("builtins.print"):
            pasos = nucleo._plan_codigo_directo(
                "Crea un proyecto web tipo Wikipedia sobre la biografía de Albert Einstein"
            )

        self.assertEqual(
            [paso["tool"] for paso in pasos],
            ["escribir_documento", "escribir_codigo"],
        )
        self.assertEqual(pasos[0]["args"]["nombre_archivo"], "contenido")
        self.assertEqual(
            Path(pasos[1]["args"]["contenido_md"]).name,
            "contenido.md",
        )

    def test_tarea_web_investiga_y_pasa_el_documento_al_especialista_codigo(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            carpeta = Path(temporal)
            tareas = EspecialistaTareas(helpers={})
            tareas._investigar_a_fondo = Mock(
                return_value="Einstein nació en Ulm y formuló la relatividad especial.")
            tareas._generar_outline = Mock(return_value=["Biografía"])
            tareas._generar_seccion = Mock(return_value=(
                True, "Einstein nació en Ulm y formuló la relatividad especial."))

            codigo = EspecialistaCodigo()
            codigo._planificar_proyecto = Mock(return_value={
                "nombre_proyecto": "einstein_web",
                "archivos": [{
                    "path": "index.html",
                    "lenguaje": "html",
                    "descripcion": "Página biográfica",
                    "secciones": [{
                        "id": "principal",
                        "descripcion": "Contenido biográfico",
                        "md_heading": "Encabezado no producido por el planner",
                    }],
                }],
            })
            prompts_codigo = []

            def generar_html(prompt, _sistema, _lenguaje, max_tokens=4000):
                prompts_codigo.append(prompt)
                self.assertEqual(max_tokens, 4000)
                return True, "<main>Contenido de Einstein</main>"

            codigo._llamar_online = generar_html
            codigo._liberar_coder = Mock()

            nucleo = self._crear_nucleo_de_prueba(tareas=tareas, codigo=codigo)
            nucleo._pasos_originales = {}
            # Evita que el normalizador de producción convierta un segmento
            # de la ruta temporal llamado "Desktop" en el destino del usuario.
            nucleo._normalizar_arg_ruta = lambda ruta: ruta
            nucleo._pendiente_bg_lock = threading.Lock()
            nucleo._pendiente_bg = None
            nucleo.speak = Mock()
            nucleo._crear_tarea = Mock(return_value="tarea-integracion")
            intencion = SimpleNamespace(
                id="intencion-web",
                params_planos=lambda: {
                    "tarea": "Haz una web sobre la biografía de Einstein",
                    "nombre_archivo": "einstein",
                    "extension": "html",
                    "ruta_destino": str(carpeta),
                    "pipeline": True,
                    "tipo_doc": "biografía",
                },
            )

            nucleo._despachar_escribir_codigo(intencion)
            pasos = nucleo._pasos_originales["tarea-integracion"]
            self.assertEqual(
                [paso["tool"] for paso in pasos],
                ["escribir_documento", "escribir_codigo"],
            )
            self.assertIs(nucleo._registro_especialistas()["tareas"], tareas)
            self.assertIs(nucleo._registro_especialistas()["codigo"], codigo)

            with patch("builtins.print"):
                resultado_doc = nucleo._ejecutar_herramienta(
                    pasos[0]["tool"], pasos[0]["args"],
                    contexto={"tarea_id": "tarea-integracion", "paso_id": "paso-1"},
                )
            self.assertTrue(resultado_doc.ok, resultado_doc.mensaje)
            ruta_md = Path(pasos[1]["args"]["contenido_md"])
            self.assertTrue(ruta_md.is_file())

            with patch("builtins.print"):
                resultado_codigo = nucleo._ejecutar_herramienta(
                    pasos[1]["tool"], pasos[1]["args"],
                    contexto={"tarea_id": "tarea-integracion", "paso_id": "paso-2"},
                )
            self.assertTrue(resultado_codigo.ok, resultado_codigo.mensaje)
            self.assertIn("Einstein nació en Ulm", prompts_codigo[0])
            tareas._investigar_a_fondo.assert_called_once()
            self.assertTrue((carpeta / "einstein" / "einstein_web" / "index.html").is_file())


class _GateQueNotifica:
    """Doble con la forma del gate real: `desbloquear()` concede y notifica,
    que es lo único que entera al núcleo de una concesión."""

    def __init__(self, on_granted):
        self.acceso_concedido = threading.Event()
        self._on_granted = on_granted

    def desbloquear(self):
        self.acceso_concedido.set()
        self._on_granted("contraseña")


class PruebasAccesoPorContrasena(unittest.TestCase):
    """El unlock por contraseña con el gate facial vivo tiene que activar la
    sesión: el Event `_acceso_concedido` del núcleo solo lo setea on_granted, y
    `run_assistant` espera los dos Events antes de encender la voz."""

    TOKEN = "token-del-proceso"

    def _nucleo_bloqueado(self):
        nucleo = object.__new__(DarkNucleo)
        nucleo._lock_unlock_token = self.TOKEN
        nucleo._credencial_acceso_lista = threading.Event()
        nucleo._acceso_concedido = threading.Event()
        nucleo._modo_bloqueado = True
        nucleo._modo_limitado_sin_voz = False
        nucleo._cambio_contrasena_pendiente = False
        nucleo.overlay = Mock()
        nucleo._arrancar_gestos = Mock()
        nucleo._iniciar_voz_wyoming = Mock()
        nucleo._emitir_bienvenida_acceso = Mock()
        nucleo._programar_retomar_tareas = Mock()
        nucleo._acceso = FachadaAcceso()
        nucleo._acceso.registrar(al_conceder=nucleo._al_conceder_acceso)
        nucleo._acceso.gate = _GateQueNotifica(nucleo._acceso._notificar_concesion)
        return nucleo

    def _unlock(self, nucleo, token=None):
        nucleo._encolar_texto_manual(json.dumps({
            "action": "access_password_unlock",
            "token": self.TOKEN if token is None else token,
        }))

    def test_la_contrasena_correcta_abre_la_sesion(self):
        nucleo = self._nucleo_bloqueado()
        with redirect_stdout(io.StringIO()):
            self._unlock(nucleo)

        self.assertTrue(nucleo._acceso_concedido.is_set(),
                        "el núcleo no se enteró de la concesión")
        self.assertTrue(nucleo._credencial_acceso_lista.is_set())
        self.assertFalse(nucleo._modo_bloqueado, "la sesión no se activó")
        nucleo.overlay.set.assert_called_once_with("idle")
        nucleo._arrancar_gestos.assert_called_once()

    def test_un_token_distinto_no_abre_nada(self):
        nucleo = self._nucleo_bloqueado()
        with redirect_stdout(io.StringIO()):
            self._unlock(nucleo, token="otro-token")

        self.assertFalse(nucleo._acceso_concedido.is_set())
        self.assertTrue(nucleo._modo_bloqueado)
        nucleo.overlay.set.assert_not_called()

    def test_el_segundo_intento_no_abre_y_lo_dice(self):
        nucleo = self._nucleo_bloqueado()
        with redirect_stdout(io.StringIO()):
            self._unlock(nucleo)
        nucleo._modo_bloqueado = True  # re-bloqueo por ausencia
        nucleo.overlay.set_error_contrasena.reset_mock()
        with redirect_stdout(io.StringIO()):
            self._unlock(nucleo)

        self.assertTrue(nucleo._modo_bloqueado,
                        "la política de un solo uso no se aplicó")
        nucleo.overlay.set_error_contrasena.assert_called_once()
        aviso = nucleo.overlay.set_error_contrasena.call_args[0][0]
        self.assertIn("ya abrió", aviso)



class _HiloInmediato:
    """`threading.Thread` que corre al arrancar: la prueba ve el resultado ya."""

    def __init__(self, target=None, name=None, daemon=None, **_):
        self._target = target

    def start(self):
        self._target()


class PruebaPlanAntesDelCoder(unittest.TestCase):
    """Una app pasa por el planificador de Tareas antes de llegar al coder."""

    def nucleo(self, tareas=None):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.esp_tareas = tareas or Mock(pide_app=Mock(return_value=True))
        nucleo.speak = Mock()
        nucleo.overlay = Mock()
        nucleo.cerebro = Mock()
        nucleo.cerebro.responder.return_value = "Estoy con usted en la planificación."
        nucleo._decir_filler = Mock()
        nucleo._plan_lock = threading.Lock()
        nucleo._command_lock = threading.Lock()
        nucleo._pasos_originales = {}
        nucleo._pendiente_bg_lock = threading.Lock()
        nucleo._pendiente_bg = None
        nucleo._normalizar_arg_ruta = lambda ruta: ruta
        nucleo._crear_tarea = Mock(return_value="tarea-plan")
        return nucleo

    def worker(self, resultado):
        nucleo = self.nucleo()
        tarea = {
            "descripcion": "Construye «App de gastos».",
            "task_manager_id": "tarea-plan",
            "intencion_id": "i-1",
            "pasos": [{
                "id": "paso-1", "tool": "escribir_codigo",
                "args": {"tarea": "Construye «App de gastos».",
                         "contenido_md": "C:/planes/gastos.md"},
            }],
        }
        nucleo._tareas_bg = Mock()
        nucleo._tareas_bg.get.side_effect = [tarea, RuntimeError("fin del worker")]
        nucleo._tarea_bg_activa = None
        nucleo._tarea_bg_cancel = threading.Event()
        nucleo._iniciar_tarea = Mock()
        nucleo._ejecutar_paso_con_reintentos = Mock(return_value=resultado)
        nucleo._pausar_tarea_por_fallo = Mock()
        nucleo._completar_tarea = Mock(return_value=True)
        nucleo._cliente_manager = Mock()
        nucleo.intencion = Mock()
        nucleo._avisos_pendientes = queue.Queue()
        return nucleo

    def test_el_foco_se_valida_y_se_comparte_con_el_bridge_y_el_cerebro(self):
        nucleo = self.nucleo()
        self.assertTrue(nucleo._establecer_especialista_enfocado("tareas"))
        self.assertEqual(nucleo.especialista_enfocado, "tareas")
        nucleo.overlay.set_especialista_enfocado.assert_called_once_with("tareas")
        nucleo.cerebro.enfocar_especialista.assert_called_once_with("tareas")
        nucleo.cerebro.responder.assert_called_once_with("especialista_entrada_foco")
        nucleo.speak.assert_called_once_with("Estoy con usted en la planificación.")
        self.assertFalse(nucleo._establecer_especialista_enfocado("inventado"))
        self.assertEqual(nucleo.especialista_enfocado, "tareas")

    def test_quitar_el_foco_no_anuncia_otra_entrada(self):
        nucleo = self.nucleo()
        nucleo.especialista_enfocado = "tareas"
        self.assertTrue(nucleo._establecer_especialista_enfocado(None))
        nucleo.cerebro.enfocar_especialista.assert_called_once_with(None)
        nucleo.cerebro.responder.assert_not_called()

    def test_respaldo_proactivo_de_tareas_usa_el_banco_formal_aunque_no_haya_foco(self):
        nucleo = self.nucleo()
        nucleo._frase_tareas_hueco("datos")
        nucleo.cerebro.responder.assert_called_once_with("tareas_hueco", decision="datos")

    @staticmethod
    def intencion(tarea):
        return SimpleNamespace(id="i-1", params_planos=lambda: {
            "tarea": tarea, "nombre_archivo": "index", "extension": "html",
            "ruta_destino": tempfile.gettempdir()})

    def test_una_app_sin_plan_va_al_planificador_rapido(self):
        nucleo = self.nucleo()
        nucleo._planificar_en_fondo = Mock()
        msg = nucleo._despachar_escribir_codigo(self.intencion("hazme una app de gastos"))
        self.assertEqual(msg, "")
        nucleo._planificar_en_fondo.assert_called_once_with(
            nucleo.esp_tareas.iniciar_planificacion, "hazme una app de gastos", "rapido")
        nucleo._crear_tarea.assert_not_called()

    def test_un_plan_aprobado_ya_no_vuelve_a_planificarse(self):
        nucleo = self.nucleo()
        msg = nucleo._despachar_escribir_codigo(
            self.intencion("Construye «App de gastos»."), planificado=True)
        self.assertIs(msg, DarkNucleo._INTENCION_EN_BG)
        self.assertEqual(nucleo._pasos_originales["tarea-plan"][0]["tool"], "escribir_codigo")

    def test_un_script_suelto_no_pasa_por_el_plan(self):
        nucleo = self.nucleo(tareas=EspecialistaTareas(
            chat_provider=Mock(), cliente_manager=Mock(), helpers={}))
        msg = nucleo._despachar_escribir_codigo(
            self.intencion("hazme un script en python que renombre fotos"))
        self.assertIs(msg, DarkNucleo._INTENCION_EN_BG)

    def test_el_paso_del_plan_corre_aparte_dice_y_traspasa(self):
        nucleo = self.nucleo()
        nucleo._traspasar_al_coder = Mock()
        paso = Mock(return_value={"decir": "¿Lo construyo?", "traspaso": {"tarea": "x"}})
        with patch("nucleo.dark_nucleo.threading.Thread", _HiloInmediato):
            nucleo._planificar_en_fondo(paso, "sí")
        paso.assert_called_once_with("sí")
        nucleo.speak.assert_called_once_with("¿Lo construyo?")
        nucleo._traspasar_al_coder.assert_called_once_with({"tarea": "x"})
        self.assertFalse(nucleo._plan_lock.locked(), "el candado se suelta al terminar")

    def test_mientras_piensa_no_se_cruzan_dos_pasos(self):
        nucleo = self.nucleo()
        nucleo._plan_lock.acquire()
        paso = Mock()
        nucleo._planificar_en_fondo(paso, "otra cosa")
        paso.assert_not_called()
        self.assertIn("Sigo pensando", nucleo.speak.call_args.args[0])

    def test_si_el_planificador_falla_se_dice_y_se_suelta(self):
        nucleo = self.nucleo()
        with patch("nucleo.dark_nucleo.threading.Thread", _HiloInmediato),                 patch("builtins.print"):
            nucleo._planificar_en_fondo(Mock(side_effect=RuntimeError("sin red")))
        self.assertIn("No pude seguir con el plan", nucleo.speak.call_args.args[0])
        self.assertFalse(nucleo._plan_lock.locked())

    def test_la_especificacion_aprobada_viaja_hasta_el_coder(self):
        nucleo = self.nucleo()
        nucleo.intencion = Mock()
        nucleo._despachar_escribir_codigo = Mock(return_value=None)
        nucleo._traspasar_al_coder({"tarea": "Construye «Cumbre».", "especificacion": "C:/planes/cumbre.md"})
        params = nucleo.intencion.intencion_desde_cache.call_args.args[2]
        self.assertEqual(params["contenido_md"], "C:/planes/cumbre.md")


    def test_el_paso_de_escribir_codigo_lleva_la_especificacion(self):
        nucleo = self.nucleo()
        intencion = SimpleNamespace(id="i-2", params_planos=lambda: {
            "tarea": "Construye «Cumbre».", "nombre_archivo": "cumbre", "extension": "html",
            "ruta_destino": tempfile.gettempdir(), "contenido_md": "C:/planes/cumbre.md"})
        nucleo._despachar_escribir_codigo(intencion, planificado=True)
        args = nucleo._pasos_originales["tarea-plan"][0]["args"]
        self.assertEqual(args["contenido_md"], "C:/planes/cumbre.md")

    def test_el_traspaso_entra_por_la_puerta_de_escribir_codigo(self):
        nucleo = self.nucleo()
        nucleo.intencion = Mock()
        nucleo._despachar_escribir_codigo = Mock(return_value=DarkNucleo._INTENCION_EN_BG)
        nucleo._armar_ventana_bg = Mock()
        nucleo._traspasar_al_coder({"tarea": "Construye «Gastos».", "nombre_archivo": "gastos",
                                    "extension": "html"})
        accion, params = nucleo.intencion.intencion_desde_cache.call_args.args[1:]
        self.assertEqual(accion, "escribir_codigo")
        self.assertEqual(params["nombre_archivo"], "gastos")
        self.assertTrue(nucleo._despachar_escribir_codigo.call_args.kwargs["planificado"])
        self.assertNotIn("contenido_md", params, "sin especificación no se inventa una")
        nucleo._armar_ventana_bg.assert_called_once()
        self.assertFalse(nucleo._command_lock.locked())

    def test_el_worker_reabre_tareas_cuando_el_coder_echa_en_falta_campos(self):
        errores = ["falta «titulo»", "«secciones» debe ser una lista de 1 a 8 pantallas"]
        resultado = PasoResultado(
            ok=False, estado="fallo", tool="escribir_codigo", paso_id="paso-1",
            mensaje="No pude componer la app.", error="; ".join(errores),
            tipo_error="interno", reintentable=False,
            datos={"etapa": "composicion", "errores": errores,
                   "especificacion": "C:/planes/gastos.md"},
        )
        nucleo = self.worker(resultado)
        nucleo.esp_tareas.reabrir_por_error.return_value = {
            "decir": "El coder señaló campos faltantes. Ya preparé el plan."}

        with redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "fin del worker"):
            nucleo._worker_tareas_bg()

        llamada = nucleo.esp_tareas.reabrir_por_error.call_args
        self.assertEqual(llamada.args, ("C:/planes/gastos.md", errores))
        self.assertEqual(llamada.kwargs["pedido"], "Construye «App de gastos».")
        self.assertTrue(callable(llamada.kwargs.get("al_cerrar")))
        nucleo._pausar_tarea_por_fallo.assert_not_called()
        nucleo._cliente_manager.pausar.assert_called_once_with("tarea-plan")
        nucleo.intencion.marcar_fallida.assert_not_called()
        nucleo._completar_tarea.assert_not_called()
        self.assertEqual(nucleo._avisos_pendientes.get_nowait(),
                         "El coder señaló campos faltantes. Ya preparé el plan.")
        self.assertIsNone(nucleo._tarea_bg_activa)

    def test_al_cerrar_la_recuperacion_se_cierra_la_tarea_y_la_intencion(self):
        errores = ["«secciones» debe ser una lista de 1 a 8 pantallas"]
        for aprobado in (False, True):
            with self.subTest(aprobado=aprobado):
                resultado = PasoResultado(
                    ok=False, estado="fallo", tool="escribir_codigo", paso_id="paso-1",
                    mensaje="No pude componer la app.", error=errores[0],
                    tipo_error="interno", reintentable=False,
                    datos={"etapa": "composicion", "errores": errores,
                           "especificacion": "C:/planes/gastos.md"},
                )
                nucleo = self.worker(resultado)
                nucleo._pasos_originales["tarea-plan"] = [{"tool": "escribir_codigo"}]
                nucleo.esp_tareas.reabrir_por_error.return_value = {
                    "decir": "El coder señaló campos faltantes. Ya preparé el plan."}

                with redirect_stdout(io.StringIO()), \
                        self.assertRaisesRegex(RuntimeError, "fin del worker"):
                    nucleo._worker_tareas_bg()

                cerrar = nucleo.esp_tareas.reabrir_por_error.call_args.kwargs["al_cerrar"]
                cerrar(aprobado)

                nucleo._cliente_manager.cancelar.assert_called_once_with("tarea-plan")
                self.assertNotIn("tarea-plan", nucleo._pasos_originales)
                if aprobado:
                    nucleo.intencion.marcar_obsoleta.assert_called_once_with("i-1")
                    nucleo.intencion.marcar_cancelada.assert_not_called()
                else:
                    nucleo.intencion.marcar_cancelada.assert_called_once_with("i-1")
                    nucleo.intencion.marcar_obsoleta.assert_not_called()

    def test_el_worker_no_reabre_tareas_por_un_fallo_de_json(self):
        errores = ["la respuesta no contiene un objeto JSON completo"]
        resultado = PasoResultado(
            ok=False, estado="fallo", tool="escribir_codigo", paso_id="paso-1",
            mensaje="No pude componer la app.", error=errores[0],
            tipo_error="interno", reintentable=False,
            datos={"etapa": "composicion", "errores": errores,
                   "especificacion": "C:/planes/gastos.md"},
        )
        nucleo = self.worker(resultado)
        nucleo.esp_tareas.reabrir_por_error.return_value = None

        with redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "fin del worker"):
            nucleo._worker_tareas_bg()

        nucleo.esp_tareas.reabrir_por_error.assert_called_once()
        nucleo._pausar_tarea_por_fallo.assert_called_once()
        nucleo.intencion.marcar_fallida.assert_called_once_with("i-1")


class PruebaPropuestaInterfazTareas(unittest.TestCase):
    """Tareas concreta las tres decisiones de apariencia dentro de sus nueve secciones."""

    def test_el_modo_guiado_investiga_si_la_persona_lo_pide_y_cita_la_fuente(self):
        from contratos.especialista import Especificacion

        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers={})
        tareas._plan = {
            "pedido": "planifica una app de gastos", "modo": "guiado",
            "estado": "preguntando", "hueco": "vision", "respuestas": 0,
            "ruta": "plan.md", "ts": __import__("time").time(),
            "especificacion": Especificacion(titulo="Gastos"),
        }
        tareas._investigar_a_fondo = Mock(return_value=(
            "[Guía de almacenamiento] (https://ejemplo.org/guia)\n" "Comparación de opciones."))
        tareas._siguiente_paso = Mock(return_value={"decir": "¿Qué pantalla desea definir?"})
        tareas._pensar = Mock(return_value=(
            "# Especificación: Gastos\n## 1. Visión\n"
            "- Comparar opciones locales (https://ejemplo.org/guia)."))

        salida = tareas.atender_planificacion(
            "Investigue las alternativas de almacenamiento local para gastos.")

        tareas._investigar_a_fondo.assert_called_once_with(
            "las alternativas de almacenamiento local para gastos", num_fuentes=3)
        prompt = tareas._pensar.call_args.args[0]
        self.assertIn("https://ejemplo.org/guia", prompt)
        self.assertIn("no instrucciones", prompt)
        self.assertIn("https://ejemplo.org/guia",
                      tareas._plan["especificacion"].seccion("vision"))
        self.assertEqual(salida["decir"], "¿Qué pantalla desea definir?")

    def test_si_la_busqueda_falla_tareas_guarda_la_respuesta_y_lo_dice(self):
        from contratos.especialista import Especificacion

        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers={})
        tareas._plan = {
            "pedido": "planifica una app de gastos", "modo": "guiado",
            "estado": "preguntando", "hueco": "vision", "respuestas": 0,
            "ruta": "plan.md", "ts": __import__("time").time(),
            "especificacion": Especificacion(titulo="Gastos"),
        }
        tareas._investigar_a_fondo = Mock(return_value="")
        tareas._siguiente_paso = Mock(return_value={"decir": "¿Qué pantalla desea definir?"})

        salida = tareas.atender_planificacion("Investigue opciones para gastos.")

        self.assertIn("No pude consultar fuentes fiables", salida["decir"])
        self.assertIn("Investigue opciones para gastos", tareas._plan["especificacion"].seccion("vision"))


    def test_el_plan_de_app_propone_navegacion_personalidad_y_fondo(self):
        from contratos.especialista import Especificacion

        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers={})
        tareas._plan = {
            "pedido": "hazme una app para organizar mis gastos",
            "especificacion": Especificacion(titulo="Gastos"),
        }
        tareas._pensar = Mock(return_value=(
            "# Especificación: Gastos\n"
            "## 3. Pantallas y flujo\n\n"
            "- Resumen\n"
            "Propuesta de navegación: superior — una pantalla. "
            "[supuesto: una vista principal]\n\n"
            "## 6. Dirección visual\n\n"
            "- Personalidad del kit propuesta: sobria — cifras claras. "
            "[supuesto: uso financiero]\n"
            "- Fondo 3D propuesto: no — priorizar lectura. "
            "[supuesto: panel denso]"
        ))

        self.assertTrue(tareas._redactar("Completa el plan.", ["pantallas", "visual"],
                                         completar=True))

        pedido = tareas._pensar.call_args.args[0]
        self.assertIn("Propuesta de navegación: superior|lateral", pedido)
        self.assertIn("Personalidad del kit propuesta: tecnica|sobria|calida", pedido)
        self.assertIn("Fondo 3D propuesto: sí|no", pedido)
        self.assertIn("el coder puede corregirlas", pedido)
        especificacion = tareas._plan["especificacion"]
        self.assertIn("Propuesta de navegación", especificacion.seccion("pantallas"))
        resumen = tareas._resumen(especificacion)
        self.assertIn("1 pantallas: Resumen", resumen)
        self.assertNotIn("Propuesta de navegación", resumen)
        self.assertIn("Personalidad del kit propuesta", especificacion.seccion("visual"))
        self.assertIn("Fondo 3D propuesto", especificacion.seccion("visual"))

    def test_la_pregunta_proactiva_usa_solo_nube_y_filtra_con_guardia(self):
        from contratos.especialista import Especificacion

        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers={})
        tareas._plan = {
            "pedido": "organizar gastos de una pareja",
            "especificacion": Especificacion(
                titulo="Gastos", secciones={"vision": "Registrar compras y revisar el total."}),
            "respuestas": 1,
        }
        tareas._texto_online = Mock(return_value="¿Qué pantallas quieres incluir?")
        tareas._helpers["filtrar_voz"] = lambda texto: "¿Qué pantallas quiere incluir?"
        salida = tareas._pregunta_proactiva("pantallas")
        self.assertEqual(salida, "¿Qué pantallas quiere incluir?")
        sistema = tareas._texto_online.call_args.args[1]
        prompt = tareas._texto_online.call_args.args[0]
        self.assertIn("trato formal", sistema)
        self.assertIn("trade-off", sistema)
        self.assertIn("No invente datos", prompt)


class PruebaDecisionCuotaCoder(unittest.TestCase):
    """Las respuestas a la cuota se consumen sin llegar al router normal."""

    def nucleo(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._cuota_coder_lock = threading.Lock()
        nucleo.speak = Mock()
        evento = threading.Event()
        nucleo._cuota_coder_pendiente = {"evento": evento, "decision": None}
        return nucleo, evento

    def test_local_despierta_al_worker_con_la_opcion_elegida(self):
        nucleo, evento = self.nucleo()
        self.assertTrue(nucleo._procesar_decision_cuota_coder("seguir con modelo local"))
        self.assertTrue(evento.is_set())
        self.assertEqual(nucleo._cuota_coder_pendiente["decision"], "modelo_local")

    def test_esperar_seguir_con_el_reset_del_proveedor(self):
        nucleo, evento = self.nucleo()
        self.assertTrue(nucleo._procesar_decision_cuota_coder("esperar al reinicio"))
        self.assertTrue(evento.is_set())
        self.assertEqual(nucleo._cuota_coder_pendiente["decision"], "esperar_reinicio")

    def test_pago_no_se_ofrece_sin_tarifa_y_no_resuelve_la_pausa(self):
        nucleo, evento = self.nucleo()
        self.assertTrue(nucleo._procesar_decision_cuota_coder("usar clave de pago"))
        self.assertFalse(evento.is_set())
        self.assertIsNone(nucleo._cuota_coder_pendiente["decision"])
        self.assertIn("tarifa declarada", nucleo.speak.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
