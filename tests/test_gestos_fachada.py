"""Fase A de la línea gestual: la capa contratos + fábrica + fachada.

Solo stdlib. El motor y el canal son dobles que registran qué les piden y en qué
orden: aquí se prueba la composición y el degradado, no MediaPipe. Las pruebas
que sí tocan el motor real van con `skipUnless` porque `herramientas/gestos.py`
tira de cv2, numpy y MediaPipe al importarse.

Ref: dark_python/gestos/{fabrica,fachada,config}.py, contratos/gestos.py.
"""
import ast
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.gestos import EstadosGestos, PuertoGestos  # noqa: E402
from gestos import FachadaGestos, config, fabrica  # noqa: E402
from gestos.fachada import enchufar_log  # noqa: E402


def _importaciones_de(texto):
    """Nombres punteados que un source importa, por AST (sin imports relativos)."""
    arbol = ast.parse(texto)
    nombres = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres += [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and not nodo.level:
            nombres.append(nodo.module)
            nombres += [f"{nodo.module}.{a.name}" for a in nodo.names]
    return nombres


def _importaciones(ruta):
    return _importaciones_de(pathlib.Path(ruta).read_text(encoding="utf-8"))


class MotorDoble:
    """Cumple `PuertoGestos` y registra lo que le hacen."""

    def __init__(self, estado="APAGADO", error_al_iniciar=None):
        self.estado = estado
        self.ultima_mano_t = 123.5
        self.on_evento = None
        self.sostiene = None
        self.video = None
        self.lectura = None
        self.agarre = None
        self.iniciar_llamadas = 0
        self._error_al_iniciar = error_al_iniciar

    def iniciar(self):
        self.iniciar_llamadas += 1
        if self._error_al_iniciar is not None:
            raise self._error_al_iniciar

    def detener(self, timeout=5.0):
        self.estado = "APAGADO"

    def fijar_sostiene(self, valor):
        self.sostiene = valor

    def fijar_video(self, valor):
        self.video = valor

    def fijar_lectura(self, valor):
        self.lectura = valor

    def fijar_agarre(self, ids):
        self.agarre = list(ids)


class CanalDoble:
    def __init__(self, error_al_iniciar=None, port=8768):
        self.motor_conectado = None
        self.iniciar_llamadas = 0
        self.detener_llamadas = 0
        self.clientes = 0
        self.port = port
        self._error_al_iniciar = error_al_iniciar

    def conectar_motor(self, motor):
        self.motor_conectado = motor

    def iniciar(self):
        self.iniciar_llamadas += 1
        if self._error_al_iniciar is not None:
            raise self._error_al_iniciar

    def detener(self, timeout=5.0):
        self.detener_llamadas += 1


def fachada_con(motor=None, canal=None, error_motor=None, error_canal=None):
    """Fachada con dobles inyectados y bitácora del orden de construcción."""
    bitacora = []

    def crear_motor(servicio, acceso=None, *, ver=False):
        bitacora.append(("crear_motor", servicio, acceso, ver))
        if error_motor is not None:
            raise error_motor
        return motor if motor is not None else MotorDoble()

    def crear_canal(**ajustes):
        bitacora.append(("crear_canal", ajustes))
        if error_canal is not None:
            raise error_canal
        return canal if canal is not None else CanalDoble()

    f = FachadaGestos("camara-falsa", acceso="event-falso",
                      crear_motor=crear_motor, crear_canal=crear_canal)
    return f, bitacora


def _loggers_de_gestos():
    """Los tres loggers a los que `enchufar_log` toca: los de las dos
    implementaciones —los nombra la fábrica, no este archivo— y el de la propia
    fachada, que es quien escribe el aviso de degradado."""
    nombres = (*fabrica.LOGGERS, FachadaGestos.__module__)
    return [logging.getLogger(nombre) for nombre in nombres]


# `iniciar()` enchufa el log, y el defecto de `GESTOS_LOG` es un `gestos.log`
# relativo. Sin redirigirlo, media suite dejaría ese fichero en el cwd del runner
# y handlers de fichero abiertos colgando de los loggers.
_DIR_LOG = tempfile.mkdtemp(prefix="dark-gestos-log-")
_RUTA_LOG_DE_MODULO = str(pathlib.Path(_DIR_LOG) / "gestos.log")
_PARCHE_LOG = None
_ESTADO_LOG = {}


def setUpModule():
    global _PARCHE_LOG, _ESTADO_LOG
    _PARCHE_LOG = patch.object(config, "LOG", _RUTA_LOG_DE_MODULO)
    _PARCHE_LOG.start()
    _ESTADO_LOG = {logger: logger.level for logger in _loggers_de_gestos()}


def tearDownModule():
    _PARCHE_LOG.stop()
    for logger, nivel in _ESTADO_LOG.items():
        for manejador in list(logger.handlers):
            if isinstance(manejador, logging.FileHandler):
                logger.removeHandler(manejador)
                manejador.close()
        logger.setLevel(nivel)
    shutil.rmtree(_DIR_LOG, ignore_errors=True)


class PruebaArranque(unittest.TestCase):
    def test_degrada_sin_lanzar(self):
        """Cualquier motivo, y D.A.R.K. sigue en marcha sin gestos."""
        for error in (ImportError("falta mediapipe"), OSError("sin camara"),
                      RuntimeError("puerto ocupado"), ValueError("host no local")):
            f, _ = fachada_con(error_motor=error)
            with self.subTest(error=type(error).__name__):
                self.assertFalse(f.iniciar())
                self.assertIs(f.error, error)
                self.assertFalse(f.activos)
                f.detener()

    def test_degrada_si_falla_el_canal(self):
        f, _ = fachada_con(error_canal=OSError("bind"))
        self.assertFalse(f.iniciar())
        self.assertFalse(f.activos)

    def test_el_canal_se_cierra_si_el_motor_no_arranca(self):
        """Rama de limpieza: el WebSocket ya estaba abierto cuando el motor falló."""
        motor, canal = MotorDoble(error_al_iniciar=RuntimeError("hilo muerto")), CanalDoble()
        f, _ = fachada_con(motor=motor, canal=canal)
        self.assertFalse(f.iniciar())
        self.assertEqual(motor.iniciar_llamadas, 1)
        self.assertEqual(canal.detener_llamadas, 1)
        self.assertIsNone(f.motor)
        self.assertIsNone(f.canal)

    def test_el_canal_no_se_cierra_si_el_motor_ni_se_construyo(self):
        canal = CanalDoble()
        f, _ = fachada_con(canal=canal, error_motor=ImportError("falta mediapipe"))
        self.assertFalse(f.iniciar())
        self.assertEqual(canal.detener_llamadas, 0)

    def test_idempotente_no_abre_dos_vetas(self):
        f, bitacora = fachada_con()
        self.assertTrue(f.iniciar())
        self.assertTrue(f.iniciar())
        self.assertEqual(sum(1 for e in bitacora if e[0] == "crear_canal"), 1)
        self.assertEqual(sum(1 for e in bitacora if e[0] == "crear_motor"), 1)

    def test_sin_arrancar_no_hay_nada(self):
        f, _ = fachada_con()
        self.assertFalse(f.activos)
        self.assertIsNone(f.estado)
        self.assertEqual(f.clientes, 0)
        self.assertEqual(f.ultima_mano_t, 0.0)
        f.detener()  # vive en atexit: no puede explosionar si no llegó a iniciar


class PruebaOrden(unittest.TestCase):
    def test_conectar_abrir_canal_y_arrancar_motor_en_ese_orden(self):
        orden = []
        motor, canal = MotorDoble(), CanalDoble()
        motor.iniciar = lambda: orden.append("motor.iniciar")
        canal.iniciar = lambda: orden.append("canal.iniciar")
        canal.conectar_motor = lambda m: orden.append("conectar")
        canal.detener = lambda timeout=5.0: None
        f, _ = fachada_con(motor=motor, canal=canal)
        f.iniciar()
        self.assertEqual(orden, ["conectar", "canal.iniciar", "motor.iniciar"])

    def test_el_motor_recibe_camara_y_evento_de_acceso(self):
        """La inyeccion que hace que el motor pida 0 fps con el acceso bloqueado."""
        f, bitacora = fachada_con()
        f.iniciar()
        self.assertEqual(bitacora[0],
                         ("crear_motor", "camara-falsa", "event-falso", False))

    def test_el_canal_conecta_al_motor(self):
        motor, canal = MotorDoble(), CanalDoble()
        f, _ = fachada_con(motor=motor, canal=canal)
        f.iniciar()
        self.assertIs(canal.motor_conectado, motor)


class PruebaLecturas(unittest.TestCase):
    def test_ultima_mano_t_sin_motor_es_cero(self):
        """El gate facial lo consulta en cada cuadro: no puede lanzar nada."""
        f, _ = fachada_con(error_motor=ImportError("nada"))
        f.iniciar()
        self.assertEqual(f.ultima_mano_t, 0.0)

    def test_estado_clientes_y_ultima_mano_delegan(self):
        motor, canal = MotorDoble(estado="AGARRE"), CanalDoble()
        canal.clientes = 2
        f, _ = fachada_con(motor=motor, canal=canal)
        f.iniciar()
        self.assertEqual(f.estado, "AGARRE")
        self.assertEqual(f.clientes, 2)
        self.assertEqual(f.ultima_mano_t, 123.5)
        self.assertTrue(f.activos)


class PruebaDetener(unittest.TestCase):
    def test_un_fallo_al_detener_no_interrumpe_el_cierre(self):
        motor = MotorDoble()
        motor.detener = Mock(side_effect=TimeoutError("el hilo no murio"))
        canal = CanalDoble()
        f, _ = fachada_con(motor=motor, canal=canal)
        f.iniciar()
        f.detener()
        self.assertEqual(canal.detener_llamadas, 1)
        self.assertFalse(f.activos)

    def test_detener_deja_la_fachada_vacia(self):
        f, _ = fachada_con(motor=MotorDoble(estado="ARMADO"), canal=CanalDoble())
        f.iniciar()
        f.detener()
        self.assertIsNone(f.motor)
        self.assertIsNone(f.canal)
        self.assertFalse(f.activos)
        self.assertEqual(f.ultima_mano_t, 0.0)


class PruebaLecturaAlDisco(unittest.TestCase):
    """La línea de 1 Hz es instrumento, no andamio: la enciende el despliegue.

    Estaba soldada al overlay (`avisarLectura(pedirVideo)`), así que en cuanto
    nadie pedía el cuadro de calibración el log se quedaba ciego. Pasó cuatro días
    del 29-oct al 2-nov y por eso `73dbe5c2` (la referencia del par) sigue sin
    medirse en sesión real: no hay una sola línea con manos.
    """

    def test_la_fachada_enciende_la_lectura_al_arrancar(self):
        motor = MotorDoble()
        f, _ = fachada_con(motor=motor)
        f.iniciar()
        self.assertIs(motor.lectura, True)

    def test_la_perquilla_apagada_se_respeta(self):
        """`GESTOS_LECTURA=0` es la única forma de callarla en el arranque."""
        motor = MotorDoble()
        f, _ = fachada_con(motor=motor)
        with patch.object(config, "LECTURA", False):
            f.iniciar()
        self.assertIs(motor.lectura, False)

    def test_se_enciende_antes_de_que_el_motor_arranque(self):
        """Si llegara después de `iniciar()`, los primeros cuadros —los del
        `gestos_on`— no se registrarían."""
        orden = []
        motor = MotorDoble()
        motor.fijar_lectura = lambda v: orden.append("lectura")
        motor.iniciar = lambda: orden.append("motor.iniciar")
        f, _ = fachada_con(motor=motor)
        f.iniciar()
        self.assertEqual(orden, ["lectura", "motor.iniciar"])

    def test_un_arranque_degradado_no_deja_lectura_encendida(self):
        """Sin motor no hay nada que lea; y `fijar_lectura` no puede ser lo que
        falle el arranque."""
        f, _ = fachada_con(error_motor=ImportError("falta mediapipe"))
        self.assertFalse(f.iniciar())
        self.assertIsNone(f.motor)

    def test_el_overlay_no_vuelve_a_soldarla(self):
        """Guarda del lado contrario: si alguien reintroduce `{tipo:"lectura"}` en
        el hook, la perquilla de despliegue vuelve a ser decorativa."""
        hook = (RAIZ / "dark_frontend" / "src" / "lib" / "gestos" / "use-gestos.ts")
        self.assertNotIn('"lectura"', hook.read_text(encoding="utf-8"))


class PruebaPuerto(unittest.TestCase):
    def test_el_doble_cumple_el_puerto(self):
        self.assertIsInstance(MotorDoble(), PuertoGestos)


class PruebaFabrica(unittest.TestCase):
    def test_ajustes_desconocidos_del_canal_se_rechazan(self):
        with self.assertRaises(ValueError) as ctx:
            fabrica.crear_canal(puerto=9999)
        self.assertIn("puerto", str(ctx.exception))

    def test_el_canal_toma_host_y_puerto_de_config(self):
        modulo_falso = Mock()
        with patch.dict(sys.modules, {"herramientas.dark_gestos_canal": modulo_falso}):
            fabrica.crear_canal()
        kwargs = modulo_falso.GestosCanal.call_args.kwargs
        self.assertEqual(kwargs["host"], config.HOST)
        self.assertEqual(kwargs["port"], config.PORT)

    def test_el_canal_pisa_la_config_con_kwargs(self):
        modulo_falso = Mock()
        with patch.dict(sys.modules, {"herramientas.dark_gestos_canal": modulo_falso}):
            fabrica.crear_canal(port=0)
        self.assertEqual(modulo_falso.GestosCanal.call_args.kwargs["port"], 0)


class PruebaConfig(unittest.TestCase):
    def test_valores_por_defecto(self):
        self.assertEqual(config.HOST, "127.0.0.1")
        self.assertEqual(config.PORT, 8768)
        # `log` no se puede escribir literal: setUpModule lo redirige a un
        # temporal para que la suite no cree ficheros en el cwd.
        ajuste = config.configuracion()
        self.assertEqual(ajuste["host"], "127.0.0.1")
        self.assertEqual(ajuste["port"], 8768)
        self.assertEqual(ajuste["log"], config.LOG)
        self.assertIs(ajuste["lectura"], True)

    def test_un_defecto_bool_no_cae_en_la_rama_int(self):
        """`isinstance(True, int)` es cierto, así que la rama bool tiene que ir
        antes: sin ella `GESTOS_LECTURA=0` devolvería el entero 0 (que no ES
        False) y `GESTOS_LECTURA=false` devolvería el defecto — lo contrario de lo
        pedido."""
        with patch.dict("os.environ", {"GESTOS_LECTURA": "0"}):
            self.assertIs(config._env("LECTURA", True), False)
        with patch.dict("os.environ", {"GESTOS_LECTURA": "false"}):
            self.assertIs(config._env("LECTURA", True), False)
        with patch.dict("os.environ", {"GESTOS_LECTURA": " OFF "}):
            self.assertIs(config._env("LECTURA", True), False)
        with patch.dict("os.environ", {"GESTOS_LECTURA": "1"}):
            self.assertIs(config._env("LECTURA", True), True)
        with patch.dict("os.environ", {"GESTOS_LECTURA": ""}):
            self.assertIs(config._env("LECTURA", True), True)

    def test_la_variable_de_entorno_manda_y_el_tipo_es_el_del_defecto(self):
        with patch.dict("os.environ", {"GESTOS_PORT": "8790"}):
            self.assertEqual(config._env("PORT", 8768), 8790)
        with patch.dict("os.environ", {"GESTOS_PORT": "no-es-numero"}):
            self.assertEqual(config._env("PORT", 8768), 8768)
        with patch.dict("os.environ", {"GESTOS_PORT": ""}):
            self.assertEqual(config._env("PORT", 8768), 8768)
        with patch.dict("os.environ", {"GESTOS_HOST": "0.0.0.0"}):
            self.assertEqual(config._env("HOST", "127.0.0.1"), "0.0.0.0")

    def test_ruta_de_log_tres_comportamientos(self):
        sin_variable = {k: v for k, v in os.environ.items() if k != "GESTOS_LOG"}
        with patch.dict("os.environ", sin_variable, clear=True):
            self.assertEqual(config.ruta_de_log(), "gestos.log")
        with patch.dict("os.environ", {"GESTOS_LOG": "  /var/log/g.log  "}):
            self.assertEqual(config.ruta_de_log(), "/var/log/g.log")
        # Vaciar la variable es 'sin fichero', no 'el defecto': _env no sirve aquí.
        with patch.dict("os.environ", {"GESTOS_LOG": ""}):
            self.assertEqual(config.ruta_de_log(), "")


class PruebaLog(unittest.TestCase):
    """`enchufar_log`: que los eventos del motor lleguen a disco dentro del núcleo.

    Sin esto, `herramientas/gestos.py` configura su FileHandler sólo en su
    `__main__ --log` y una sesión real pierde cada `gestos_on`/`agarre_inicio` al
    cerrar la consola — el agujero por el que no se puede calibrar el embrague.
    """

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="dark-gestos-log-")
        self.ruta = str(pathlib.Path(self.dir) / "eventos.log")
        self._antes = {
            logger: (logger.level, list(logger.handlers))
            for logger in _loggers_de_gestos()
        }

    def tearDown(self):
        for logger, (nivel, manejadores) in self._antes.items():
            for manejador in list(logger.handlers):
                if manejador not in manejadores:
                    logger.removeHandler(manejador)
                    if isinstance(manejador, logging.FileHandler):
                        manejador.close()
            logger.setLevel(nivel)
        shutil.rmtree(self.dir, ignore_errors=True)

    def _handlers_de_fichero(self, ruta):
        esperado = os.path.normcase(os.path.abspath(ruta))
        return [
            m
            for logger in _loggers_de_gestos()
            for m in logger.handlers
            if isinstance(m, logging.FileHandler)
            and os.path.normcase(m.baseFilename) == esperado
        ]

    def test_sin_ruta_no_se_enchufa_nada(self):
        self.assertEqual(enchufar_log(""), 0)
        self.assertEqual(self._handlers_de_fichero(""), [])

    def test_un_handler_por_logger_y_ruta_resuelta(self):
        self.assertEqual(enchufar_log(self.ruta), 3)
        self.assertEqual(len(self._handlers_de_fichero(self.ruta)), 3)
        self.assertTrue(pathlib.Path(self.ruta).exists())

    def test_es_idempotente(self):
        enchufar_log(self.ruta)
        self.assertEqual(enchufar_log(self.ruta), 0)
        self.assertEqual(len(self._handlers_de_fichero(self.ruta)), 3)

    def test_un_evento_info_llega_al_fichero(self):
        """El motor emite con `LOGGER.info` y el núcleo no hace `basicConfig`: si
        el nivel se queda en WARNING, el fichero existe y está vacío."""
        enchufar_log(self.ruta)
        logging.getLogger("herramientas.gestos").info("gestos_on {'motivo': 'palma'}")
        texto = pathlib.Path(self.ruta).read_text(encoding="utf-8")
        self.assertIn("gestos_on", texto)
        self.assertIn("herramientas.gestos", texto)

    def test_una_ruta_que_no_se_puede_abrir_no_explosiona(self):
        # `self.dir` es un directorio: abrirlo como fichero da OSError.
        self.assertEqual(enchufar_log(self.dir), 0)
        self.assertEqual(self._handlers_de_fichero(self.dir), [])

    def test_el_aviso_de_degradado_tambien_se_escribe(self):
        f, _ = fachada_con(error_motor=ImportError("falta MediaPipe"))
        with patch.object(config, "LOG", self.ruta):
            self.assertFalse(f.iniciar())
        texto = pathlib.Path(self.ruta).read_text(encoding="utf-8")
        self.assertIn("Gestos no disponibles", texto)
        self.assertIn("falta MediaPipe", texto)

    def test_la_ruta_de_la_perilla_llega_a_la_fachada(self):
        self.assertEqual(config.configuracion()["log"], config.LOG)


try:
    import herramientas.gestos as _motor_real

    _HAY_MOTOR = True
except Exception:  # cv2 / numpy / MediaPipe ausentes
    _HAY_MOTOR = False


@unittest.skipUnless(_HAY_MOTOR, "herramientas.gestos necesita cv2 y MediaPipe")
class PruebaMotorReal(unittest.TestCase):
    def test_el_motor_real_cumple_el_puerto(self):
        """Construirlo no abre la cámara: eso lo hace VisionService al iniciar."""
        self.assertIsInstance(_motor_real.GestureEngine(Mock()), PuertoGestos)

    def test_la_tabla_de_estados_ata_los_literales_del_motor(self):
        """El worker indexa por estas cadenas sus histogramas de CPU y fps."""
        self.assertEqual(
            [e.value for e in EstadosGestos],
            [_motor_real.APAGADO, _motor_real.ARMADO, _motor_real.AGARRE],
        )

    def test_sin_acceso_concedido_el_motor_arranca_apagado(self):
        motor = _motor_real.GestureEngine(Mock(), acceso=threading.Event())
        self.assertEqual(motor.estado, _motor_real.APAGADO)
        self.assertEqual(motor.ultima_mano_t, 0.0)

    def test_el_motor_no_conoce_la_interfaz(self):
        """Lo que promete el contrato: emite eventos y nada más."""
        proscritos = [n for n in _importaciones(_motor_real.__file__)
                      if "overlay" in n or "frontend" in n]
        self.assertEqual(proscritos, [])


@unittest.skipUnless(_HAY_MOTOR, "herramientas.gestos necesita cv2 y MediaPipe")
class PruebaIntegracionReal(unittest.TestCase):
    """Las fábricas de la fachada van inyectadas con dobles en el resto del
    archivo, así que una firma que no encaje entre la capa y las clases de
    `herramientas/` pasaría desapercibida. Aquí se llaman a las de verdad, sin
    arrancar ningún hilo: `GestureEngine` guarda el servicio y no lo toca hasta
    `iniciar()`, y `Mock()` sirve para la cámara."""

    def test_la_fabrica_produce_un_motor_conforme(self):
        motor = fabrica.crear_motor(Mock(), threading.Event())
        self.assertIsInstance(motor, PuertoGestos)
        self.assertEqual(motor.estado, _motor_real.APAGADO)

    def test_el_canal_real_se_conecta_al_motor_real(self):
        """Los dos sentidos de la costura: eventos hacia el canal, `sostiene` de
        vuelta al motor. Se comprueba que el aviso LLEGA; lo que el motor hace
        con él (no apagar con un puño que sostiene algo) es del paso de estado y
        lo prueba herramientas/tests/test_gestos_puno.py."""
        motor = fabrica.crear_motor(Mock(), threading.Event())
        canal = fabrica.crear_canal(port=0)
        canal.conectar_motor(motor)
        self.assertEqual(motor.on_evento, canal.emitir)
        canal.on_mensaje({"tipo": "sostiene", "valor": True})
        self.assertTrue(motor._sostiene)

    def test_el_canal_real_abre_y_cierra_un_puerto_efimero(self):
        """`iniciar()` espera de verdad a que el servidor escucha; con port=0 no
        choca con el 8768 del núcleo en marcha."""
        canal = fabrica.crear_canal(port=0)
        canal.iniciar()
        self.assertEqual(canal.clientes, 0)
        canal.detener()


class PruebaAcoplamiento(unittest.TestCase):
    """Regla de la casa: fuera de la fábrica, nadie nombra la implementación.

    `dark_nucleo.py` son 7600 líneas, así que el árbol se parsea una sola vez
    por clase, como hace `tests/test_herramienta_contrato.py`.
    """

    PROSCRITOS = frozenset({"herramientas.gestos", "herramientas.dark_gestos_canal"})
    PERMITIDOS = {"gestos/fabrica.py", "herramientas/gestos.py",
                  "herramientas/dark_gestos_canal.py"}

    @classmethod
    def setUpClass(cls):
        cls._nucleo = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8")
        cls._arbol = ast.parse(cls._nucleo)

    def test_ningun_modulo_de_produccion_importa_el_motor_o_el_canal(self):
        culpables = []
        for ruta in sorted(DARK_PYTHON.rglob("*.py")):
            rel = str(ruta.relative_to(DARK_PYTHON)).replace("\\", "/")
            if "__pycache__" in rel or rel.startswith(("respaldo/", "herramientas/tests/")):
                continue
            if rel in self.PERMITIDOS:
                continue
            texto = ruta.read_text(encoding="utf-8")
            # Pre-filtro: todo nombre proscrito lleva "herramientas", y parsear
            # los ~150 archivos del paquete costaba medio suite.
            if "herramientas" not in texto:
                continue
            if self.PROSCRITOS & set(_importaciones_de(texto)):
                culpables.append(rel)
        self.assertEqual(culpables, [])

    def test_el_nucleo_usa_la_fachada_y_la_fabrica_de_camara(self):
        self.assertIn("from acceso import FachadaAcceso, crear_servicio_camara", self._nucleo)
        self.assertIn("from gestos import FachadaGestos", self._nucleo)
        self.assertNotIn("herramientas.gestos", self._nucleo)
        self.assertNotIn("VisionService", self._nucleo)

    def test_los_gestos_se_levantan_en_la_concesion_no_en_el_arranque(self):
        """`crear_motor` importa `herramientas/gestos.py`, y eso vale ~1,08 s de
        cv2+MediaPipe, más los 7,8 MB del modelo que carga el detector al arrancar
        el hilo. Esa cuenta no se paga con D.A.R.K. bloqueado, y tampoco dentro
        del hilo que concede el acceso: va en un hilo breve."""

        def cuerpo(nombre):
            for nodo in ast.walk(self._arbol):
                if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre:
                    return nodo
            self.fail(f"{nombre} ya no existe en dark_nucleo.py")

        def metodos_llamados(raiz):
            return {n.func.attr for n in ast.walk(raiz)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}

        self.assertNotIn("_arrancar_gestos", metodos_llamados(cuerpo("_iniciar_puerta_acceso")))
        self.assertIn("_arrancar_gestos", metodos_llamados(cuerpo("_al_conceder_acceso")))

        arranque = cuerpo("_arrancar_gestos")
        self.assertIn("_levantar", {n.name for n in ast.walk(arranque)
                                    if isinstance(n, ast.FunctionDef)})
        hilos = [n for n in ast.walk(arranque)
                 if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "Thread"]
        self.assertEqual(len(hilos), 1)
        destinos = {k.value.id for k in hilos[0].keywords
                    if k.arg == "target" and isinstance(k.value, ast.Name)}
        self.assertEqual(destinos, {"_levantar"})

    def test_el_motor_pide_cero_fps_mientras_el_acceso_no_esta_concedido(self):
        """La promesa que hace que re-bloquear no deje la cámara abierta. Se
        comprueba en el código del worker, no lanzando hilos: es la línea que el
        núcleo respeta al pasarle su Event."""
        fuente = (DARK_PYTHON / "herramientas" / "gestos.py").read_text(encoding="utf-8")
        self.assertIn("if self._acceso is not None and not self._acceso.is_set():", fuente)
        self.assertIn("sub.fijar_fps(0.0)", fuente)


if __name__ == "__main__":
    unittest.main()
