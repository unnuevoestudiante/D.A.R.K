"""R4: el contrato del Manager/Task Manager, contra la verdad medida.

La Fase A no movió ni una llamada: describió. Este archivo vigila dos cosas:

  * que la descripción siga siendo verdad —las 14 rutas del cliente, los sitios de
    llamada, las copias de la URL, las formas medidas de `/status`, `/tasks` y sus
    pasos—;
  * que los defectos que la Fase D cerró no se reabran, y que los dos que dejó abiertos
    (el `resume` por id y los enteros que vuelven como cadena) sigan escritos como hechos
    del código de hoy, no como una opinión.

Las 36 llamadas medidas en la Fase A ya no están repartidas en dos familias: desde la
**Fase C1** los 14 sitios de broker, código y tareas y desde la **Fase C2** los 19
vivos del núcleo hablan con el cliente, y los 3 que faltan morían dentro de cuatro
helpers que la C2 borró. Lo que queda vigilado aquí es el otro lado del balance: **no
queda ningún sitio crudo**, nadie copia la URL desde la C2, y las rutas que pueden
pedirse son exactamente las declaradas. El pin de la Fase C2 fallará el día que alguien
vuelva a escribir `requests.get` contra un puerto local.

El contrato ya no lo conocen solo el cliente: lo conocen sus cuatro consumidores y la
fábrica de especialistas. Las barreras de quién nombra la clase y de quién puede
construir el cliente viven en `tests/test_cliente_manager.py` y
`tests/test_consumidores_manager.py`.

Ref: contratos/manager.py, nucleo/dark_nucleo.py, especialistas/especialista_tareas.py,
especialistas/especialista_codigo.py, herramientas/internas/model_broker.py,
proveedores/manager/cliente.py.
"""
import ast
import pathlib
import queue
import re
import sys
import threading
import time
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.manager import (  # noqa: E402
    CAMPOS_ESTADO_RECURSOS,
    CAMPOS_PASO,
    CAMPOS_TAREA,
    ESTADOS_ABORTADAS,
    ESTADOS_TERMINADAS,
    ESTADOS_VIVAS,
    MANAGER,
    RUTAS_MANAGER,
    RUTAS_TAREAS,
    SITIOS_DE_LA_URL,
    TASK_MANAGER,
    EstadoRecursos,
    PasoTarea,
    PuertoClienteManager,
    PuertoRecursos,
    PuertoTaskManager,
    Tarea,
    es_abortada,
    es_terminada,
    es_viva,
    normalizar_estado,
)

NUCLEO_REL = "nucleo/dark_nucleo.py"
TAREAS_REL = "especialistas/especialista_tareas.py"
CODIGO_REL = "especialistas/especialista_codigo.py"
BROKER_REL = "herramientas/internas/model_broker.py"
CLIENTE_REL = "proveedores/manager/cliente.py"
#: Los cuatro consumidores, todos con sus llamadas ya dentro del cliente: la lista de
#: sitios crudos se vació con la Fase C2.
CONSUMIDORES = (NUCLEO_REL, TAREAS_REL, CODIGO_REL, BROKER_REL)
#: Donde hoy se declara una `requests.Session()` (defecto 5: cinco declaraciones, tres
#: de ellas solo como respaldo cuando nadie inyecta la sesión del Núcleo).
SESIONES = (NUCLEO_REL, TAREAS_REL, CODIGO_REL, BROKER_REL,
            "especialistas/especialista_comunicacion.py")

# ---- Las tres respuestas medidas el 25-oct contra los servidores vivos (solo GET).
STATUS_MEDIDO = {
    "ramDisponibleMB": 4889, "ollamaDisponible": True, "modelosActivos": [],
    "ramUsadaPorModelosMB": 0, "presupuestoTotalMB": 8837,
    "presupuestoRestanteMB": 8837, "cpuUsoPct": 15.1, "cpuTempC": None,
}
PASO_MEDIDO = {
    "id": "paso-1", "descripcion": "Investigar biografia de Einstein",
    "completado": True, "completadoEn": "2026-09-18T23:51:19.8227695Z",
    "resultado": "Biografia investigada", "error": None, "intentos": 1,
}
TAREA_MEDIDA = {
    "id": "5e784bfd-84b7-4e5c-aad4-4631c6c46f2e",
    "descripcion": "Biografia interactiva de Albert Einstein en HTML5 + CSS",
    "estado": "Cancelada", "prioridad": "Alta", "moduloAsignado": "Nucleo",
    "fechaCreacion": "2026-09-18T23:51:17.1606005Z",
    "fechaUltimaActualizacion": "2026-09-19T18:01:15.4097876Z",
    "fechaCompletacion": None,
    "pasos": [dict(PASO_MEDIDO, completado=(i < 2), id=f"paso-{i+1}")
              for i in range(5)],
    "pasoActualId": None, "dependencias": [], "resultadoFinal": None,
    "errores": [], "snapshotInicial": {"a": 1}, "snapshotActual": {"a": 1},
    "metadata": {}, "snapshotsParaRollback": [],
}

_HUECO = "{*}"
_VERBOS = ("get", "post", "put", "delete")

_ARBOLES = {}


def _arbol(rel):
    if rel not in _ARBOLES:
        _ARBOLES[rel] = ast.parse((DARK_PYTHON / rel).read_text(encoding="utf-8"))
    return _ARBOLES[rel]


def _fuente(rel):
    return (DARK_PYTHON / rel).read_text(encoding="utf-8")


def _clase(rel, nombre):
    for nodo in ast.walk(_arbol(rel)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"clase {nombre} no encontrada en {rel}")


def _func(rel, clase, nombre):
    for nodo in _clase(rel, clase).body:
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"{clase}.{nombre} no existe en {rel}")


def _literales_de(nodo):
    return {n.value for n in ast.walk(nodo)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _nombre_base(nodo):
    """Texto de la variable que abre un f-string de URL, si lo es. La primera pieza
    de un JoinedStr es un FormattedValue, no un Name."""
    if isinstance(nodo, ast.FormattedValue):
        nodo = nodo.value
    if isinstance(nodo, ast.Name):
        return nodo.id
    if isinstance(nodo, ast.Attribute):
        return nodo.attr
    return ""


def _plantilla(unido):
    """`("/tasks/{*}/cancel")` a partir de un f-string cuya primera pieza es la URL
    base. None si la cadena no arranca en una variable de base."""
    if not isinstance(unido, ast.JoinedStr) or not unido.values:
        return None
    base = _nombre_base(unido.values[0])
    if not (base.endswith("_URL") or base.endswith("_url")):
        return None
    salida = []
    for valor in unido.values[1:]:
        if isinstance(valor, ast.Constant) and isinstance(valor.value, str):
            salida.append(valor.value)
        elif isinstance(valor, (ast.FormattedValue, ast.JoinedStr)):
            salida.append(_HUECO)
        else:
            return None
    return "".join(salida), base


def _llamadas_a_los_managers():
    """Cada HTTP real que producción hace **a mano** a los dos servidores:
    [(archivo, línea, verbo, plantilla, base_es_de_tareas)]. Desde la Fase C1 los
    migrados ya no aparecen aquí: salen por `_plantillas_del_cliente()`."""
    salida = []
    for rel in CONSUMIDORES:
        for nodo in ast.walk(_arbol(rel)):
            if not isinstance(nodo, ast.Call):
                continue
            f = nodo.func
            if not (isinstance(f, ast.Attribute) and f.attr in _VERBOS):
                continue
            if not nodo.args:
                continue
            plantilla = _plantilla(nodo.args[0])
            if plantilla is None:
                continue
            ruta, base = plantilla
            salida.append((rel, nodo.lineno, f.attr.upper(), ruta,
                           "TASK" in base.upper()))
    return salida


#: Las tres salidas del cliente. `_leer` es siempre GET; en las otras dos el verbo es
#: el primer argumento y la plantilla el segundo.
_SALIDAS_DEL_CLIENTE = {"_leer": 0, "_pedir": 1, "_escribir": 1}


def _plantillas_del_cliente():
    """Las rutas que pide `proveedores/manager/cliente.py`, medidas en su AST:
    [(verbo, plantilla)]. Es la otra mitad del inventario: desde la C1 hay rutas —la
    `DELETE /tasks/{tarea_id}` o el `/resume`— que solo se llaman a través del cliente,
    y declararlas sin medirlas las convertiría en invento."""
    salida = []
    for nodo in ast.walk(_arbol(CLIENTE_REL)):
        if not isinstance(nodo, ast.Call):
            continue
        if not (isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr in _SALIDAS_DEL_CLIENTE):
            continue
        pos = _SALIDAS_DEL_CLIENTE[nodo.func.attr]
        if len(nodo.args) <= pos:
            continue
        plantilla = nodo.args[pos]
        if not (isinstance(plantilla, ast.Constant)
                and isinstance(plantilla.value, str)):
            continue
        if nodo.func.attr == "_leer":
            verbo = "GET"
        else:
            verbo_nodo = nodo.args[0]
            if not (isinstance(verbo_nodo, ast.Constant)
                    and isinstance(verbo_nodo.value, str)):
                continue
            verbo = verbo_nodo.value
        salida.append((verbo, plantilla.value))
    return salida


def _canonica(ruta):
    return re.sub(r"\{[^}]*\}", _HUECO, ruta)


def _rutas_que_se_piden():
    """Las (verbo, ruta canónica) que alguien pide hoy, por cualquiera de las dos
    familias de sitios."""
    return ({(v, _canonica(r)) for _, _, v, r, _ in _llamadas_a_los_managers()}
            | {(v, _canonica(r)) for v, r in _plantillas_del_cliente()})


def _declaradas():
    return {(v, _canonica(r)) for r, v, _ in RUTAS_MANAGER} | \
           {(v, _canonica(r)) for r, v, _ in RUTAS_TAREAS}


class TestContratoSoloStdlib(unittest.TestCase):
    def test_el_contrato_solo_importa_stdlib(self):
        importados = set()
        for nodo in ast.walk(_arbol("contratos/manager.py")):
            if isinstance(nodo, ast.Import):
                importados.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module.split(".")[0])
        self.assertLessEqual(importados,
                             {"__future__", "dataclasses", "typing", "unicodedata",
                              "config_runtime"},
                             "un cliente del Manager que importa requests ya no es "
                             "describible sin red: la Fase B es la que lo trae")

    def test_el_helper_de_runtime_sigue_siendo_solo_stdlib(self):
        importados = set()
        for nodo in ast.walk(_arbol("config_runtime.py")):
            if isinstance(nodo, ast.Import):
                importados.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom) and nodo.module:
                importados.add(nodo.module.split(".")[0])
        self.assertLessEqual(importados,
                             {"__future__", "json", "os", "functools", "pathlib",
                              "typing", "urllib"})

    def test_no_nombra_a_ningun_modulo_del_proyecto(self):
        for paquete in ("herramientas", "especialistas", "nucleo", "proveedores",
                        "voz", "modulos", "cerebro"):
            self.assertNotIn(f"import {paquete}", _fuente("contratos/manager.py"),
                             f"el contrato de R4 se acopla a {paquete}")

    def test_los_dos_servidores_estan_declados_una_sola_vez(self):
        self.assertEqual(MANAGER, "http://localhost:5050")
        self.assertEqual(TASK_MANAGER, "http://localhost:5051")


class TestInventarioDeRutas(unittest.TestCase):
    def test_catorce_rutas_tres_del_manager_y_once_del_task_manager(self):
        self.assertEqual(len(RUTAS_MANAGER), 3)
        self.assertEqual(len(RUTAS_TAREAS), 11)
        self.assertEqual(len(_declaradas()), 14)

    def test_el_contrato_no_inventa_rutas_que_nadie_llama(self):
        """Set equality sobre las dos familias: ni una ruta declarada sin llamada real,
        ni una llamada real sin declarar —en el núcleo o en el cliente."""
        self.assertEqual(_rutas_que_se_piden(), _declaradas(),
                         "las rutas declaradas y las que se piden en producción "
                         "dejaron de ser el mismo conjunto")

    def test_cero_sitios_crudos_todos_migrados(self):
        """El inventario cerrado por la Fase C2. La Fase A midió 36 sitios a mano: 14 se
        los llevó la C1, **3 morían dentro de los cuatro helpers de sub-pasos que nadie
        llamaba** (se borraron con ellos) y los 19 vivos del núcleo pasan hoy por el
        cliente. Si este número sube, alguien volvió a escribir HTTP a mano."""
        esperado = {NUCLEO_REL: 0, TAREAS_REL: 0, CODIGO_REL: 0, BROKER_REL: 0}
        contador = {rel: 0 for rel in esperado}
        for rel, _, _, _, _ in _llamadas_a_los_managers():
            contador[rel] = contador.get(rel, 0) + 1
        self.assertEqual(contador, esperado,
                         "la cuenta de sitios crudos cambió: actualiza el contrato y la "
                         "Fase C, en ese orden")
        self.assertEqual(len(_llamadas_a_los_managers()), 0)

    def test_ningun_consumidor_vuelve_a_tocar_requests(self):
        """Barrera de la C1 y de la C2: un solo `self._http.get(f\"{MANAGER_URL}…\")`
        suelto en cualquiera de los cuatro reabriría el inventario sin que ningún test de
        rutas lo vea, porque la ruta seguiría declarada."""
        for rel in CONSUMIDORES:
            self.assertEqual([x for x in _llamadas_a_los_managers() if x[0] == rel], [],
                             f"{rel} volvió a pedir HTTP a mano")

    def test_los_verbos_usados_son_get_post_y_delete(self):
        self.assertEqual({v for v, _ in _rutas_que_se_piden()},
                         {"GET", "POST", "DELETE"})

    def test_cada_ruta_declara_quien_la_llama(self):
        """Sin el `quién` no hay Fase C posible: la tabla es el mapa de migración."""
        for tabla in (RUTAS_MANAGER, RUTAS_TAREAS):
            for ruta, verbo, quien in tabla:
                self.assertTrue(quien.strip(), f"{verbo} {ruta} sin dueño")
                self.assertIn("timeout", quien.lower(),
                              f"{verbo} {ruta} no declara su timeout medido")

    def test_las_llamadas_apuntan_a_la_base_correcta(self):
        """`/status` es del Manager y `/tasks` del Task Manager: mezclar bases es
        pedir una ruta que no existe."""
        declaradas_tareas = {_canonica(r) for r, v, _ in RUTAS_TAREAS}
        for _, linea, _, ruta, es_tareas in _llamadas_a_los_managers():
            self.assertEqual(es_tareas, _canonica(ruta) in declaradas_tareas,
                             f"línea {linea}: {ruta} servida por la base equivocada")

    def test_la_url_no_la_copia_nadie_desde_la_C2(self):
        """Eran seis; la C1 se llevó cuatro y la C2 las dos del núcleo.
        `SITIOS_DE_LA_URL` está vacío y la fábrica es la dueña de la base: este pin ya no
        cuenta copias, **prohíbe** que vuelvan."""
        self.assertEqual(SITIOS_DE_LA_URL, ())
        for rel in CONSUMIDORES:
            self.assertNotIn("DARK_MANAGER_URL", _fuente(rel))
            self.assertNotIn("DARK_TASK_MANAGER_URL", _fuente(rel))
            for linea in _fuente(rel).splitlines():
                if re.match(r"\s*(MANAGER_URL|TASK_MANAGER_URL)\s*=", linea):
                    self.fail(f"{rel} volvió a declararse la URL base: {linea!r}")
            self.assertNotIn("localhost:505", _fuente(rel),
                             f"{rel} escribe un puerto del Manager a mano")

    def test_los_cuatro_consumidores_borraron_sus_constantes_de_URL(self):
        for rel in CONSUMIDORES:
            for constante in ("MANAGER_URL", "TASK_MANAGER_URL"):
                self.assertNotIn(constante, _fuente(rel),
                                 f"{rel} conserva {constante}: o escribe HTTP a mano o "
                                 "es un muerto que hay que borrar")


class TestFormasMedidas(unittest.TestCase):
    def test_el_status_tiene_ocho_claves_y_dos_cifras_distintas(self):
        self.assertEqual(len(CAMPOS_ESTADO_RECURSOS), 8)
        self.assertEqual(set(STATUS_MEDIDO), set(CAMPOS_ESTADO_RECURSOS))
        rec = EstadoRecursos.desde_json(STATUS_MEDIDO)
        self.assertEqual(rec.ram_disponible_mb, 4889)
        self.assertEqual(rec.presupuesto_restante_mb, 8837)
        self.assertNotEqual(rec.ram_disponible_mb, rec.presupuesto_restante_mb,
                            "disponible y presupuesto volvieron a ser el mismo número")
        self.assertFalse(rec.residencia)

    def test_estado_recursos_no_reclama_lo_que_no_llega(self):
        vacio = EstadoRecursos.desde_json(None)
        self.assertEqual((vacio.ram_disponible_mb, vacio.presupuesto_total_mb), (0, 0))
        self.assertFalse(vacio.ollama_disponible)
        self.assertIsNone(vacio.cpu_temp_c)
        self.assertEqual(EstadoRecursos.desde_json({}).modelos_activos, ())

    def test_cpu_temp_c_puede_ser_null(self):
        self.assertIsNone(EstadoRecursos.desde_json(STATUS_MEDIDO).cpu_temp_c)
        self.assertEqual(EstadoRecursos.desde_json(
            dict(STATUS_MEDIDO, cpuTempC=61.0)).cpu_temp_c, 61.0)

    def test_tarea_tiene_diecisiete_claves_y_el_cliente_no_lee_los_snapshots(self):
        self.assertEqual(len(CAMPOS_TAREA), 17)
        self.assertEqual(set(TAREA_MEDIDA), set(CAMPOS_TAREA))
        t = Tarea.desde_json(TAREA_MEDIDA)
        for ignorado in ("snapshotInicial", "snapshotActual", "snapshotsParaRollback",
                         "metadata", "dependencias", "fechaUltimaActualizacion"):
            self.assertNotIn(ignorado, {f.name for f in t.__dataclass_fields__.values()},
                             f"el contrato arrastra {ignorado}: nadie en Python lo usa")

    def test_progreso_y_reanudable_con_la_tarea_real_de_hoy(self):
        t = Tarea.desde_json(TAREA_MEDIDA)
        self.assertEqual(t.progreso, (2, 5))
        self.assertEqual(t.estado_canonico, "cancelada")
        self.assertFalse(t.viva)
        self.assertFalse(t.reanudable,
                         "una Cancelada con pasos a medias NO es reanudable: el "
                         "defecto 2 es exactamente confundir estas dos cosas")
        viva = Tarea.desde_json(dict(TAREA_MEDIDA, estado="Pendiente"))
        self.assertTrue(viva.reanudable)
        terminada = Tarea.desde_json(dict(
            TAREA_MEDIDA, estado="Completada",
            pasos=[dict(p, completado=True) for p in TAREA_MEDIDA["pasos"]]))
        self.assertFalse(terminada.reanudable)

    def test_los_pasos_tienen_siete_claves(self):
        self.assertEqual(len(CAMPOS_PASO), 7)
        self.assertEqual(set(PASO_MEDIDO), set(CAMPOS_PASO))
        p = PasoTarea.desde_json(PASO_MEDIDO)
        self.assertEqual((p.id, p.completado, p.intentos), ("paso-1", True, 1))
        self.assertIsNone(p.error)

    def test_tasks_es_un_dict_keyed_por_id_y_interrupted_es_una_lista(self):
        """El consumidor que haga `.values()` sin saber esto se cae con 200 OK."""
        tareas = {TAREA_MEDIDA["id"]: TAREA_MEDIDA}
        tuplecita = Tarea.desde_lista_json(tareas.values())
        self.assertEqual(len(tuplecita), 1)
        self.assertIsInstance(tuplecita, tuple)
        self.assertEqual(tuplecita[0].id, TAREA_MEDIDA["id"])
        self.assertEqual(Tarea.desde_lista_json(None), ())

    def test_lo_que_se_envia_no_vuelve_como_se_envio(self):
        """Defecto 6: `crear` manda enteros y `/tasks` devuelve cadenas. Desde la C2 el
        cuerpo se arma en el cliente, así que el literal vive allí; la asimetría del
        servidor no cambió: lo que se manda como `2` vuelve como `"Alta"`."""
        cliente = _func(CLIENTE_REL, "ClienteManager", "crear")
        literales = _literales_de(cliente)
        self.assertIn("prioridad", literales)
        self.assertIn("modulo", literales)
        self.assertNotIn("moduloAsignado", literales,
                         "el cliente ya traduce: el contrato puede dejar de prometer "
                         "la frontera")
        t = Tarea.desde_json(TAREA_MEDIDA)
        self.assertIsInstance(t.prioridad, str)
        self.assertIsInstance(t.modulo_asignado, str)


class TestVocabularioDeEstados(unittest.TestCase):
    def test_normalizar_estado_unifica_los_estilos(self):
        for crudo, canonico in (("Cancelada", "cancelada"), ("COMPLETADA", "completada"),
                                ("En Progreso", "enprogreso"),
                                ("Requiere Confirmación", "requiereconfirmacion"),
                                ("  Fallida  ", "fallida"), (None, ""), (2, "2")):
            self.assertEqual(normalizar_estado(crudo), canonico, crudo)

    def test_los_tres_grupos_no_se_pisan(self):
        grupos = [set(ESTADOS_TERMINADAS), set(ESTADOS_ABORTADAS), set(ESTADOS_VIVAS)]
        self.assertEqual(sum(len(g) for g in grupos), 7 + 2 + 7)
        self.assertIn("ejecutandose", ESTADOS_VIVAS,
                      "la Fase B añadió el estado que comparaba `tool_estado_tareas`: "
                      "si desaparece, una tarea activa vuelve a no ser ni viva ni "
                      "terminada para el contrato")
        for i in range(3):
            for j in range(i + 1, 3):
                self.assertEqual(grupos[i] & grupos[j], set(),
                                 f"el estado {grupos[i] & grupos[j]} está en dos "
                                 "grupos: `es_viva` y `es_terminada` darían True")

    def test_normalizar_no_inventa_traducciones(self):
        """Un estado nuevo del servidor sale normalizado, no convertido."""
        self.assertEqual(normalizar_estado("Reintentando"), "reintentando")
        self.assertFalse(es_viva("Reintentando"))
        self.assertFalse(es_terminada("Reintentando"))
        self.assertFalse(es_abortada("Reintentando"))

    def test_el_filtro_de_reanudar_del_nucleo_usa_la_palabra_del_contrato(self):
        """Cerrado por la Fase D (defecto 7): el latido escribía `pendiente`, `pausada` y
        `enprogreso` a mano. Hoy pide `t.viva` —el único predicado del contrato— y la
        única palabra que conserva es la excepción deliberada: `requiereconfirmacion` es
        viva y no se reencola, se pregunta."""
        filtro = _func(NUCLEO_REL, "DarkNucleo", "_retomar_tareas_pendientes")
        buscados = _literales_de(filtro) & set(ESTADOS_VIVAS)
        self.assertEqual(buscados, {"requiereconfirmacion"},
                         f"el metrónomo volvió a escribir estados a mano: "
                         f"{sorted(buscados)}")
        self.assertIn("viva", {a.attr for a in ast.walk(filtro)
                               if isinstance(a, ast.Attribute)},
                      "el filtro dejó de usar `Tarea.viva`: sin el predicado del "
                      "contrato un estado nuevo del servidor se queda fuera en silencio")

    def test_el_menu_oculta_terminadas_y_abortadas(self):
        """El oculto del menú eran nueve cadenas escritas a mano (dos idiomas, singular y
        plural). Desde la C2 es la misma decisión con los dos predicados del contrato, así
        que el vocabulario vive en un sitio; si alguien vuelve a escribir los estados aquí,
        este pin tiene que fallar."""
        ocultar = _func(NUCLEO_REL, "DarkNucleo", "_filtrar_tareas_activas")
        llamadas = {n.func.id for n in ast.walk(ocultar)
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        self.assertTrue({"es_terminada", "es_abortada"} <= llamadas,
                        "el menú dejó de usar los predicados del contrato")
        estados = _literales_de(ocultar) & (set(ESTADOS_TERMINADAS)
                                            | set(ESTADOS_ABORTADAS))
        self.assertEqual(estados, set(),
                         f"el menú volvió a escribir estados a mano: {sorted(estados)}")

    def test_interrumpida_no_es_un_estado(self):
        """Es un filtro por pasos a medias; mezclarlo con los vocabularios fue el
        defecto 2."""
        for grupo in (ESTADOS_TERMINADAS, ESTADOS_ABORTADAS, ESTADOS_VIVAS):
            for estado in grupo:
                self.assertNotIn("interrupt", estado)
        self.assertTrue(any("interrupted" in r for r, v, _ in RUTAS_TAREAS))


class TestPuertos(unittest.TestCase):
    def _metodos(self, puerto):
        return {n for n in dir(puerto) if not n.startswith("_")}

    def test_puerto_recursos(self):
        self.assertEqual(self._metodos(PuertoRecursos),
                         {"estado", "esta_vivo", "cargar_modelo", "descargar_modelo"})

    def test_puerto_task_manager(self):
        """Once métodos. No están `obtener` ni `añadir_pasos`, que el servidor sí sirve:
        los pedían solo los cuatro helpers de sub-pasos que la C2 borró, y un puerto con
        un método sin llamador es una invitación a inventarle uno."""
        self.assertEqual(self._metodos(PuertoTaskManager), {
            "listar", "interrumpidas", "crear", "iniciar", "completar_paso",
            "fallar_paso", "completar", "cancelar", "pausar", "reanudar", "eliminar"})

    def test_el_puerto_completo_es_la_reunion_mas_cerrar(self):
        self.assertEqual(self._metodos(PuertoClienteManager),
                         self._metodos(PuertoRecursos)
                         | self._metodos(PuertoTaskManager) | {"cerrar"})

    def test_el_puerto_de_tareas_no_se_confunde_con_el_del_especialista(self):
        """`PuertoTareas` ya existe en `contratos/especialista.py` y es otra cosa: el
        planificador, con tres métodos. Si R4 reutiliza el nombre, la fábrica de R3 y
        la de R4 prometen interfaces distintas con la misma etiqueta."""
        from contratos.especialista import PuertoTareas as PuertoDelEspecialista
        del_especialista = self._metodos(PuertoDelEspecialista)
        self.assertEqual(del_especialista,
                         {"obtener_tareas", "crear_tarea", "iniciar_tarea"})
        self.assertEqual(self._metodos(PuertoTaskManager) & del_especialista, set(),
                         "los dos puertos comparten un nombre de método: hay que "
                         "decidir cuál manda")
        # Las tres operaciones del especialista sí están cubiertas aquí, con otros
        # nombres: el cliente no añade capacidades, cambia el vocabulario.
        self.assertTrue({"listar", "crear", "iniciar"} <= set(
            self._metodos(PuertoTaskManager)))

    def test_los_tres_metodos_de_escritura_de_una_tarea_no_estan_en_recursos(self):
        """El puerto de recursos no puede tocar tareas: es la frontera que hoy no
        existe (un `broker` que llama a `/load` y un núcleo que llama a `/load` son
        dos dueños del mismo presupuesto)."""
        self.assertEqual(self._metodos(PuertoRecursos)
                         & self._metodos(PuertoTaskManager), set())


class TestDefectosEscritos(unittest.TestCase):
    """Pines del código de HOY. Los defectos 1 (mitad latido), 2, 3 y 7 ya están
    cerrados y sus pines dicen por qué no pueden volver; los que siguen abiertos son el
    `resume` por id y los enteros que vuelven como cadena."""

    def test_el_metronomo_es_un_intento_por_concesion_real(self):
        """Cerrado por la Fase D (defecto 1). El pin anterior exigía el `while True` con
        `wait()` sobre `_acceso_concedido`; ahora exige lo contrario, porque ese era el
        latido: el gate setea el Event en cada callback, así que el bucle pedía `/tasks`
        entero (41.862 bytes) cada 10 s hasta el fin de la sesión. La señal buena es el
        borde bloqueado→concedido, que es lo que llama a `_programar_retomar_tareas`."""
        import nucleo.dark_nucleo as dn
        self.assertTrue(dn.AUTO_RETOMAR_TAREAS)
        #: 10 s siguen ahí, pero ya no como periodo: son el asentado de la concesión
        #: para no hablar por encima del saludo de bienvenida.
        self.assertEqual(dn.AUTO_RETOMAR_DELAY_SEGUNDOS, 10)
        programa = _func(NUCLEO_REL, "DarkNucleo", "_programar_retomar_tareas")
        self.assertFalse(any(isinstance(n, ast.While) for n in ast.walk(programa)),
                         "`_programar_retomar_tareas` volvió a traer el bucle: el "
                         "latido de 10 s reabierto")
        señales = {(a.attr, getattr(a.value, "attr", getattr(a.value, "id", "")))
                   for a in ast.walk(programa) if isinstance(a, ast.Attribute)}
        self.assertIn(("set", "_retomar_solicitado"), señales,
                      "la concesión ya no deja señal: el hilo no tiene cómo enterarse")
        self.assertNotIn(("wait", "_acceso_concedido"), señales,
                         "`_programar_retomar_tareas` espera el Event del acceso: con "
                         "el acceso concedido el wait no duerme y vuelve el latido")
        bucle = _func(NUCLEO_REL, "DarkNucleo", "_bucle_retomar_tareas")
        despierta = [n for n in ast.walk(bucle) if isinstance(n, ast.Call)
                     and getattr(n.func, "attr", "") == "wait"
                     and getattr(n.func.value, "attr", "") == "_retomar_solicitado"]
        self.assertTrue(despierta,
                        "el hilo del metrónomo ya no duerme en la señal de concesión")
        #: El anuncio del latido ("DEBUG - auto-retomando tareas pendientes") se
        #: imprimía antes de filtrar: salía aunque no hubiera nada que reanudar. Hoy no
        #: existe; lo que queda vive después del filtro y lo vigila
        #: `TestElMetronomoNoHablaSolo.test_sin_tareas_no_se_imprime_nada`.
        self.assertNotIn("auto-retomando", _fuente(NUCLEO_REL),
                         "el hilo volvió a anunciar antes de filtrar")

    def test_el_metronomo_no_reencola_la_misma_tarea_dos_veces(self):
        """Cada latido cancelaba la tarea y creaba otra **con id nuevo**, así que la
        lista de pendientes nunca se agotaba: "Tengo 3 tareas listas para ejecutar" y
        "Encolé 3 tareas" cada 10 s, con tres tareas de fondo peleando por el lock del
        LLM y el input del teléfono bloqueado. El id no puede ser la clave; la
        descripción sí, y la marca tiene que ir **antes** de ejecutar: el camino sin
        pasos (`continue`) también es un intento de esta sesión."""
        retomar = _func(NUCLEO_REL, "DarkNucleo", "_retomar_tareas_pendientes")
        init = _func(NUCLEO_REL, "DarkNucleo", "__init__")
        for clave, nodo in (("__init__", init), ("_retomar", retomar)):
            self.assertIn("_tareas_ya_reanudadas",
                          {a.attr for a in ast.walk(nodo) if isinstance(a, ast.Attribute)}
                          | {a.id for a in ast.walk(nodo) if isinstance(a, ast.Name)},
                          f"{clave} ya no mira el historial de reanudadas: el ciclo "
                          "infinito vuelve")
        self.assertIn("_clave_reanudada",
                      {a.attr for a in ast.walk(retomar) if isinstance(a, ast.Attribute)},
                      "el filtro dejó de usar la clave estable: con id nuevo no filtra "
                      "nada")
        marca = [n.lineno for n in ast.walk(retomar) if isinstance(n, ast.Call)
                 and getattr(n.func, "attr", "") == "add"]
        ejecucion = [n.lineno for n in ast.walk(retomar) if isinstance(n, ast.Call)
                     and getattr(n.func, "attr", "") == "_ejecutar_tareas"]
        self.assertTrue(marca and ejecucion,
                        "el metrónomo dejó de marcar o dejó de ejecutar: revisar el pin")
        self.assertLess(max(marca), min(ejecucion),
                        "la tarea se marca después de ejecutarla: el camino sin pasos "
                        "vuelve a hablar cada pasada")
        clave = _func(NUCLEO_REL, "DarkNucleo", "_clave_reanudada")
        self.assertIn("descripcion",
                      {a.attr for a in ast.walk(clave) if isinstance(a, ast.Attribute)},
                      "la clave dejó de ser la descripción")

    def test_el_metronomo_no_repregunta_una_confirmacion_viva(self):
        """El almacén compartido evita volver a preguntar cada 10 s."""
        retomar = _func(NUCLEO_REL, "DarkNucleo", "_retomar_tareas_pendientes")
        atributos = {a.attr for a in ast.walk(retomar) if isinstance(a, ast.Attribute)}
        self.assertIn("confirmaciones", atributos,
                      "el metrónomo dejó de consultar el almacén compartido")
        self.assertIn("hay_pendiente", atributos,
                      "el metrónomo volvió a pedir confirmación sin mirar si ya hay "
                      "una pendiente")
        preguntar = [n for n in ast.walk(retomar) if isinstance(n, ast.Call)
                     and getattr(n.func, "attr", "") == "_pedir_confirmacion_tareas"]
        self.assertEqual(len(preguntar), 1,
                         "más de una llamada a pedir confirmación en la pasada")

    def test_el_nucleo_sigue_sin_usa_resume(self):
        """De los dos mitades del defecto 1, la Fase D cerró el latido y deja viva esta:
        `_ejecutar_tareas` sigue cancelando y creando con id nuevo en vez de llamar a
        `/tasks/{id}/resume`. Moverla requiere un POST real contra el Manager y cambia
        cómo se ejecutan las tareas, así que es línea del usuario, no del refactor. La
        ruta sí la llama producción: la usa el especialista a través del cliente."""
        self.assertNotIn("/resume", _fuente(NUCLEO_REL),
                         "el núcleo ya reanuda por la ruta buena: defecto 1 cerrado del "
                         "todo, hay que reescribir el contrato")
        self.assertNotIn("/resume", _fuente(TAREAS_REL),
                         "el especialista volvió a escribir la ruta: la Fase C1 se "
                         "deshizo a medias")
        self.assertIn("/tasks/{tarea_id}/resume", _fuente(CLIENTE_REL),
                      "nadie pide ya el `/resume`: la ruta declarada es un invento")

    def test_el_resultado_de_interrumpidas_tiene_dueno(self):
        """Cerrado por la Fase D (defecto 2). Antes el método se arrancaba como hilo y
        su `return` no lo leía nadie; seguir siéndolo es inofensivo mientras el valor se
        consuma **dentro**: aquí se filtra por `reanudable` (dos de las tareas del 25-oct
        estaban `Cancelada`, y reanimar una cancelada era el bug) y lo que queda reanudable
        se anuncia por la cola de avisos. Un `print` de consola no lo oye nadie."""
        verificar = _func(NUCLEO_REL, "DarkNucleo", "_verificar_tareas_interrumpidas")
        attrs = {a.attr for a in ast.walk(verificar) if isinstance(a, ast.Attribute)}
        self.assertIn("reanudable", attrs,
                      "el escáner de arrancada volvió a tomar `/tasks/interrupted` tal "
                      "cual: reanima canceladas")
        self.assertIn("_avisos_pendientes", attrs,
                      "el resultado otra vez se queda en un print que nadie lee")
        #: `None` (no contestó) y `()` (no hay) siguen siendo distintos: el aviso solo
        #: puede salir de una lista leída.
        self.assertIn("is None", ast.unparse(verificar),
                      "el escáner confundió el silencio con la ausencia de tareas")

    def test_los_pollers_del_menu_tienen_parada(self):
        """Cerrado por la Fase D (defecto 3). `_menu_stop_polling` se creaba y nunca se
        setaba: los dos hilos eran inmortales y no había forma de apagarlos. Hoy hay un
        método que lo setea, los dos hilos tienen nombre para poder ser esperados, y el
        método está registrado en el arranque."""
        fuente = _fuente(NUCLEO_REL)
        self.assertIn("self._menu_stop_polling.set()", fuente,
                      "`_menu_stop_polling` dejó de setearse: los pollers vuelven a ser "
                      "inmortales")
        parada = _func(NUCLEO_REL, "DarkNucleo", "_detener_pollers_del_menu")
        self.assertIn("atexit.register(self._detener_pollers_del_menu)", fuente,
                      "la parada existe pero nadie la llama al apagar")
        for nombre in ("poll-recursos", "poll-tareas"):
            self.assertIn(f'name="{nombre}"', fuente,
                          f"un poller dejó de llamarse {nombre}: no se puede esperar por "
                          "él ni distinguirlo en un volcado de hilos")

    def test_cinco_sesiones_para_los_mismos_dos_puertos(self):
        total = sum(_fuente(rel).count("requests.Session()") for rel in SESIONES)
        self.assertEqual(total, 5,
                         "el número de sesiones cambió: el contrato dice otra cosa")

    def test_el_contrato_ya_tiene_sus_cuatro_consumidores(self):
        """Barrera al revés que en la Fase B: allí el contrato solo lo conocía el
        cliente; desde la C1 lo conocen el cliente, la fábrica de especialistas y los
        tres consumidores migrados, **y todavía** el núcleo, que lo importó para cablear
        pero sigue pidiendo 22 rutas a mano. Cualquier módulo fuera de esta lista que
        nombre el contrato es un salto de la Fase C: o migra entero o no migra."""
        permitidos = {"contratos/manager.py", CLIENTE_REL,
                      "proveedores/manager/fabrica.py", NUCLEO_REL,
                      "especialistas/fabrica.py", TAREAS_REL, CODIGO_REL, BROKER_REL}
        senales = ("contratos.manager", "PuertoClienteManager", "PuertoTaskManager",
                   "EstadoRecursos", "ResultadoCarga")
        encontrados = set()
        for ruta in DARK_PYTHON.rglob("*.py"):
            if "__pycache__" in ruta.parts:
                continue
            rel = ruta.relative_to(DARK_PYTHON).as_posix()
            if rel in permitidos:
                continue
            if any(s in ruta.read_text(encoding="utf-8") for s in senales):
                encontrados.add(rel)
        self.assertEqual(encontrados, set(),
                         "el contrato de R4 tiene consumidores fuera de la Fase C: "
                         f"{sorted(encontrados)}")

    def test_los_cuatro_consumidores_construyen_su_cliente_por_la_fabrica(self):
        """Ningún consumidor escribe `ClienteManager`: la clase solo la nombra
        `proveedores/manager/fabrica.py`. El núcleo también la pide, y es correcto: es
        quien cablea, no quien la construye a mano."""
        for rel in CONSUMIDORES:
            fuente = _fuente(rel)
            self.assertIn("crear_cliente_manager", fuente,
                          f"{rel} ya no pide el cliente a la fábrica")
            self.assertNotIn("ClienteManager(", fuente.replace(
                "crear_cliente_manager(", ""),
                             f"{rel} construye la clase: la regla de la casa es la "
                             "fábrica")

    def test_cada_ruta_del_mapa_tiene_un_dueno_en_el_cliente(self):
        """El mapa cerrado por la Fase C2: cada ruta declarada la pide un método del
        cliente. Si una desaparece de las dos familias, el contrato conserva una ruta que
        nadie usa."""
        crudas = {(v, _canonica(r)) for _, _, v, r, _ in _llamadas_a_los_managers()}
        por_cliente = {(v, _canonica(r)) for v, r in _plantillas_del_cliente()}
        for ruta, verbo, _ in list(RUTAS_MANAGER) + list(RUTAS_TAREAS):
            clave = (verbo, _canonica(ruta))
            self.assertTrue(clave in crudas or clave in por_cliente,
                            f"{verbo} {ruta}: nadie la pide ya")


class TestElMetronomoNoHablaSolo(unittest.TestCase):
    """Conducta del metrónomo, no su sintaxis: estos tests son los que prueban que el
    ciclo que bloqueaba el input está cortado de verdad. Sobreviven a la Fase D porque
    no miran cómo está escrito el bucle, sino cuántas veces habla."""

    def _fake(self, tareas):
        """La pasada de verdad (`DarkNucleo._retomar_tareas_pendientes`) con el resto
        del núcleo de pega. `tareas` son dicts del alambre y entran como `Tarea`: desde
        la C2 el puerto devuelve datos normalizados, así que un dict aquí sería probar un
        consumidor que ya no existe."""
        import nucleo.dark_nucleo as dn

        class _Nucleo:
            _retomar_tareas_pendientes = dn.DarkNucleo._retomar_tareas_pendientes
            _clave_reanudada = staticmethod(dn.DarkNucleo._clave_reanudada)

            def __init__(self, datos):
                self.hablado = []
                self.encoladas = []
                self.pedidas = 0
                self.tareas = Tarea.desde_lista_json(datos)
                from nucleo.confirmacion import AlmacenConfirmacion
                self.confirmaciones = AlmacenConfirmacion()
                self._tareas_ya_reanudadas = set()

            def _obtener_tareas_actuales(self):
                return self.tareas

            def speak(self, texto):
                self.hablado.append(texto)

            def _ejecutar_tareas(self, nuevas):
                self.encoladas.append([t.id for t in nuevas])

            def _pedir_confirmacion_tareas(self, confirmar):
                self.pedidas += 1
                self.confirmaciones.solicitar(
                    ejecutar=lambda: None,
                    pregunta="¿Autorizas estas tareas?",
                    origen="tareas",
                )

        return _Nucleo(tareas)

    def _pasada(self, nucleo):
        """Una pasada del metrónomo con la consola capturada: el anuncio viejo se imprimía
        antes de filtrar, así que la prueba de que ya no está es no oírla."""
        import contextlib
        import io
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            nucleo._retomar_tareas_pendientes()
        return salida.getvalue()

    def test_sin_tareas_no_se_imprime_nada(self):
        """El día que el Task Manager contesta 0 tareas reanudables —que es como estaba
        el 25-oct por la tarde— la pasada anterior escribía su DEBUG y pedía `/tasks`
        entero cada 10 s hasta el fin de la sesión."""
        self.assertEqual(self._pasada(self._fake([])), "",
                         "una pasada sin nada que reanudar imprimió algo")

    def test_el_silencio_del_task_manager_no_es_una_tarea(self):
        """`None` (no contestó) se comporta como vacío, no como "reanuda todo": un fallo
        de red no puede ponerle una tarea nueva al usuario."""
        n = self._fake([])
        n._obtener_tareas_actuales = lambda: None
        self.assertEqual(self._pasada(n), "",
                         "el silencio del Task Manager habló o imprimió")
        self.assertEqual((n.hablado, n.encoladas, n.pedidas), ([], [], 0))

    def test_tres_pasadas_sobre_las_mismas_tareas_solo_encolan_una_vez(self):
        """La forma que tenía el bug: el paso falla, la tarea vuelve `Pendiente` con
        **id nuevo** y el latido la re-encola para siempre."""
        ciclo1 = [{"id": "a1", "descripcion": "informe sobre ventas",
                   "estado": "Pendiente"},
                  {"id": "a2", "descripcion": "informe sobre gastos",
                   "estado": "Pendiente"}]
        ciclo2 = [{"id": "b1", "descripcion": "informe sobre ventas",
                   "estado": "Pendiente"},
                  {"id": "b2", "descripcion": "informe sobre gastos",
                   "estado": "Pendiente"}]
        n = self._fake(ciclo1)
        self._pasada(n)
        n.tareas = Tarea.desde_lista_json(ciclo2)
        self._pasada(n)
        self._pasada(n)
        self.assertEqual([len(x) for x in n.encoladas], [2],
                         f"el metrónomo re-encola en pasadas siguientes: {n.encoladas}")
        self.assertEqual([h for h in n.hablado if h.startswith("Tengo")],
                         ["Tengo 2 tareas listas para ejecutar."])

    def test_una_confirmacion_pendiente_no_se_repregunta(self):
        tareas = [{"id": "c1", "descripcion": "borrar el log",
                   "estado": "RequiereConfirmacion"}]
        n = self._fake(tareas)
        for _ in range(3):
            self._pasada(n)
        self.assertEqual(n.pedidas, 1,
                         "pidió el sí o el no tres veces: el metrónomo habla por encima "
                         "del input")

    def test_la_clave_es_la_descripcion_no_el_id(self):
        """`_ejecutar_tareas` cancela y crea: el id cambia en cada pasada, la
        descripción no."""
        n = self._fake([])
        vieja = Tarea(id="a1", descripcion="Informe sobre  Ventas")
        nueva = Tarea(id="z9", descripcion="informe sobre ventas")
        self.assertEqual(n._clave_reanudada(vieja), n._clave_reanudada(nueva))
        self.assertEqual(n._clave_reanudada(Tarea(id="q7")), "id:q7")


class TestElMetronomoSoloCaminaCuandoLeConceden(unittest.TestCase):
    """Conducta del defecto 1 cerrado: el hilo existe para que una concesión lo llame
    una vez, no para preguntar cada 10 s hasta el fin de la sesión."""

    def _nucleo_de_pega(self, retardo=0.01):
        import nucleo.dark_nucleo as dn
        from unittest import mock

        class _Nucleo:
            _programar_retomar_tareas = dn.DarkNucleo._programar_retomar_tareas
            _bucle_retomar_tareas = dn.DarkNucleo._bucle_retomar_tareas
            _detener_metronomo = dn.DarkNucleo._detener_metronomo

            def __init__(self):
                self._retomar_hilo = None
                self._retomar_hilo_lock = threading.Lock()
                self._retomar_solicitado = threading.Event()
                self._retomar_parado = threading.Event()
                self._acceso_concedido = threading.Event()
                self.pasadas = []
                self._en_curso = 0
                self._en_curso_lock = threading.Lock()
                self.max_simultaneas = 0

            def _retomar_tareas_pendientes(self):
                #: La pasada de verdad tarda segundos (llama a `/tasks` y habla); esta
                #: también, para que simultaneidad estricta > 1 sea observable.
                with self._en_curso_lock:
                    self._en_curso += 1
                    self.max_simultaneas = max(self.max_simultaneas, self._en_curso)
                time.sleep(0.02)
                with self._en_curso_lock:
                    self._en_curso -= 1
                self.pasadas.append(1)

        #: El retardo es el asentado de la concesión (10 s), no el periodo de nada; un
        #: test no puede esperarlo. Se lee del global del módulo en cada pasada.
        self._parche = mock.patch.object(dn, "AUTO_RETOMAR_DELAY_SEGUNDOS", retardo)
        self._parche.start()
        self.addCleanup(self._parche.stop)
        nucleo = _Nucleo()
        self.addCleanup(nucleo._detener_metronomo)
        return nucleo

    @staticmethod
    def _hasta(condicion, segundos=2.0):
        """Espera `condicion()` sin dormir a ciegas: devuelve cuándo se cumplió."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if condicion():
                return True
            time.sleep(0.005)
        return False

    def test_sin_concesion_no_hay_pasada(self):
        """Nadie llama a `_programar_retomar_tareas`: ni hilo, ni `/tasks`, ni voz."""
        n = self._nucleo_de_pega()
        time.sleep(0.1)
        self.assertEqual((n.pasadas, n._retomar_hilo), ([], None),
                         "el metrónomo caminó sin que nadie le concediera el acceso")

    def test_una_concesion_da_una_sola_pasada(self):
        """El bug medido: con el acceso concedido, el bucle viejo hacía `wait()` sobre
        `_acceso_concedido` —que el gate deja puesto— y pedía `/tasks` entero cada 10 s
        hasta el fin de la sesión. Una concesión, una pasada: después de ella el hilo
        vuelve a dormir y no despierta solo."""
        n = self._nucleo_de_pega()
        n._acceso_concedido.set()
        n._programar_retomar_tareas()
        self.assertTrue(self._hasta(lambda: len(n.pasadas) == 1),
                        "la concesión no produjo ninguna pasada")
        #: Un lapso largo comparado con el retardo: si fuera un latido, a esta altura
        #: ya habría acumulado decenas de pasadas.
        time.sleep(0.3)
        self.assertEqual(len(n.pasadas), 1,
                         f"el metrónomo dio {len(n.pasadas)} pasadas por una concesión")
        self.assertEqual(n._retomar_hilo.name, "retomar-tareas",
                         "un solo hilo, y con nombre para poder esperarlo")

    def test_dos_concesiones_no_abren_dos_hilos_ni_dos_pasadas_a_la_vez(self):
        """Lo que el latido viejo no garantizaba: si llegan más concesiones mientras una
        pasada está en curso, sigue habiendo UN hilo y las pasadas se serializan. Dos
        cadenas de fondo pidiendo `/tasks` y peleando por el lock del LLM es lo que
        tapaba el input del teléfono."""
        n = self._nucleo_de_pega(retardo=0.005)
        n._acceso_concedido.set()
        hilos = set()
        for _ in range(6):
            n._programar_retomar_tareas()
            hilos.add(n._retomar_hilo)
            time.sleep(0.01)
        self.assertTrue(self._hasta(lambda: bool(n.pasadas)),
                        "seis concesiones y el metrónomo no dio ni una pasada")
        time.sleep(0.1)
        self.assertEqual(len(hilos), 1,
                         f"se abrieron {len(hilos)} hilos de metrónomo")
        self.assertEqual(n.max_simultaneas, 1,
                         "dos pasadas del metrónomo corrieron a la vez")
        self.assertGreater(len(n.pasadas), 0, "seis concesiones no producieron pasada")

    def test_un_rebloqueo_durante_el_asentado_cancela_la_pasada(self):
        """Si el rostro desaparece mientras la pasada estaba en camino, no se habla por
        encima de un acceso ya retirado."""
        n = self._nucleo_de_pega(retardo=0.05)
        n._programar_retomar_tareas()
        time.sleep(0.2)
        self.assertEqual(n.pasadas, [],
                         "hubo pasada sin acceso concedido")
        self.assertFalse(n._retomar_solicitado.is_set(),
                         "la señal quedó pendiente: se consumió en vano o nunca se miró")

    def test_la_parada_saca_al_hilo_de_su_wait(self):
        """El hilo duerme en un `wait()` sin timeout: sin una parada que lo despierte no
        hay forma de apagarlo —el defecto 3, cerrado por la Fase D—."""
        n = self._nucleo_de_pega()
        n._acceso_concedido.set()
        n._programar_retomar_tareas()
        self.assertTrue(self._hasta(lambda: len(n.pasadas) == 1))
        hilo = n._retomar_hilo
        n._detener_metronomo()
        self.assertTrue(self._hasta(lambda: not hilo.is_alive()),
                        "el hilo del metrónomo sobrevivió a `_detener_metronomo`")
        n._programar_retomar_tareas()
        self.assertFalse(n._retomar_solicitado.is_set(),
                         "después de parado, una concesión volvió a armear la señal")


class TestLasTareasInterrumpidasTienenDueno(unittest.TestCase):
    """Conducta del defecto 2 cerrado: `/tasks/interrupted` son datos, y de los datos
    solo se anuncia lo que el contrato llama reanudable."""

    def _nucleo_de_pega(self, respuesta):
        import nucleo.dark_nucleo as dn

        class _Cliente:
            def interrumpidas(self, timeout=None):
                self.timeout = timeout
                return respuesta

        class _Nucleo:
            _verificar_tareas_interrumpidas = (
                dn.DarkNucleo._verificar_tareas_interrumpidas)

            def __init__(self):
                self._cliente_manager = _Cliente()
                self._avisos_pendientes = queue.Queue()

        return _Nucleo()

    def _leer(self, nucleo):
        """El escáner imprime su recuento; aquí importa el valor devuelto y la cola."""
        import contextlib
        import io
        with contextlib.redirect_stdout(io.StringIO()):
            return nucleo._verificar_tareas_interrumpidas()

    def test_dos_canceladas_no_avisan_nada(self):
        """La foto del 25-oct: las dos tareas que devolvía `/tasks/interrupted` estaban
        `Cancelada`. Reanudarlas era el bug; decirlas era el ruido."""
        canceladas = (Tarea(id="x1", descripcion="informe sobre ventas",
                            estado="Cancelada",
                            pasos=(PasoTarea(id="p1", completado=True),
                                   PasoTarea(id="p2"))),
                      Tarea(id="x2", descripcion="borrar el log", estado="Cancelada",
                            pasos=(PasoTarea(id="p1"),)))
        n = self._nucleo_de_pega(canceladas)
        self.assertEqual(self._leer(n), ())
        self.assertTrue(n._avisos_pendientes.empty(),
                        "el aviso volvió a salir de tareas canceladas")

    def test_una_con_pasos_pendientes_si_se_anuncia(self):
        pendiente = (Tarea(id="y1", descripcion="documentar la API",
                           estado="Pausada",
                           pasos=(PasoTarea(id="p1", completado=True),
                                  PasoTarea(id="p2"))),)
        n = self._nucleo_de_pega(pendiente)
        self.assertEqual(self._leer(n), pendiente)
        aviso = n._avisos_pendientes.get_nowait()
        self.assertIn("documentar la API", aviso)

    def test_el_silencio_no_es_ausencia(self):
        """`None` es «no pude leer»: no se anuncia ni se confunde con «no hay»."""
        n = self._nucleo_de_pega(None)
        self.assertEqual(self._leer(n), ())
        self.assertTrue(n._avisos_pendientes.empty())
        self.assertEqual(n._cliente_manager.timeout, 3,
                         "el escáner de arrancada dejó de pedir su timeout propio de 3 s")


class TestLosPollersDelMenuSeApagan(unittest.TestCase):
    """Conducta del defecto 3 cerrado: los dos hilos del menú tienen parada y se les
    puede esperar."""

    def _nucleo_de_pega(self):
        import nucleo.dark_nucleo as dn

        class _Overlay:
            def estado(self):
                return "idle"

        class _Nucleo:
            _poll_recursos_periodicamente = (
                dn.DarkNucleo._poll_recursos_periodicamente)
            _poll_tareas_periodicamente = (
                dn.DarkNucleo._poll_tareas_periodicamente)
            _detener_pollers_del_menu = dn.DarkNucleo._detener_pollers_del_menu

            def __init__(self):
                self._menu_stop_polling = threading.Event()
                self._menu_lock = threading.Lock()
                self._menu_recursos_visible = False
                self._menu_tareas_visible = False
                self._menu_recursos_data = {}
                self._menu_tareas_data = []
                self.peticiones = []
                self.overlay = _Overlay()

            def _obtener_estado_recursos(self):
                self.peticiones.append("status")
                return EstadoRecursos(respondio=True)

            def _obtener_tareas_actuales(self):
                self.peticiones.append("tasks")
                return ()

            def _filtrar_tareas_activas(self, tareas):
                return [t.como_dict() for t in tareas]

            def _set_overlay(self, state, menu_data=None):
                pass

        n = _Nucleo()
        n._hilo_poll_recursos = threading.Thread(
            target=n._poll_recursos_periodicamente, daemon=True, name="poll-recursos")
        n._hilo_poll_tareas = threading.Thread(
            target=n._poll_tareas_periodicamente, daemon=True, name="poll-tareas")
        n._hilo_poll_recursos.start()
        n._hilo_poll_tareas.start()
        return n

    def test_menu_cerrado_no_pide_nada(self):
        """El `if` de visibilidad va dentro del bucle: con el menú cerrado los dos
        pollers duermen sin tocar el wire."""
        n = self._nucleo_de_pega()
        time.sleep(0.2)
        self.assertEqual(n.peticiones, [],
                         f"el menú cerrado pidió {n.peticiones}")
        n._detener_pollers_del_menu()

    def test_la_parada_termina_los_dos_hilos(self):
        n = self._nucleo_de_pega()
        self.assertTrue(n._hilo_poll_recursos.is_alive())
        n._menu_recursos_visible = True
        n._menu_tareas_visible = True
        n._detener_pollers_del_menu()
        for hilo in (n._hilo_poll_recursos, n._hilo_poll_tareas):
            self.assertFalse(hilo.is_alive(),
                             f"{hilo.name} sobrevivió a la parada del menú")
        self.assertTrue(n._menu_stop_polling.is_set())


class TestCerrarTareaContraLoMedido(unittest.TestCase):
    """26-oct: la duda que el contrato dejaba escrita —«por qué el `/complete` no cierra
    la tarea»— estaba **mal puesta**. Medido contra el Task Manager vivo: `/complete` sí
    cierra (el log imprime `TAREA COMPLETADA` tantas veces como tareas en `Completada`
    hay: 13 de 13) y lo roto es el alrededor. El único POST de esta medición llevó un id
    inventado y midió el 500 vacío que predice el `Program.cs:160` sin `try/catch`.

    Aquí queda el hueco de Python, que es el único corregible desde esta normalización:
    la rama de cancelación del worker cierra la intención y avisa por voz, pero **no**
    POSTea `/cancel`, así que la tarea se queda viva en el servidor mientras Dark ya la
    olvidó —y `/tasks/interrupted` la devuelve el resto de la vida, porque el servidor
    tampoco limpia su marca de interrupción al cerrar—.
    """

    def test_la_rama_de_cancelacion_del_worker_no_avisa_al_servidor(self):
        worker = _func(NUCLEO_REL, "DarkNucleo", "_worker_tareas_bg")
        attrs = {a.attr for a in ast.walk(worker) if isinstance(a, ast.Attribute)}
        self.assertNotIn(
            "cancelar", attrs,
            "el worker ya POSTea `/cancel` al cancelarse: el contrato y los docs de R4 "
            "dicen lo contrario, hay que reescribirlos")
        self.assertIn(
            "_completar_tarea", attrs,
            "la rama de éxito dejó de cerrar la tarea en el servidor: el `/complete` "
            "que sí funcionaba ya no se llama")

    def test_el_500_del_complete_inexistente_esta_escrito_en_la_ruta(self):
        """El contrato es el sitio donde vive la forma del servidor. `POST /complete` con
        un id que no existe contesta 500 medido —no 404— y Python le gasta sus 3
        reintentos; si algún día el servidor devuelve 404, este pin se cae y la tabla
        `RUTAS_TAREAS` deja de ser verdad."""
        dueña = [v for (r, _verb, v) in RUTAS_TAREAS
                 if r == "/tasks/{tarea_id}/complete"]
        self.assertEqual(len(dueña), 1, f"/complete declarado {len(dueña)} veces")
        self.assertIn("500", dueña[0],
                      "la tabla no dice ya qué contesta el servidor a un id inexistente")


if __name__ == "__main__":
    unittest.main()
