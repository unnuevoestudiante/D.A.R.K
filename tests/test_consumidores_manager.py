"""R4 Fase C1: los tres consumidores pequeños del Manager, contra el puerto.

La Fase B escribió el cliente; la **C1 movió a los tres consumidores que cabían sin
tocar el núcleo**: `model_broker` (1 sitio), `especialista_codigo` (2) y
`especialista_tareas` (11). La **C2** se llevó después los 19 sitios vivos del núcleo,
así que los tres de arriba siguen siendo los consumidores pequeños y el inventario
completo lo vigila `tests/test_contrato_manager.py`.

Este archivo no prueba transporte (eso ya está en `tests/test_cliente_manager.py`):
prueba **política**, que es lo que la migración tenía que conservar sito por sito:

  * **La mentira del broker, cerrada por decisión del usuario.** `asegurar` devolvía
    `True` con un HTTP 400 **diciendo que el Manager lo había aprobado**. Lo que se corta
    ahora es la afirmación: con un rechazo explícito (`RAM_INSUFFICIENT` /
    `PRESUPUESTO_EXCEDIDO`) devuelve `False`; con un error ambiguo —el `HTTP 400 sin
    estado` que esta caja contesta de verdad, un 500 o silencio— devuelve `True` y lo
    dice en la consola y en la traza (`manager_no_goberno_carga`), porque quien carga el
    modelo es Ollama. Es la tabla de `TestElBrokerDejaDeMentir`.
  * **El reintento del código:** solo el 400, una vez, con 5 s y `timeout=15` propios.
  * **El `timeout=5` del especialista de tareas** para `/complete`, que no sube al 10
    del núcleo porque él nunca reintentó.
  * **El cableado:** una sola instancia del cliente, compuesta por el Núcleo y pasada al
    broker y a los dos especialistas —tres consumidores, una sesión.

Nada sale a la red: los tres consumidores reciben un doble que implementa los 16
métodos del puerto y apunta cada llamada.

Ref: dark_python/herramientas/internas/model_broker.py,
especialistas/{especialista_codigo,especialista_tareas,fabrica}.py, nucleo/dark_nucleo.py.
"""
import contextlib
import io
import pathlib
import sys
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.manager import (  # noqa: E402
    CARGA_RECHAZADA,
    EstadoRecursos,
    PuertoClienteManager,
    ResultadoCarga,
    Tarea,
    es_terminada,
)
from especialistas import fabrica  # noqa: E402
from herramientas.internas.model_broker import broker  # noqa: E402

NUCLEO_REL = "nucleo/dark_nucleo.py"


def _fuente(rel):
    return (DARK_PYTHON / rel).read_text(encoding="utf-8")


def _carga(codigo, estado=None):
    """El `ResultadoCarga` que el cliente habría construido con esa respuesta."""
    datos = {"status": estado} if estado else None
    return ResultadoCarga.desde_respuesta(codigo, datos,
                                          estado or f"http {codigo}")


class ClienteFalso:
    """Doble de `PuertoClienteManager`: apunta cada llamada y devuelve lo programado.
    `cargas` es la cola de resultados de `/load`; si se agota, repite el último."""

    def __init__(self, cargas=(), tareas=(), estado=None, vivo=True):
        self.llamadas = []
        self._cargas = list(cargas) or [ResultadoCarga(aceptado=False,
                                                      detalle="cola vacia")]
        self._tareas = tuple(tareas)
        self._estado = estado if estado is not None else EstadoRecursos()
        self._vivo = vivo

    def _reg(self, nombre, *a, **k):
        self.llamadas.append((nombre, a, k))

    @property
    def nombres(self):
        return [n for n, _a, _k in self.llamadas]

    def _una(self, nombre):
        encontradas = [l for l in self.llamadas if l[0] == nombre]
        if len(encontradas) != 1:
            raise AssertionError(f"{nombre} se llamó {len(encontradas)} veces: "
                                 f"{self.nombres}")
        return encontradas[0]

    # Manager (5050)

    def estado(self, timeout=None):
        self._reg("estado", timeout=timeout)
        return self._estado

    def esta_vivo(self, timeout=1.0):
        self._reg("esta_vivo", timeout=timeout)
        return self._vivo

    def cargar_modelo(self, modelo, timeout=None):
        self._reg("cargar_modelo", modelo, timeout=timeout)
        if len(self._cargas) > 1:
            return self._cargas.pop(0)
        return self._cargas[0]

    def descargar_modelo(self, modelo, timeout=None):
        self._reg("descargar_modelo", modelo, timeout=timeout)
        return True

    # Task Manager (5051)

    def listar(self, timeout=None):
        self._reg("listar", timeout=timeout)
        return self._tareas

    def interrumpidas(self, timeout=None):
        self._reg("interrumpidas", timeout=timeout)
        return self._tareas

    def crear(self, descripcion, *, prioridad=2, modulo=0, pasos=(), timeout=None):
        self._reg("crear", descripcion, prioridad=prioridad, modulo=modulo,
                  pasos=pasos, timeout=timeout)
        return "tarea-1"

    def iniciar(self, tarea_id, timeout=None):
        self._reg("iniciar", tarea_id, timeout=timeout)
        return True

    def completar_paso(self, tarea_id, paso_id, resultado=None, *, timeout=None):
        self._reg("completar_paso", tarea_id, paso_id, resultado, timeout=timeout)
        return True

    def fallar_paso(self, tarea_id, paso_id, error, *, timeout=None):
        self._reg("fallar_paso", tarea_id, paso_id, error, timeout=timeout)
        return True

    def completar(self, tarea_id, resultado, *, timeout=None):
        self._reg("completar", tarea_id, resultado, timeout=timeout)
        return True

    def cancelar(self, tarea_id, timeout=None):
        self._reg("cancelar", tarea_id, timeout=timeout)
        return True

    def pausar(self, tarea_id, timeout=None):
        self._reg("pausar", tarea_id, timeout=timeout)
        return True

    def reanudar(self, tarea_id, timeout=None):
        self._reg("reanudar", tarea_id, timeout=timeout)
        return self._tareas[0] if self._tareas else None

    def eliminar(self, tarea_id, timeout=None):
        self._reg("eliminar", tarea_id, timeout=timeout)
        return True

    def cerrar(self):
        self._reg("cerrar")


class TrazaFalsa:
    def __init__(self):
        self.marcas = []
        self.metadatos = {}

    def mark(self, nombre):
        self.marcas.append(nombre)

    def set_metadata(self, **campos):
        self.metadatos.update(campos)


class RuntimeFalso:
    """El proveedor LLM por la parte que mira el broker: qué tiene Ollama cargado."""

    def __init__(self, cargados=()):
        self._cargados = list(cargados)
        self.consultas = 0

    def loaded_models(self, timeout=2):
        self.consultas += 1
        return list(self._cargados)


def _silencioso(llamable, *a, **k):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        resultado = llamable(*a, **k)
    return resultado, salida.getvalue()


TAREA_UNA = Tarea(id="t1", descripcion="hacer algo", estado="Pendiente",
                  prioridad="Alta", modulo_asignado="Nucleo")
TAREA_DOS = Tarea(id="t2", descripcion="otra", estado="Ejecutándose",
                  pasos=(), prioridad="Baja")


class TestElDobleCumpleElPuerto(unittest.TestCase):
    """Si el doble se queda corto, los tests de abajo prueban una política que ningún
    cliente real puede tener: son los 16 métodos del puerto o no son nada."""

    def test_los_dieciseis_metodos_del_puerto(self):
        promesa = {n for n in dir(PuertoClienteManager) if not n.startswith("_")}
        self.assertEqual(len(promesa), 16)
        self.assertEqual({n for n in dir(ClienteFalso) if not n.startswith("_")
                          and callable(getattr(ClienteFalso, n, None))} -
                         {"nombres"}, promesa)


class TestElBrokerDejaDeMentir(unittest.TestCase):
    """La mentira que se cerró es **afirmar la aprobación del Manager**, no seguir el
    turno. Medido el 25-oct en caja: `/load` contesta `HTTP 400` **sin `status`** y a
    veces ni eso (read timeout), mientras Ollama tiene el modelo. Cortar ahí dejó el
    chat en "No tengo RAM" por un auxiliar que no sabe responder. Así que:

      * rechazo **explícito** (`status` en `CARGA_RECHAZADA`) → `False`;
      * cualquier otra respuesta de error, o ausencia de ella → `True`, pero diciendo y
        trazando que **el Manager no gobernó la carga** y que la resuelve Ollama."""

    def setUp(self):
        self._manager_antes = broker._manager
        self._runtime_antes = broker._runtime

    def tearDown(self):
        broker._manager = self._manager_antes
        broker._runtime = self._runtime_antes

    def _preparar(self, cliente, cargados=()):
        broker._manager = cliente
        broker._runtime = RuntimeFalso(cargados)
        return cliente

    def test_el_400_con_rechazo_explito_es_un_False(self):
        cliente = self._preparar(ClienteFalso([_carga(400, "RAM_INSUFFICIENT")]))
        valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
        self.assertIs(valor, False,
                      "el broker volvió a prometer un modelo que el Manager rechazó")
        self.assertIn("rechazó", impreso)
        self.assertEqual(cliente.nombres, ["cargar_modelo"])

    def test_el_400_sin_estado_medido_en_caja_no_es_un_no_hay_RAM(self):
        """`HTTP 400 sin estado` es lo que el Manager de esta caja contesta a `/load`.
        No es un rechazo de RAM: es el Manager sin gobernar la carga, y el turno sigue
        porque quien carga el modelo es Ollama."""
        self._preparar(ClienteFalso([_carga(400)]))
        valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
        self.assertIs(valor, True)
        self.assertIn("no gobierna", impreso)
        self.assertIn("HTTP 400", impreso)

    def test_un_500_tampoco_decide_por_el_motor(self):
        self._preparar(ClienteFalso([_carga(500)]))
        valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
        self.assertIs(valor, True)
        self.assertIn("HTTP 500", impreso)

    def test_sin_respuesta_sigue_dejando_pasar_el_turno(self):
        """Deliberado: si el Manager está apagado, Ollama carga solo al recibir el
        request. Lo que no se pierde es decirlo en la consola y en la traza."""
        cliente = self._preparar(ClienteFalso(
            [ResultadoCarga(aceptado=False, detalle="sin respuesta")]))
        traza = TrazaFalsa()
        valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct",
                                     30, traza)
        self.assertIs(valor, True)
        self.assertIn("sin respuesta", impreso)
        self.assertIn("la resuelve Ollama", impreso)
        self.assertIs(traza.metadatos.get("manager_no_goberno_carga"), True)
        self.assertEqual(cliente.nombres, ["cargar_modelo"])

    def test_el_cuerpo_del_error_sale_en_la_linea_para_poder_medirlo(self):
        """Un 400 sin `status` no dice nada: el detalle (los primeros 120 bytes que ya
        trae `ResultadoCarga`) es lo que permite saber qué está contestando el Manager."""
        self._preparar(ClienteFalso(
            [ResultadoCarga(aceptado=False, codigo_http=400,
                            detalle="Ollama no responde")]))
        valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
        self.assertIs(valor, True)
        self.assertIn("Ollama no responde", impreso)

    def test_un_200_con_status_de_rechazo_es_False(self):
        """`codigo_http=200` no basta: el Manager dice `RAM_INSUFFICIENT` con 200.
        La tabla de `aceptado` es del contrato, no del broker."""
        for estado in CARGA_RECHAZADA:
            with self.subTest(status=estado):
                self._preparar(ClienteFalso([_carga(200, estado)]))
                valor, _ = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
                self.assertIs(valor, False)

    def test_un_200_cargado_es_True(self):
        for estado in ("cargado", "ya_cargado"):
            with self.subTest(status=estado):
                self._preparar(ClienteFalso([_carga(200, estado)]))
                valor, impreso = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
                self.assertIs(valor, True)
                self.assertIn("listo", impreso)

    def test_si_Ollama_ya_lo_tiene_no_se_llama_al_Manager(self):
        cliente = self._preparar(ClienteFalso([_carga(200, "cargado")]),
                                 cargados=["qwen2.5:7b-instruct"])
        valor, _ = _silencioso(broker.asegurar, "qwen2.5:7b-instruct")
        self.assertIs(valor, True)
        self.assertEqual(cliente.llamadas, [],
                         "la residencia es la fuente de verdad: pedir `/load` otra vez "
                         "desincroniza al Manager")

    def test_el_suelo_de_timeout_sigue_sendo_30(self):
        """El timeout era 90 s y se bajó a 30; el `max` existe para que un llamador
        ansioso no vuelva a poner 5. El número lo recibe el cliente, no la tabla."""
        cliente = self._preparar(ClienteFalso([_carga(200, "cargado")]))
        _silencioso(broker.asegurar, "qwen2.5:7b-instruct", 5)
        self.assertEqual(cliente._una("cargar_modelo")[2]["timeout"], 30)
        self._preparar(ClienteFalso([_carga(200, "cargado")]))
        cliente = broker._manager
        _silencioso(broker.asegurar, "qwen2.5:7b-instruct", 45)
        self.assertEqual(cliente._una("cargar_modelo")[2]["timeout"], 45)

    def test_la_traza_cuenta_el_HTTP_ya_decidido(self):
        self._preparar(ClienteFalso([_carga(400, "RAM_INSUFFICIENT")]))
        traza = TrazaFalsa()
        _silencioso(broker.asegurar, "qwen2.5:7b-instruct", 30, traza)
        self.assertIn("manager_load_start", traza.marcas)
        self.assertIn("manager_load_end", traza.marcas)
        self.assertEqual(traza.metadatos["manager_load_http_status"], 400)
        self.assertEqual(traza.metadatos["manager_load_status"], "RAM_INSUFFICIENT")
        self.assertNotIn("manager_http_error_continued", traza.metadatos,
                         "la clave de la mentira sigue viva: alguien la vuelve a leer")
        self.assertNotIn("manager_no_goberno_carga", traza.metadatos,
                         "un rechazo explícito sí gobierna la carga: no es un fallo del "
                         "auxiliar")

    def test_configurar_cliente_pide_el_puerto_no_el_diccionario(self):
        class SinCargar:
            def estado(self, timeout=None):
                return EstadoRecursos()

        with self.assertRaises(TypeError):
            broker.configurar_cliente(SinCargar())
        with self.assertRaises(TypeError):
            broker.configurar_cliente(None)
        cliente = ClienteFalso([_carga(200, "cargado")])
        broker.configurar_cliente(cliente)
        self.assertIs(broker._manager, cliente)


@contextlib.contextmanager
def _Ollama_sin_el_modelo():
    """`_asegurar_modelo` pregunta primero a Ollama (`broker.esta_cargado`) y solo
    después habla con el Manager. En esta caja el modelo puede estar residente de
    verdad, y entonces el test mediría el atajo en vez de la política del 400."""
    fake = mock.Mock(name="broker-sin-residencia")
    fake.esta_cargado.return_value = False
    with mock.patch("especialistas.especialista_codigo.broker", fake):
        yield fake


class TestLaPoliticaDelEspecialistaCodigo(unittest.TestCase):
    """El reintento del 400 es suyo, no del transporte: dos llamadas, 5 s entre ellas
    y `timeout=15` en cada una."""

    def _codigo(self, cliente, liberar_modelo=None):
        sin_uso = lambda *a, **k: None  # noqa: E731
        codigo = fabrica.crear_especialista_codigo(
            http_session=None, chat_provider=None, cliente_manager=cliente,
            llm_lock=None, liberar_whisper=sin_uso, recargar_whisper=sin_uso,
            preparar_modelo=sin_uso, liberar_modelo=liberar_modelo)
        self.assertIs(codigo._manager, cliente,
                      "el especialista volvió a construir su propio cliente")
        return codigo

    def test_el_400_se_reintenta_una_sola_vez(self):
        cliente = ClienteFalso([_carga(400), _carga(400)])
        codigo = self._codigo(cliente)
        with _Ollama_sin_el_modelo(), mock.patch(
                "especialistas.especialista_codigo.time.sleep") as duerme:
            salida, impreso = _silencioso(codigo._asegurar_modelo,
                                          "qwen2.5:7b-instruct")
        cargado, mensaje = salida
        self.assertIs(cargado, False)
        self.assertIn("(HTTP 400)", mensaje)
        self.assertEqual(cliente.nombres.count("cargar_modelo"), 2)
        duerme.assert_called_once_with(5)
        for _n, _a, k in cliente.llamadas:
            self.assertEqual(k["timeout"], 15,
                             "`_asegurar_modelo` perdió su timeout de 15 s: el de la "
                             "tabla son 30 y cambiarlo cambia el turno")

    def test_el_segundo_intento_aceptado_gana(self):
        cliente = ClienteFalso([_carga(400), _carga(200, "cargado")])
        codigo = self._codigo(cliente)
        with _Ollama_sin_el_modelo(), mock.patch(
                "especialistas.especialista_codigo.time.sleep"):
            salida, _ = _silencioso(codigo._asegurar_modelo, "qwen2.5:7b-instruct")
        self.assertEqual(salida, (True, None))

    def test_sin_respuesta_corta_en_la_primera(self):
        """Sin Manager no hay nada que reintentar en 5 segundos: el reintento era del
        400, no del silencio."""
        cliente = ClienteFalso([ResultadoCarga(aceptado=False, detalle="sin respuesta")])
        codigo = self._codigo(cliente)
        with _Ollama_sin_el_modelo(), mock.patch(
                "especialistas.especialista_codigo.time.sleep") as duerme:
            salida, impreso = _silencioso(codigo._asegurar_modelo,
                                          "qwen2.5:7b-instruct")
        self.assertIs(salida[0], False)
        self.assertIn("no está disponible", salida[1])
        self.assertIn("error cargando", impreso)
        self.assertEqual(cliente.nombres.count("cargar_modelo"), 1)
        duerme.assert_not_called()

    def test_un_500_no_se_reintenta(self):
        cliente = ClienteFalso([_carga(500)])
        codigo = self._codigo(cliente)
        with _Ollama_sin_el_modelo(), mock.patch(
                "especialistas.especialista_codigo.time.sleep") as duerme:
            salida, _ = _silencioso(codigo._asegurar_modelo, "qwen2.5:7b-instruct")
        self.assertIs(salida[0], False)
        self.assertEqual(cliente.nombres.count("cargar_modelo"), 1)
        duerme.assert_not_called()

    def test_si_Ollama_lo_tiene_no_se_molesta_al_Manager(self):
        """El atajo que el test de arriba apaga: si el modelo ya está residente, el
        especialista no habla con el Manager. Aquí sí se deja el broker de verdad."""
        cliente = ClienteFalso()
        codigo = self._codigo(cliente)
        with mock.patch("especialistas.especialista_codigo.broker") as brk:
            brk.esta_cargado.return_value = True
            salida, _ = _silencioso(codigo._asegurar_modelo, "qwen2.5:7b-instruct")
        self.assertEqual(salida, (True, None))
        self.assertEqual(cliente.llamadas, [])

    def test_descargar_va_por_el_puerto(self):
        cliente = ClienteFalso()
        codigo = self._codigo(cliente)
        self.assertIs(codigo._descargar_modelo("qwen2.5:7b-instruct"), True)
        llamada = cliente._una("descargar_modelo")
        self.assertEqual(llamada[1], ("qwen2.5:7b-instruct",))
        self.assertEqual(llamada[2]["timeout"], 15)

    def test_la_politica_de_RAM_del_nucleo_manda_sobre_el_puerto(self):
        """`liberar_modelo` es el callback del Núcleo: si existe, el especialista no
        habla con el Manager. Sigue siendo la política del que reserva la RAM."""
        Called = []
        cliente = ClienteFalso()
        codigo = self._codigo(cliente,
                              liberar_modelo=lambda m: Called.append(m) or True)
        self.assertIs(codigo._descargar_modelo("m"), True)
        self.assertEqual(Called, ["m"])
        self.assertEqual(cliente.llamadas, [])

    def test_los_dos_puertos_del_Manager_no_viven_en_los_migrados(self):
        """Un `5050` queda en dos prosas de docstring, y está bien: explican **dónde**
        vive ahora el HTTP. Lo que no puede volver es una URL —ni `http://`, ni
        `localhost`, ni la constante que la escribía—: desde la C1 estos tres módulos no
        saben qué puerto escucha el Manager."""
        for rel in ("especialistas/especialista_codigo.py",
                    "especialistas/especialista_tareas.py",
                    "herramientas/internas/model_broker.py"):
            fuente = _fuente(rel)
            for texto in ("http://", "localhost", "MANAGER_URL", "TASK_MANAGER_URL"):
                self.assertNotIn(texto, fuente, f"{rel} vuelve a escribir {texto}")


class TestLaBocaDelEspecialistaTareas(unittest.TestCase):
    """Once sitios migrados: el especialista deja de ser un HTTP y pasa a ser la boca
    del Task Manager. Aquí se fija qué método del puerto llama cada uno y con qué
    timeout, porque la C2 va a leer esta tabla para no perder números."""

    def _tareas(self, cliente, **kw):
        sin_uso = lambda *a, **k: None  # noqa: E731
        kwargs = dict(http_session=None, chat_provider=None,
                      cliente_manager=cliente, llm_lock=None,
                      preparar_modelo=sin_uso, helpers={})
        kwargs.update(kw)
        tareas = fabrica.crear_especialista_tareas(**kwargs)
        self.assertIs(tareas._manager, cliente)
        return tareas

    def test_el_CRSU_de_tareas_llama_al_puerto_justo(self):
        cliente = ClienteFalso(tareas=[TAREA_UNA])
        t = self._tareas(cliente)
        with contextlib.redirect_stdout(io.StringIO()):
            t.obtener_tareas()
            t.crear_tarea("algo", prioridad=1, modulo=2, pasos=[{"id": "p1"}])
            t.iniciar_tarea("t1")
            t.completar_paso("t1", "p1", "hecho")
            t.fallar_paso("t1", "p1", "roto")
            t.completar_tarea("t1", "listo")
            t.eliminar_tarea("t1")
            t.cancelar_tarea("t1")
            t.reanudar_tarea("t1")
            t.verificar_tareas_interrumpidas()
            t.obtener_estado_recursos()
        self.assertEqual(cliente.nombres, [
            "listar", "crear", "iniciar", "completar_paso", "fallar_paso", "completar",
            "eliminar", "cancelar", "reanudar", "interrumpidas", "estado"])

    def test_completar_tarea_no_sube_al_timeout_del_nucleo(self):
        """El `/complete` del núcleo usa 10 porque reintenta tres veces; este
        especialista nunca reintentó y se queda con el 5 propio de hoy."""
        cliente = ClienteFalso()
        t = self._tareas(cliente)
        t.completar_tarea("t1", "listo")
        self.assertEqual(cliente._una("completar")[2]["timeout"], 5)

    def test_los_demas_usan_el_default_de_la_tabla(self):
        """Ningún sitio de la C1 pasa `timeout=` salvo donde hoy había un número
        propio: `None` es "el de la tabla del cliente", no "sin límite"."""
        cliente = ClienteFalso(tareas=[TAREA_UNA])
        t = self._tareas(cliente)
        for nombre, metodo in (("listar", t.obtener_tareas),
                               ("iniciar", lambda: t.iniciar_tarea("t1")),
                               ("eliminar", lambda: t.eliminar_tarea("t1")),
                               ("cancelar", lambda: t.cancelar_tarea("t1")),
                               ("reanudar", lambda: t.reanudar_tarea("t1")),
                               ("interrumpidas", t.verificar_tareas_interrumpidas),
                               ("estado", t.obtener_estado_recursos)):
            with contextlib.redirect_stdout(io.StringIO()):
                metodo()
            with self.subTest(metodo=nombre):
                self.assertIsNone(cliente._una(nombre)[2]["timeout"])

    def test_obtener_tareas_devuelve_Tarea_no_el_dict_del_servidor(self):
        cliente = ClienteFalso(tareas=[TAREA_UNA, TAREA_DOS])
        t = self._tareas(cliente)
        salida = t.obtener_tareas()
        self.assertIsInstance(salida, tuple)
        self.assertTrue(all(isinstance(x, Tarea) for x in salida))
        self.assertEqual([x.id for x in salida], ["t1", "t2"])

    def test_la_puerta_del_especialista_sigue_siendo_la_del_contrato(self):
        """`contratos/especialista.py` promete `obtener_tareas()` al Núcleo. Si algún
        día devuelve el dict crudo otra vez, la C2 no lo va a poder filtrar con
        `es_terminada`."""
        cliente = ClienteFalso(tareas=[TAREA_UNA])
        t = self._tareas(cliente)
        self.assertEqual(t.obtener_tareas()[0].estado_canonico, "pendiente")

    def test_interrumpidas_devuelve_y_narra_el_progreso(self):
        """El defecto 2 es un problema del **núcleo** (tira el valor de vuelta), no de
        este especialista: aquí el resultado sí se devuelve y el progreso sí se pinta,
        con la forma de `Tarea`."""
        cliente = ClienteFalso(tareas=[Tarea(
            id="t9", descripcion="a medias", estado="Cancelada",
            pasos=())])
        t = self._tareas(cliente)
        salida, impreso = _silencioso(t.verificar_tareas_interrumpidas)
        self.assertEqual([x.id for x in salida], ["t9"])
        self.assertIn("1 tarea(s) interrumpida(s)", impreso)
        self.assertIn("progreso: 0/0", impreso)

    def test_estado_recursos_sale_del_puerto_como_Objeto(self):
        cliente = ClienteFalso(estado=EstadoRecursos(ram_disponible_mb=4889,
                                                     respondio=True))
        t = self._tareas(cliente)
        self.assertIsInstance(t.obtener_estado_recursos(), EstadoRecursos)

    def test_tool_estado_recursos_no_confunde_cero_con_silencio(self):
        """Sin `respondio`, un `EstadoRecursos()` vacío y un Manager que dice 0 MB
        eran el mismo dato para el poller del menú (`if datos:`)."""
        mudo = self._tareas(ClienteFalso(estado=EstadoRecursos()))
        texto, _ = _silencioso(mudo.tool_estado_recursos)
        self.assertIn("No pude consultar el estado", texto)
        vivo = self._tareas(ClienteFalso(estado=EstadoRecursos(
            ram_disponible_mb=0, respondio=True, cpu_uso_pct=15.1)))
        texto, _ = _silencioso(vivo.tool_estado_recursos)
        self.assertNotIn("No pude", texto)
        self.assertIn("RAM disponible: 0MB", texto)

    def test_tool_retomar_usa_el_vocabulario_canonico(self):
        """El filtro del metrónomo busca cuatro palabras en minúsculas; aquí se
        comparan contra `estado_canonico`, así que `Cancelada` deja de colarse por
        mayúscula y `Pendiente` se retoma aunque el servidor la escriba capitalizada."""
        cliente = ClienteFalso(tareas=[
            Tarea(id="a", descripcion="p", estado="Pendiente"),
            Tarea(id="b", descripcion="c", estado="Cancelada"),
            Tarea(id="c", descripcion="r", estado="Requiere Confirmación"),
        ])
        t = self._tareas(cliente)
        texto, _ = _silencioso(t.tool_retomar_tareas)
        self.assertIn("Retomando 1 tareas", texto)
        self.assertIn("1 tareas requieren confirmación", texto)
        self.assertEqual(cliente._una("iniciar")[1], ("a",),
                         "una tarea cancelada no se reinicia por ir en mayúsculas")

    def test_tool_estado_tareas_sigue_contando_Fallida_como_pendiente(self):
        """Decisión de la C1: este filtro son DOS palabras (`completada`, `cancelada`),
        no las tuplas del contrato. `Fallida` cuenta como pendiente para el usuario, y
        `ESTADOS_TERMINADAS` la excluiría: por eso aquí sale 2 y no 1."""
        cliente = ClienteFalso(tareas=[
            Tarea(id="a", descripcion="f", estado="Fallida"),
            Tarea(id="b", descripcion="c", estado="Completada"),
            Tarea(id="c", descripcion="e", estado="Ejecutándose"),
        ])
        t = self._tareas(cliente)
        texto, _ = _silencioso(t.tool_estado_tareas)
        self.assertIn("Tareas pendientes: 2", texto)
        self.assertIn("Tarea activa: e", texto)
        self.assertTrue(es_terminada("Fallida"),
                        "si `Fallida` deja de ser terminada, el comentario del "
                        "especialista miente y se puede usar la tupla")


class TestCableadoDeUnaSolaInstancia(unittest.TestCase):
    """El Núcleo compone el cliente y lo reparte: tres consumidores, una sesión. Si
    aparece un segundo `crear_cliente_manager`, el Manager vuelve a tener varios
    clientes TCP pidiendo el mismo presupuesto."""

    def test_el_nucleo_compone_un_solo_cliente(self):
        fuente = _fuente(NUCLEO_REL)
        self.assertIn("from proveedores.manager.fabrica import crear_cliente_manager",
                      fuente)
        self.assertEqual(fuente.count("crear_cliente_manager("), 1,
                         "el núcleo construye el cliente más de una vez: cada copia es "
                         "una sesión TCP nueva pidiendo el mismo presupuesto")
        self.assertIn("self._cliente_manager = crear_cliente_manager(session=self._http)",
                      fuente)

    def test_lo_reparte_entre_broker_y_los_dos_especialistas(self):
        fuente = _fuente(NUCLEO_REL)
        self.assertIn("broker.configurar_cliente(self._cliente_manager)", fuente)
        self.assertEqual(fuente.count("cliente_manager=self._cliente_manager"), 2,
                         "el mapa de repartir el cliente cambió: broker + código + "
                         "tareas")

    def test_la_fabrica_pide_el_cliente_como_capability(self):
        """`cliente_manager` es palabra clave **sin valor por defecto** en la fábrica:
        un especialista sin cliente es un error de cableado, no un cliente propio a
        escondidas (la regla de la casa: la fábrica decide, el módulo no adivina)."""
        import inspect
        for crear in (fabrica.crear_especialista_codigo,
                      fabrica.crear_especialista_tareas):
            with self.subTest(fabrica=crear.__name__):
                p = inspect.signature(crear).parameters["cliente_manager"]
                self.assertIs(p.kind, inspect.Parameter.KEYWORD_ONLY)
                self.assertIs(p.default, inspect.Parameter.empty)


if __name__ == "__main__":
    unittest.main()
