"""R4 Fase B: el cliente concreto del Manager, contra el contrato de la Fase A.

Aquí no se toca la red. La Fase B escribió este cliente cuando todavía no lo consumía
nadie; desde la **Fase C1** los tres consumidores pequeños (`model_broker`,
`especialista_codigo`, `especialista_tareas`) y desde la **Fase C2** el propio
`dark_nucleo.py` ya solo llegan a los dos servidores por él, y lo que sigue vigilado
aquí es que el adaptador sea **fiel al transporte que ya existía** —misma URL, mismo
verbo, mismo timeout, mismo cuerpo— y que degradar nunca lance, porque el Manager es un
proceso C# que puede estar apagado.

Cuatro familias de pruebas:

  * **Conformidad con el puerto**: los 16 métodos, las 16 firmas, y las dos barreras que
    dicen quién puede nombrar la clase (solo `fabrica.py`) y quién puede construir el
    cliente (la fábrica y los cuatro consumidores migrados).
  * **Las 14 rutas declaradas**: tabla con la URL, el verbo, el payload y el timeout que
    sale de cada método. Es `RUTAS_MANAGER` + `RUTAS_TAREAS` traducido a llamadas; las
    dos que faltan respecto a las 16 medidas (`GET /tasks/{id}` y
    `POST /tasks/{id}/steps`) las borró la C2 porque nadie las pedía.
  * **Degradación**: un 500 y una conexión rechazada, ruta por ruta, con el valor que
    promete el contrato y la línea que se imprime.
  * **Los consumidores de la C1**: la tabla de resultados de `broker.asegurar` —la
    mentira del 400 cerrada por decisión del usuario—, el reintento del código y la
    forma de `obtener_tareas()`. Viven aquí porque son el contrato puesto a prueba.

Ref: dark_python/proveedores/manager/{cliente,fabrica}.py, contratos/manager.py.
"""
import ast
import contextlib
import inspect
import io
import os
import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import requests  # noqa: E402

from contratos.manager import (  # noqa: E402
    MANAGER,
    RUTAS_MANAGER,
    RUTAS_TAREAS,
    TASK_MANAGER,
    EstadoRecursos,
    PuertoClienteManager,
    PuertoRecursos,
    PuertoTaskManager,
    ResultadoCarga,
    Tarea,
)
from proveedores.manager.cliente import (  # noqa: E402
    TIEMPOS_POR_DEFECTO,
    ClienteManager,
    _canon,
    _unir,
)
from proveedores.manager.fabrica import crear_cliente_manager  # noqa: E402

CLIENTE_REL = "proveedores/manager/cliente.py"
FABRICA_REL = "proveedores/manager/fabrica.py"
CONTRATO_REL = "contratos/manager.py"
#: Los cuatro consumidores del Manager: los tres pequeños desde la Fase C1 y el núcleo
#: desde la C2. Todos llegan a los dos servidores por el cliente de abajo.
CONSUMIDORES = ("nucleo/dark_nucleo.py",
                "especialistas/especialista_tareas.py",
                "especialistas/especialista_codigo.py",
                "herramientas/internas/model_broker.py")

# ---- Las formas medidas el 25-oct contra los dos servidores vivos (solo GET).
STATUS_MEDIDO = {
    "ramDisponibleMB": 4889, "ollamaDisponible": True, "modelosActivos": [],
    "ramUsadaPorModelosMB": 0, "presupuestoTotalMB": 8837,
    "presupuestoRestanteMB": 8837, "cpuUsoPct": 15.1, "cpuTempC": None,
}
TAREA_MEDIDA = {
    "id": "5e784bfd-84b7-4e5c-aad4-4631c6c46f2e",
    "descripcion": "Biografia interactiva de Albert Einstein en HTML5 + CSS",
    "estado": "Cancelada", "prioridad": "Alta", "moduloAsignado": "Nucleo",
    "pasos": [{"id": f"paso-{i + 1}", "descripcion": "p", "completado": i < 2,
               "intentos": 1, "resultado": None, "error": None} for i in range(5)],
    "pasoActualId": None, "errores": [], "resultadoFinal": None,
    "snapshotInicial": {"a": 1}, "metadata": {},
}
ID = TAREA_MEDIDA["id"]

#: `\b` al principio para que `PuertoClienteManager` no cuente como mención a la clase.
NOMBRE_DE_LA_CLASE = re.compile(r"\bClienteManager\b")


def _fuente(rel):
    return (DARK_PYTHON / rel).read_text(encoding="utf-8")


def _modulos_de_produccion():
    """Todos los .py de `dark_python` salvo el `__pycache__`."""
    for ruta in sorted(DARK_PYTHON.rglob("*.py")):
        if "__pycache__" in ruta.parts:
            continue
        yield ruta, ruta.relative_to(DARK_PYTHON).as_posix()


class _Respuesta:
    """El `Response` de requests por la parte que usa el cliente."""

    def __init__(self, codigo=200, cuerpo=None, texto=""):
        self.status_code = codigo
        self._cuerpo = cuerpo
        self.text = texto

    def json(self):
        if self._cuerpo is None:
            raise ValueError("el cuerpo no es JSON")
        return self._cuerpo


class DobleSesion:
    """Registra cada llamada y devuelve lo que le toque. `error=` simula que ni hubo
    respuesta (el Manager apagado)."""

    def __init__(self, respuesta=None, error=None):
        self.llamadas = []
        self._respuesta = respuesta
        self._error = error
        self.cerrada = False

    def request(self, verbo, url, json=None, timeout=None):
        self.llamadas.append((verbo, url, json, timeout))
        if self._error is not None:
            raise self._error
        return self._respuesta if self._respuesta is not None else _Respuesta(200)

    def close(self):
        self.cerrada = True

    @property
    def ultima(self):
        return self.llamadas[-1]


def _cliente(respuesta=None, error=None, **kw):
    doble = DobleSesion(respuesta, error)
    return ClienteManager(session=doble, **kw), doble


def _silencioso(llamable, *a, **k):
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        resultado = llamable(*a, **k)
    return resultado, salida.getvalue()


def _rutas_del_cliente():
    """Las claves de `TIEMPOS_POR_DEFECTO`: lo que el cliente puede pedir."""
    return set(TIEMPOS_POR_DEFECTO)


def _rutas_del_contrato():
    salida = set()
    for tabla in (RUTAS_MANAGER, RUTAS_TAREAS):
        for ruta, verbo, _ in tabla:
            salida.add((verbo, _canon(ruta)))
    return salida


class TestConformidadConElPuerto(unittest.TestCase):
    def _metodos(self, puerto):
        return {n for n in dir(puerto) if not n.startswith("_")
                and callable(getattr(puerto, n, None))}

    def test_el_cliente_es_exactamente_los_dieciseis_metodos_del_puerto(self):
        promesa = self._metodos(PuertoClienteManager)
        self.assertEqual(len(promesa), 16)
        self.assertEqual(promesa,
                         self._metodos(PuertoRecursos)
                         | self._metodos(PuertoTaskManager) | {"cerrar"},
                         "la reunión de los dos puertos dejó de ser el cliente")
        self.assertEqual(self._metodos(ClienteManager), promesa,
                         "el cliente y el puerto dejaron de ser el mismo vocabulario")

    def test_ninguna_firma_deriva_del_puerto(self):
        for nombre in sorted(self._metodos(PuertoClienteManager)):
            with self.subTest(metodo=nombre):
                self.assertEqual(
                    str(inspect.signature(getattr(PuertoClienteManager, nombre))),
                    str(inspect.signature(getattr(ClienteManager, nombre))),
                    "el puerto y la implementación divergieron: la fábrica promete una "
                    "cosa y entrega otra")

    def test_la_fabrica_es_el_unico_sitio_de_produccion_que_nombra_la_clase(self):
        """`\bClienteManager\b` y no `ClienteManager` a secas: `PuertoClienteManager`
        contiene la palabra y el contrato la menciona mil veces sin construir nada."""
        menciones = [rel for _, rel in _modulos_de_produccion()
                     if rel != CLIENTE_REL and NOMBRE_DE_LA_CLASE.search(_fuente(rel))]
        self.assertEqual(menciones, [FABRICA_REL],
                         "alguien más construye el cliente: la regla de la casa es la "
                         "fábrica")

    def test_el_contrato_lo_conocen_su_cliente_y_sus_cuatro_consumidores(self):
        """Barrera heredada de la Fase A, movida dos veces: allí nadie consumía el
        contrato; en la B lo conocía solo el cliente; desde la C1 lo conocen también los
        tres migrados, el núcleo que los cablea y la fábrica de especialistas. Un módulo
        fuera de esta lista que nombre el contrato se ha saltado la Fase C que le toca."""
        senales = ("contratos.manager", "from contratos import manager",
                   "PuertoClienteManager", "PuertoTaskManager", "EstadoRecursos",
                   "ResultadoCarga")
        permitidos = ({CONTRATO_REL, CLIENTE_REL, FABRICA_REL}
                      | set(CONSUMIDORES) | {"contratos/especialista.py",
                                             "especialistas/fabrica.py"})
        encontrados = {rel for _, rel in _modulos_de_produccion()
                       if rel not in permitidos
                       and any(s in _fuente(rel) for s in senales)}
        self.assertEqual(encontrados, set(),
                         f"estos módulos hablan con el contrato de R4 sin haber pasado "
                         f"por su fase: {sorted(encontrados)}")

    def test_los_cuatro_consumidores_solo_conocen_al_cliente(self):
        """La barrera que levantó la C1 y cerró la C2: ningún consumidor escribe la URL,
        y los cuatro piden el cliente a la fábrica. La cuenta de sitios a mano la vigila
        `test_contrato_manager.test_cero_sitios_crudos_todos_migrados`."""
        for rel in CONSUMIDORES:
            self.assertIn("crear_cliente_manager", _fuente(rel),
                          f"{rel} dejó de pedir el cliente")
            for nombre in ("MANAGER_URL", "TASK_MANAGER_URL"):
                self.assertNotIn(nombre, _fuente(rel),
                                 f"{rel} volvió a escribir {nombre}")
        fuente = _fuente("nucleo/dark_nucleo.py")
        for declaracion in ('MANAGER_URL = "http://localhost:5050"',
                            'TASK_MANAGER_URL = "http://localhost:5051"'):
            self.assertNotIn(declaracion, fuente,
                             "la URL del núcleo volvió a estar escrita a mano: el "
                             "defecto 4 reabierto")


class TestUnaSolaSalidaHTTP(unittest.TestCase):
    def test_todo_sale_por_un_metodo_de_la_sesion(self):
        """El cliente usa **una** primitiva de `requests`: `session.request`. Si alguien
        añade un `.get(` directo hay dos salidas que vigilar y la tabla de rutas deja de
        ser la dueña de lo que sale."""
        atributos = set()
        for nodo in ast.walk(ast.parse(_fuente(CLIENTE_REL))):
            if (isinstance(nodo, ast.Attribute)
                    and isinstance(nodo.value, ast.Attribute)
                    and nodo.value.attr == "_http"):
                atributos.add(nodo.attr)
        self.assertEqual(atributos, {"request", "close"})

    def test_una_sesion_por_cliente(self):
        self.assertEqual(_fuente(CLIENTE_REL).count("requests.Session()"), 1)

    def test_construirse_no_toca_la_red(self):
        cliente = ClienteManager()
        self.assertIsInstance(cliente._http, requests.Session)
        self.assertTrue(cliente._sesion_propia)
        self.assertEqual(cliente._manager_url, MANAGER)
        self.assertEqual(cliente._task_url, TASK_MANAGER)

    def test_el_host_no_esta_escrito_en_ningun_sitio(self):
        """Seis copias de la URL son el defecto 4; la séptima sería peor que el
        defecto. Las dos bases vienen del contrato y el entorno las pisa."""
        for rel in (CLIENTE_REL, FABRICA_REL):
            lineas = [ln.strip() for ln in _fuente(rel).splitlines()
                      if "localhost" in ln or "http://" in ln]
            self.assertEqual(lineas, [], f"{rel} vuelve a escribir una URL: {lineas}")

    def test_los_numeros_de_puerto_no_salen_del_contrato(self):
        """Los puertos sí aparecen, pero solo como prosa de sección. Lo que no puede
        aparecer es un `5050` dentro de una expresión: eso sería una séptima copia."""
        for rel in (CLIENTE_REL, FABRICA_REL):
            codigo = [ln.strip() for ln in ast.unparse(
                ast.parse(_fuente(rel))).splitlines()
                if "5050" in ln or "5051" in ln]
            self.assertEqual(codigo, [], f"{rel} pone un puerto en el código: {codigo}")

    def test_los_agujeros_de_plantilla_se_cuentan(self):
        self.assertEqual(_unir("/tasks/{tarea_id}/cancel", ID), f"/tasks/{ID}/cancel")
        self.assertEqual(_unir("/tasks/{tarea_id}/steps/{paso_id}/fail", "t", "p"),
                         "/tasks/t/steps/p/fail")
        self.assertEqual(_unir("/status"), "/status")
        with self.assertRaises(AssertionError):
            _unir("/tasks/{tarea_id}", "de", "sobra")


class TestLasCatorceRutas(unittest.TestCase):
    """Cada método contra la URL, el verbo, el cuerpo y el timeout que le tocan."""

    def setUp(self):
        self.cliente, self.doble = _cliente(_Respuesta(200, {}, ""))

    def _esperar(self, verbo, url, payload, timeout):
        self.assertEqual(self.doble.ultima, (verbo, url, payload, timeout))

    def test_las_rutas_que_puede_pedir_el_cliente_son_las_del_contrato(self):
        self.assertEqual(_rutas_del_cliente(), _rutas_del_contrato())
        self.assertEqual(len(_rutas_del_cliente()), 14)

    def test_las_tres_del_manager(self):
        c = self.cliente
        c.estado()
        self._esperar("GET", f"{MANAGER}/status", None, 5.0)
        c.cargar_modelo("qwen2.5:7b-instruct")
        self._esperar("POST", f"{MANAGER}/load/qwen2.5:7b-instruct", None, 30.0)
        c.descargar_modelo("qwen2.5:7b-instruct")
        self._esperar("POST", f"{MANAGER}/unload/qwen2.5:7b-instruct", None, 15.0)

    def test_el_probe_de_arranque_tiene_su_propio_timeout(self):
        self.cliente.esta_vivo()
        self._esperar("GET", f"{MANAGER}/status", None, 1.0)

    def test_las_once_del_task_manager(self):
        c, base = self.cliente, TASK_MANAGER
        c.listar()
        self._esperar("GET", f"{base}/tasks", None, 5.0)
        c.interrumpidas()
        self._esperar("GET", f"{base}/tasks/interrupted", None, 5.0)
        c.eliminar(ID)
        self._esperar("DELETE", f"{base}/tasks/{ID}", None, 5.0)
        c.iniciar(ID)
        self._esperar("POST", f"{base}/tasks/{ID}/start", None, 5.0)
        c.cancelar(ID)
        self._esperar("POST", f"{base}/tasks/{ID}/cancel", None, 5.0)
        c.pausar(ID)
        self._esperar("POST", f"{base}/tasks/{ID}/pause", None, 5.0)
        c.reanudar(ID)
        self._esperar("POST", f"{base}/tasks/{ID}/resume", None, 5.0)
        c.completar_paso(ID, "p1", "hecho")
        self._esperar("POST", f"{base}/tasks/{ID}/steps/p1/complete",
                      {"resultado": "hecho"}, 5.0)
        c.fallar_paso(ID, "p1", "roto")
        self._esperar("POST", f"{base}/tasks/{ID}/steps/p1/fail",
                      {"error": "roto"}, 5.0)
        c.completar(ID, "listo")
        self._esperar("POST", f"{base}/tasks/{ID}/complete",
                      {"resultado": "listo"}, 10.0)
        c.crear("hacer algo")
        self._esperar("POST", f"{base}/tasks",
                      {"descripcion": "hacer algo", "prioridad": 2, "modulo": 0,
                       "pasos": []}, 5.0)

    def test_los_cuerpos_vacios_son_cuerpos_vacios(self):
        """Hoy `/start`, `/cancel` y `/pause` se POSTean sin body. Mandar `{}` cambiaría
        la petición que recibe un servidor C# que no hemos pedido prestado."""
        for metodo in (self.cliente.iniciar, self.cliente.cancelar, self.cliente.pausar):
            metodo(ID)
            with self.subTest(metodo=metodo.__name__):
                self.assertEqual((self.doble.ultima[0], self.doble.ultima[2]),
                                 ("POST", None))

    def test_completar_paso_sin_resultado_manda_objeto_vacio(self):
        """Es literalmente lo que hace el núcleo hoy: `{"resultado": r} if r else {}`."""
        self.cliente.completar_paso(ID, "p1")
        self.assertEqual(self.doble.ultima[2], {})

    def test_la_tabla_de_timeouts_es_la_snapshot_mediada(self):
        self.assertEqual(TIEMPOS_POR_DEFECTO, {
            ("GET", "/status"): 5.0,
            ("POST", "/load/{*}"): 30.0,
            ("POST", "/unload/{*}"): 15.0,
            ("GET", "/tasks"): 5.0,
            ("POST", "/tasks"): 5.0,
            ("DELETE", "/tasks/{*}"): 5.0,
            ("POST", "/tasks/{*}/start"): 5.0,
            ("POST", "/tasks/{*}/steps/{*}/complete"): 5.0,
            ("POST", "/tasks/{*}/steps/{*}/fail"): 5.0,
            ("POST", "/tasks/{*}/complete"): 10.0,
            ("POST", "/tasks/{*}/cancel"): 5.0,
            ("POST", "/tasks/{*}/pause"): 5.0,
            ("POST", "/tasks/{*}/resume"): 5.0,
            ("GET", "/tasks/interrupted"): 5.0,
        })

    def test_un_consumidor_puede_pisar_el_timeout(self):
        """Los números propios que la Fase C tiene que conservar: probe 1 s, cancelación
        del menú 8 s, `_preparar_modelo_de_trabajo` 60 s, `/interrupted` del núcleo 3 s."""
        c = self.cliente
        c.cancelar(ID, timeout=8)
        self.assertEqual(self.doble.ultima[3], 8)
        c.cargar_modelo("m", timeout=60)
        self.assertEqual(self.doble.ultima[3], 60)
        c.interrumpidas(timeout=3)
        self.assertEqual(self.doble.ultima[3], 3)

    def test_una_ruta_no_declarada_se_cae_por_su_timeout(self):
        """No hay guard aparte: la tabla ES el inventario. Nadie puede sacar una ruta
        que `contratos/manager.py` no haya declarado."""
        with self.assertRaises(KeyError):
            self.cliente._pedir("GET", "/no-existe")
        self.assertEqual(self.doble.llamadas, [],
                         "la ruta inventada ni siquiera llegó a salir")


class TestLoQueNormalizaElCliente(unittest.TestCase):
    def test_listar_normaliza_el_dict_keyed_por_id(self):
        c, _ = _cliente(_Respuesta(200, {ID: TAREA_MEDIDA,
                                         "otro": dict(TAREA_MEDIDA, id="otro")}))
        tareas = c.listar()
        self.assertIsInstance(tareas, tuple)
        self.assertEqual([t.id for t in tareas], [ID, "otro"])
        self.assertIsInstance(tareas[0], Tarea)
        self.assertEqual(tareas[0].progreso, (2, 5))

    def test_listar_no_exige_un_diccionario(self):
        """/tasks devolvió un dict el 25-oct; `/tasks/interrupted` devuelve una lista.
        El cliente sabe las dos formas y no las mezcla hacia afuera."""
        c, _ = _cliente(_Respuesta(200, [TAREA_MEDIDA]))
        self.assertEqual([t.id for t in c.listar()], [ID])

    def test_interrumpidas_es_lista_y_sale_normalizada(self):
        c, _ = _cliente(_Respuesta(200, [TAREA_MEDIDA]))
        tareas = c.interrumpidas()
        self.assertEqual(len(tareas), 1)
        self.assertFalse(tareas[0].reanudable,
                         "una Cancelada a 2/5 pasos no es reanudable: defecto 2")

    def test_leer_vacio_frente_a_no_leer(self):
        """El consumidor del metrónomo necesita la diferencia: con `()` calla (no hay
        nada que reanimar); con `None` dice "No pude conectar con el gestor de tareas"
        en vez de mentir. El cliente no decide cuál de las dos es un error."""
        vacio, _ = _cliente(_Respuesta(200, {}))
        self.assertEqual(vacio.listar(), ())
        sin_leer, _ = _cliente(_Respuesta(500, None, "null reference"))
        self.assertIsNone(_silencioso(sin_leer.listar)[0])
        self.assertIsNone(_silencioso(sin_leer.interrumpidas)[0])

    def test_modelos_activos_acepta_las_dos_formas(self):
        """`modelosActivos` llega vacío hoy: el núcleo lo lee como dicts con `name` y el
        contrato promete nombres. Las dos se toleran, ninguna se inventa."""
        con_dicts = dict(STATUS_MEDIDO,
                         modelosActivos=[{"name": "qwen2.5:7b-instruct"}])
        c, _ = _cliente(_Respuesta(200, con_dicts))
        self.assertEqual(c.estado().modelos_activos, ("qwen2.5:7b-instruct",))
        self.assertTrue(c.estado().residencia)
        c2, _ = _cliente(_Respuesta(200, dict(STATUS_MEDIDO,
                                              modelosActivos=["a", "", None])))
        self.assertEqual(c2.estado().modelos_activos, ("a",))

    def test_estado_con_el_status_medido(self):
        c, _ = _cliente(_Respuesta(200, STATUS_MEDIDO))
        estado = c.estado()
        self.assertIsInstance(estado, EstadoRecursos)
        self.assertTrue(estado.respondio)
        self.assertEqual((estado.ram_disponible_mb, estado.presupuesto_restante_mb),
                         (4889, 8837))
        self.assertFalse(estado.residencia)

    def test_crear_devuelve_el_id_sin_convertir_nada(self):
        """Defecto 6: mando enteros, recibo cadenas. El cliente no traduce."""
        c, doble = _cliente(_Respuesta(200, {"id": ID, "prioridad": "Alta"}))
        self.assertEqual(c.crear("algo", prioridad=2, modulo=0,
                                 pasos=[{"id": "p1"}]), ID)
        self.assertEqual(doble.ultima[2], {"descripcion": "algo", "prioridad": 2,
                                           "modulo": 0, "pasos": [{"id": "p1"}]})

    def test_crear_sin_id_en_el_cuerpo_no_es_un_keyerror(self):
        """Hoy `r.json()["id"]` lanza KeyError con un 200 raro, y el único `except` que
        lo rodea es el de `RequestException`. El cliente degrada a None."""
        c, _ = _cliente(_Respuesta(200, {"mensaje": "sin id"}))
        self.assertIsNone(c.crear("algo"))

    def test_reanudar_normaliza_el_cuerpo_del_servidor(self):
        c, _ = _cliente(_Respuesta(200, TAREA_MEDIDA))
        reanudada = c.reanudar(ID)
        self.assertIsInstance(reanudada, Tarea)
        self.assertEqual(reanudada.estado_canonico, "cancelada")


class TestDegradacionRutaPorRuta(unittest.TestCase):
    """Un 500 y una conexión rechazada: lo que devuelve el cliente, no lo que hace el
    consumidor con eso (eso sigue siendo del núcleo)."""

    def _llamar_todos(self, cliente):
        """Los 15 métodos del puerto que hacen HTTP (el 16, `cerrar()`, cierra la sesión
        y no sale a la red)."""
        return {
            "estado": cliente.estado(), "esta_vivo": cliente.esta_vivo(),
            "cargar_modelo": cliente.cargar_modelo("m"),
            "descargar_modelo": cliente.descargar_modelo("m"),
            "listar": cliente.listar(), "interrumpidas": cliente.interrumpidas(),
            "crear": cliente.crear("d"), "iniciar": cliente.iniciar(ID),
            "completar_paso": cliente.completar_paso(ID, "p"),
            "fallar_paso": cliente.fallar_paso(ID, "p", "e"),
            "completar": cliente.completar(ID, "r"),
            "cancelar": cliente.cancelar(ID), "pausar": cliente.pausar(ID),
            "reanudar": cliente.reanudar(ID), "eliminar": cliente.eliminar(ID),
        }

    def test_un_500_devuelve_la_forma_degradada(self):
        cliente, _ = _cliente(_Respuesta(500, None, "null reference"))
        salida, impreso = _silencioso(self._llamar_todos, cliente)
        self.assertEqual(salida["estado"], EstadoRecursos())
        self.assertFalse(salida["estado"].respondio)
        self.assertIsNone(salida["listar"],
                          "None es 'no pude leer', () es 'leí y no hay': ver "
                          "test_leer_vacio_frente_a_no_leer")
        self.assertIsNone(salida["interrumpidas"])
        self.assertIsNone(salida["crear"])
        self.assertIsNone(salida["reanudar"])
        for escritura in ("descargar_modelo", "iniciar", "completar_paso", "fallar_paso",
                          "completar", "cancelar", "pausar", "eliminar"):
            self.assertIs(salida[escritura], False, escritura)
        self.assertIs(salida["esta_vivo"], True,
                      "un 500 sigue siendo alguien al otro lado: el probe de arranque "
                      "no mira el código")
        self.assertIs(salida["cargar_modelo"].codigo_http, 500)
        self.assertFalse(salida["cargar_modelo"].aceptado)
        self.assertIn("null reference", impreso)

    def test_sin_conexion_no_lanza_nada(self):
        cliente, doble = _cliente(error=requests.exceptions.ConnectionError("apagado"))
        salida, impreso = _silencioso(self._llamar_todos, cliente)
        self.assertIs(salida["esta_vivo"], False)
        self.assertIsNone(salida["cargar_modelo"].codigo_http)
        self.assertEqual(salida["cargar_modelo"].detalle, "sin respuesta")
        self.assertEqual(len(doble.llamadas), 15)
        self.assertEqual(impreso.count("apagado"), 15,
                         "cada ruta dice dónde se cayó; ninguna se traga el error")
        for etiqueta in ("[Manager]", "[Tareas]"):
            self.assertIn(etiqueta, impreso)

    def test_un_200_que_no_es_json_no_rompe(self):
        """`/start`, `/cancel` y `/pause` contestan sin cuerpo. Un `estado()` con cuerpo
        de texto plano no es un Manager con cero RAM: es una respuesta que no sirve."""
        cliente, _ = _cliente(_Respuesta(200, None, "OK"))
        self.assertTrue(cliente.iniciar(ID))
        self.assertTrue(cliente.cancelar(ID))
        estado, _ = _silencioso(cliente.estado)
        self.assertIsInstance(estado, EstadoRecursos)
        self.assertFalse(estado.respondio)

    def test_la_politica_de_error_sigue_siendo_del_consumidor(self):
        """El broker corta **solo con un rechazo explícito** (`status` en
        `CARGA_RECHAZADA`) y sigue con cualquier error ambiguo —el `HTTP 400 sin estado`
        que esta caja contesta de verdad—; el especialista de código reintenta una vez el
        400. El cliente no elige por ellos: entrega `codigo_http` y `status` tal cual. La
        política se prueba en `tests/test_consumidores_manager.py`."""
        c, _ = _cliente(_Respuesta(400, {"status": "RAM_INSUFFICIENT"}, "no hay ram"))
        self.assertEqual(c.cargar_modelo("m"),
                         ResultadoCarga(aceptado=False, estado="RAM_INSUFFICIENT",
                                        codigo_http=400, detalle="no hay ram"))
        c2, _ = _cliente(_Respuesta(200, {"status": "ya_cargado"}))
        self.assertTrue(c2.cargar_modelo("m").aceptado)
        c3, _ = _cliente(_Respuesta(200, {"status": "PRESUPUESTO_EXCEDIDO"}))
        self.assertFalse(c3.cargar_modelo("m").aceptado)

    def test_el_detalle_llega_truncado_como_lo_imprime_el_nucleo(self):
        c, _ = _cliente(_Respuesta(200, {"status": "cargado"}, "x" * 500))
        self.assertEqual(len(c.cargar_modelo("m").detalle), 120)


class TestLaFabrica(unittest.TestCase):
    def tearDown(self):
        for variable in ("DARK_MANAGER_URL", "DARK_TASK_MANAGER_URL"):
            os.environ.pop(variable, None)

    def test_la_fabrica_construye_el_cliente(self):
        cliente = crear_cliente_manager(session=DobleSesion())
        self.assertIsInstance(cliente, ClienteManager)
        self.assertEqual((cliente._manager_url, cliente._task_url),
                         (MANAGER, TASK_MANAGER))

    def test_el_entorno_manda_sobre_el_contrato(self):
        os.environ["DARK_MANAGER_URL"] = "http://otra.maquina:5050/"
        os.environ["DARK_TASK_MANAGER_URL"] = "http://otra.maquina:5051"
        doble = DobleSesion()
        cliente = crear_cliente_manager(session=doble)
        self.assertEqual(cliente._manager_url, "http://otra.maquina:5050")
        self.assertEqual(cliente._task_url, "http://otra.maquina:5051")
        cliente.estado()
        self.assertEqual(doble.ultima[1], "http://otra.maquina:5050/status")

    def test_el_argumento_explicito_manda_sobre_el_entorno(self):
        os.environ["DARK_MANAGER_URL"] = "http://env:5050"
        cliente = crear_cliente_manager(session=DobleSesion(),
                                        manager_url="http://explicito:5050")
        self.assertEqual(cliente._manager_url, "http://explicito:5050")

    def test_la_firma_de_la_fabrica_es_la_promesa(self):
        firma = inspect.signature(crear_cliente_manager)
        self.assertEqual(list(firma.parameters),
                         ["session", "manager_url", "task_manager_url"])
        self.assertIn("PuertoClienteManager", str(firma.return_annotation),
                      "la fábrica devuelve el puerto, no la clase")

    def test_el_cliente_no_importa_a_ningun_modulo_del_proyecto(self):
        """La capa de abajo no conoce a la de arriba: `cliente.py` solo habla con el
        contrato y con `requests`."""
        importados = set()
        for nodo in ast.walk(ast.parse(_fuente(CLIENTE_REL))):
            if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                origen = (nodo.module or "") if isinstance(nodo, ast.ImportFrom) \
                    else nodo.names[0].name
                importados.add(origen.split(".")[0])
        self.assertEqual(importados, {"__future__", "re", "collections",
                                      "dataclasses", "typing", "requests",
                                      "contratos"}, importados)


class TestCerrar(unittest.TestCase):
    def test_cerrar_cierra_la_sesion_propia(self):
        cliente = ClienteManager()
        cerradas = []
        cliente._http.close = lambda: cerradas.append(True)
        cliente.cerrar()
        self.assertEqual(cerradas, [True])

    def test_cerrar_dos_veces_no_estropea_nada(self):
        """`Session.close()` es idempotente y el cliente no añade estado: la Fase D va
        a llamar a `cerrar()` desde más de un sitio (parada del núcleo y de los
        pollers) y no necesita un flag que lo controle."""
        cliente = ClienteManager()
        cerradas = []
        cliente._http.close = lambda: cerradas.append(True)
        cliente.cerrar()
        cliente.cerrar()
        self.assertEqual(cerradas, [True, True])

    def test_cerrar_no_cierra_lo_que_no_es_suyo(self):
        """El núcleo inyecta su sesión y la usa para media vida más: cerrarla sería
        apagar al vecino. La parada solo aplica al cliente que es dueño de la suya."""
        doble = DobleSesion()
        crear_cliente_manager(session=doble).cerrar()
        self.assertFalse(doble.cerrada)


if __name__ == "__main__":
    unittest.main()
