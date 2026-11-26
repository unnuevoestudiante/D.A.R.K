"""R2: el banco existe, describe lo mismo y solo resuelve por nombre exacto.

El banco (`herramientas/banco.py` + su fábrica) se construye aquí sobre dos
mundos: dobles generados a partir del inventario real medido por AST (31 `tool_*`
+ los 3 del núcleo) y los especialistas reales que la fábrica del R3 ya sabe
montar. Lo que se prueba no es que el banco funcione con juguetes: es que **ve
exactamente lo mismo que ve el despachador de `dark_nucleo.py`** — el mismo
esquema JSON, los mismos nombres, el mismo dueño por herramienta — para que la
Fase C pueda apagar el reflejo sin que el modelo note el cambio.

Ref: herramientas/banco.py, herramientas/fabrica.py, contratos/herramienta.py,
nucleo/dark_nucleo.py (`_ejecutar_herramienta`).
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
from contratos.herramienta import (  # noqa: E402
    ALIAS_DE_NOMBRES,
    FUENTE_NUCLEO,
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
    INVISIBLES_AL_MODELO,
    PREFIJO_HERRAMIENTA,
    PuertoBancoHerramientas,
    PuertoHerramienta,
    REGISTRO_ESPECIALISTAS,
    RESOLUCION_ALIAS,
    RESOLUCION_BARRIDO,
    RESOLUCION_CONTRATO,
    RESOLUCION_NUCLEO,
    DescriptorHerramienta,
    ParametroHerramienta,
)
from herramientas.banco import (  # noqa: E402
    BancoHerramientas,
    Dueño,
    EjecutableNoEncontrado,
    FaltaArgumento,
    HerramientaMontada,
    HerramientaNoEncontrada,
)
from herramientas.fabrica import (  # noqa: E402
    crear_banco,
    dueños_de_registro,
    mapa_de_dueños,
)

# Los cinco dueños reales de `tool_*` (mismo inventario que vigila la Fase A).
FUENTES = {
    "codigo": ("especialistas/especialista_codigo.py", "EspecialistaCodigo"),
    "comunicacion": ("especialistas/especialista_comunicacion.py",
                     "EspecialistaComunicacion"),
    "tareas": ("especialistas/especialista_tareas.py", "EspecialistaTareas"),
    "conversacion": ("especialistas/especialista_conversacional.py",
                     "EspecialistaConversacional"),
    "terminal": ("herramientas/externas/terminal.py", "DarkTerminal"),
}
NUCLEO = ("nucleo/dark_nucleo.py", "DarkNucleo")
CAPACIDADES = ("herramientas/internas/ejecutor.py", "EjecutorHerramientas")
PAQUETES_PRODUCCION = ("nucleo", "modulos", "especialistas", "proveedores",
                       "voz", "overlay", "acceso", "herramientas")

_ARBOLES = {}


def _arbol(rel):
    if rel not in _ARBOLES:
        _ARBOLES[rel] = ast.parse((DARK_PYTHON / rel).read_text(encoding="utf-8"))
    return _ARBOLES[rel]


def _clase(rel, nombre):
    for nodo in ast.walk(_arbol(rel)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"clase {nombre} no encontrada en {rel}")


def _herramientas(cls_ast):
    return {n.name[len(PREFIJO_HERRAMIENTA):] for n in cls_ast.body
            if isinstance(n, ast.FunctionDef)
            and n.name.startswith(PREFIJO_HERRAMIENTA)}


# El mapa del banco sale del contrato de especialista (R3), no del núcleo: la
# fábrica lo deriva y aquí se le pide igual que en producción.
MAPA = mapa_de_dueños()
POR_DUEÑO = {c: _herramientas(_clase(*FUENTES[c])) for c in FUENTES}
TODAS = set().union(*POR_DUEÑO.values())
ENTRADAS = {e["name"]: e for e in tm.MANIFEST}
# Los dos dueños sin prefijo: el núcleo y el módulo de capacidades. Para el banco
# son la MISMA ruta (nombre pelado, RESOLUCION_NUCLEO), así que las cuentas de
# inventario se suman; lo que las separa es quién define el método.
SIN_PREFIJO = set(HERRAMIENTAS_DEL_NUCLEO) | set(HERRAMIENTAS_DE_CAPACIDADES)


# --------------------------------------------------------------------------------
# Dobles: un dueño cuyos `tool_*` tienen LA firma declarada en el MANIFEST, para
# que la política de argumentos del banco se pruebe contra shapes reales.
# --------------------------------------------------------------------------------

def _metodo(nombre_metodo, params, requeridos, contexto_extra):
    """Devuelve `def <nombre_metodo>(self, ...)` que devuelve lo que le llegó.

    Se genera con `exec` a propósito: un `**kwargs` genérico no ejercita la parte
    del banco que filtra por firma, que es justo la que el despachador hace hoy.
    Las herramientas sin declaración en el MANIFEST sí reciben `**sobrantes`, como
    las reales.
    """
    args = [p if p in requeridos else f"{p}=None" for p in params]
    if contexto_extra:
        args += ["tarea_id=None", "paso_id=None"]
    if args:
        firma = ", ".join(["self"] + args)
        sobrantes = "{}"
    else:
        firma = "self, **sobrantes"
        sobrantes = "sobrantes"
    recibidos = ", ".join(f"{p!r}: {p}" for p in params)
    contexto = ", 'tarea_id': tarea_id, 'paso_id': paso_id" if contexto_extra else ""
    codigo = (f"def {nombre_metodo}({firma}):\n"
              f"    return {{'llamada': {nombre_metodo!r}, 'recibidos': "
              f"{{{recibidos}}}{contexto}, 'sobrantes': {sobrantes}}}\n")
    ns = {}
    exec(codigo, ns)
    return ns[nombre_metodo]


def _dobles_por_capacidad():
    """{capacidad: objeto} con los 31 `tool_*` medidos, cada uno con su firma.

    Solo las 4 capacidades del registro: conversación tiene 0 `tool_*` y además no
    está en `_registro_especialistas()`, así que un dueño suyo sería inventado.
    """
    salida = {}
    for capacidad in REGISTRO_ESPECIALISTAS:
        nombres = POR_DUEÑO[capacidad]
        atributos = {}
        for nombre in nombres:
            entrada = ENTRADAS.get(nombre)
            atributos[PREFIJO_HERRAMIENTA + nombre] = _metodo(
                PREFIJO_HERRAMIENTA + nombre,
                list(entrada["params"]) if entrada else [],
                list(entrada["required"]) if entrada else [],
                bool(entrada.get("contexto_extra")) if entrada else False,
            )
        salida[capacidad] = type(f"Doble{capacidad.title()}", (), atributos)()
    nucleares = {}
    for nombre in HERRAMIENTAS_DEL_NUCLEO:
        entrada = ENTRADAS.get(nombre)
        nucleares[nombre] = _metodo(
            nombre, list(entrada["params"]), list(entrada["required"]),
            bool(entrada.get("contexto_extra")))
    salida["nucleo"] = type("DobleNucleo", (), nucleares)()
    capacidades = {}
    for nombre in HERRAMIENTAS_DE_CAPACIDADES:
        entrada = ENTRADAS.get(nombre)
        capacidades[nombre] = _metodo(
            nombre, list(entrada["params"]), list(entrada["required"]),
            bool(entrada.get("contexto_extra")))
    salida["capacidades"] = type("DobleCapacidades", (), capacidades)()
    return salida


def _banco_de_dobles(**kwargs):
    dobles = _dobles_por_capacidad()
    núcleo = dobles.pop("nucleo")
    capacidades = dobles.pop("capacidades")
    return crear_banco(especialistas=dobles, núcleo=núcleo,
                       capacidades=capacidades, **kwargs)


class PruebaInventarioDelBanco(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banco = _banco_de_dobles(mapa=MAPA)

    def test_todos_los_ejecutables_estan_montados(self):
        faltan = [n for n in TODAS | SIN_PREFIJO
                  if self.banco.montada(n) is None]
        self.assertEqual(faltan, [], f"el banco no monta {faltan}")

    def test_el_banco_no_inventa_nombres(self):
        conocidos = TODAS | set(ENTRADAS) | SIN_PREFIJO
        extranos = {d.nombre for d in self.banco.descriptores()} - conocidos
        self.assertEqual(extranos, set(), f"el banco publicó {extranos}")

    def test_son_36_descriptores_con_36_montadas(self):
        self.assertEqual(len(self.banco.descriptores()), 37)  # + planificar_proyecto
        self.assertEqual(len(self.banco.descriptores()),
                         len(TODAS) + 5)
                         # los 31 tool_* + descargar_archivo + el alias
                         # terminal_desarrollo + abrir_en_navegador (K.3.2) +
                         # guardar_sitio_web (K.3.5b) + cambiar_nombre_archivo
                         # (residuo #1), los tres últimos del núcleo
                         # y sin `tool_*` detrás
        self.assertEqual(
            sorted(n for n in self.banco.descriptores()
                   if self.banco.montada(n.nombre) is None), [])

    def test_los_invisibles_no_van_al_modelo(self):
        for nombre in INVISIBLES_AL_MODELO:
            descriptor = self.banco.descriptor(nombre)
            self.assertIsNotNone(descriptor, nombre)
            self.assertFalse(descriptor.visible_al_modelo, nombre)
            self.assertEqual(descriptor.params, (),
                             f"{nombre}: el banco inventó parámetros no declarados")

    def test_terminal_desarrollo_llega_a_su_ejecutable_por_alias(self):
        """Defectos 3 y 5, cerrados a la vez: el `handler` declarado no existía.

        El banco no lo inventa: `ALIAS_DE_NOMBRES` traduce el nombre que el modelo
        pide al ejecutable que sí existe, y la resolución queda marcada como alias
        para que el catálogo lo admita en vez de esconderlo.
        """
        self.assertEqual(self.banco.sin_ejecutable(), ())
        descriptor = self.banco.descriptor("terminal_desarrollo")
        self.assertEqual(descriptor.resolucion, RESOLUCION_ALIAS)
        self.assertEqual(descriptor.ejecutor,
                         PREFIJO_HERRAMIENTA + ALIAS_DE_NOMBRES["terminal_desarrollo"])
        self.assertEqual(descriptor.especialista, "terminal")
        self.assertEqual(descriptor.inconsistencias(), ())
        self.assertIsNotNone(self.banco.montada("terminal_desarrollo"))
        resultado = self.banco.ejecutar("terminal_desarrollo", {"operacion": "espacio_disco"})
        self.assertEqual(resultado["llamada"], "tool_terminal_coder")

    def test_sin_el_dueno_del_alias_la_huerfana_se_sigue_nombrando(self):
        """Quitar `terminal` del registro: el alias no crea un ejecutable de la nada."""
        dobles = _dobles_por_capacidad()
        núcleo = dobles.pop("nucleo")
        capacidades = dobles.pop("capacidades")
        del dobles["terminal"]
        banco = crear_banco(especialistas=dobles, núcleo=núcleo,
                            capacidades=capacidades, mapa=MAPA)
        self.assertEqual(set(banco.sin_ejecutable()),
                         {"terminal_diagnostico", "terminal_desarrollo"})
        with self.assertRaises(EjecutableNoEncontrado) as error:
            banco.ejecutar("terminal_desarrollo", {"operacion": "espacio_disco"})
        self.assertEqual(error.exception.codigo, "handler_not_found:terminal_desarrollo")

    def test_un_alias_no_desvia_lo_que_ya_existe(self):
        """`terminal_coder` se pide por su nombre real: el alias es solo para el
        nombre declarado al modelo, no un segundo acceso al mismo ejecutable."""
        descriptor = self.banco.descriptor("terminal_coder")
        self.assertNotEqual(descriptor.resolucion, RESOLUCION_ALIAS)
        self.assertEqual(descriptor.ejecutor, "tool_terminal_coder")

    def test_el_inventario_cambio_de_tamano_se_avisa_aqui(self):
        """31 tool_* + los 6 sin prefijo = 36. Si la Fase C o el corte de
        capacidades mueve cuerpos, este número baja y se actualiza.

        El corte de conmutación no cambia la cuenta: saca los dos métodos del
        núcleo y los pone en el dueño de capacidades. Lo que sí cambia es el
        REPARTO de las seis sin prefijo, y eso lo vigila
        `test_los_seis_nombres_sin_prefijo_viven_en_el_contrato`.
        """
        self.assertEqual(len(TODAS), 32)  # + planificar_proyecto (plan-coder-v2)
        self.assertEqual(len(HERRAMIENTAS_DEL_NUCLEO), 0)
        self.assertEqual(len(HERRAMIENTAS_DE_CAPACIDADES), 6)
        self.assertEqual(len(SIN_PREFIJO), 6)


class PruebaConformidadConLoQueVeElModelo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banco = _banco_de_dobles(mapa=MAPA)

    def test_el_esquema_del_banco_es_el_del_MANIFEST(self):
        self.assertEqual(self.banco.esquema_para_el_modelo(), tm.tools_schema())

    def test_los_nombres_del_router_son_los_del_manifiesto(self):
        self.assertEqual(self.banco.nombres_del_router(), tuple(tm.tool_names()))

    def test_sin_dobles_el_banco_de_la_fabrica_también_coincide(self):
        """La fábrica sin dueños: publica las 21 declaradas igual, sin montar nada."""
        banco = crear_banco(especialistas={})
        self.assertEqual(banco.esquema_para_el_modelo(), tm.tools_schema())
        self.assertEqual(len(banco.sin_ejecutable()), 21)
        self.assertEqual(len(banco.descriptores()), 21)

    def test_los_flags_de_ejecucion_siguen_viajando(self):
        for nombre, entrada in ENTRADAS.items():
            d = self.banco.descriptor(nombre)
            self.assertEqual(d.background, bool(entrada.get("background", False)), nombre)
            self.assertEqual(d.respuesta_directa,
                             bool(entrada.get("respuesta_directa", False)), nombre)
            self.assertEqual(d.contexto_extra,
                             bool(entrada.get("contexto_extra", False)), nombre)


class PruebaRutasYDuenos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con_mapa = _banco_de_dobles(mapa=MAPA)
        cls.sin_mapa = _banco_de_dobles(mapa={})

    def _resolucion_esperada(self, nombre):
        if nombre in SIN_PREFIJO:
            return RESOLUCION_NUCLEO
        if nombre in ALIAS_DE_NOMBRES:
            return RESOLUCION_ALIAS
        return RESOLUCION_CONTRATO if nombre in MAPA else RESOLUCION_BARRIDO

    def test_cada_herramienta_conoce_su_ruta(self):
        for nombre in sorted(TODAS | SIN_PREFIJO):
            d = self.con_mapa.descriptor(nombre)
            self.assertEqual(d.resolucion, self._resolucion_esperada(nombre), nombre)

    def test_el_mapa_del_contrato_y_el_escaneo_reparten_los_mismos_duenos(self):
        """La promesa que hizo posible la Fase C: el mapa no elige dueños, los copia.

        `mapa_de_dueños()` se deriva escaneando las tuplas del contrato, así que un
        banco sin mapa llega al mismo dueño barriendo `dueños` en orden. Si alguien
        añade al mapa una herramienta que su especialista no define, esta prueba lo
        nombra.
        """
        for nombre in TODAS | SIN_PREFIJO:
            con = self.con_mapa.montada(nombre)
            sin = self.sin_mapa.montada(nombre)
            self.assertIsNotNone(con, nombre)
            self.assertEqual(con.dueño, sin.dueño, nombre)
            self.assertEqual(con.descriptor.especialista, sin.descriptor.especialista,
                             nombre)

    def test_el_nucleo_gana_a_comunicacion_en_los_dos_sombreados(self):
        for nombre in ("investigar", "buscar_imagenes"):
            d = self.con_mapa.descriptor(nombre)
            self.assertEqual(d.fuente, FUENTE_NUCLEO, nombre)
            self.assertEqual(d.resolucion, RESOLUCION_NUCLEO, nombre)
            self.assertEqual(d.ejecutor, nombre, nombre)
            self.assertEqual(d.especialista, None, nombre)
            self.assertIn(nombre, POR_DUEÑO["comunicacion"],
                          f"tool_{nombre} ya no está en comunicación: la sombra "
                          f"del núcleo dejó de ser código muerto")

    def test_los_seis_nombres_sin_prefijo_viven_en_el_contrato(self):
        """Las dos listas del contrato son la única dueña del dato.

        `_TOOLS_NUCLEO` murió con el despachador y el corte de capacidades no
        metió una tercera: lo que cada lista reclama tiene que estar DEFINIDO en
        el archivo del dueño que esa lista nombra, y en ningún otro. Ahí es donde
        se ve que un cuerpo se quedó en el núcleo después de cambiar de dueño.
        """
        self.assertEqual(set(HERRAMIENTAS_DEL_NUCLEO) |
                         set(HERRAMIENTAS_DE_CAPACIDADES),
                         {"descargar_archivo", "investigar", "buscar_imagenes",
                          "abrir_en_navegador", "guardar_sitio_web",
                          "cambiar_nombre_archivo"})
        self.assertEqual(set(HERRAMIENTAS_DEL_NUCLEO) &
                         set(HERRAMIENTAS_DE_CAPACIDADES), set(),
                         "un nombre reclamado por dos dueños sin prefijo")
        núcleo = {n.name for n in _clase(*NUCLEO).body
                  if isinstance(n, ast.FunctionDef)}
        for nombre in HERRAMIENTAS_DEL_NUCLEO:
            self.assertIn(nombre, núcleo,
                          f"el contrato reclama {nombre} pero el núcleo no lo define")
        dueño = {n.name for n in _clase(*CAPACIDADES).body
                 if isinstance(n, ast.FunctionDef)}
        for nombre in HERRAMIENTAS_DE_CAPACIDADES:
            self.assertIn(nombre, dueño,
                          f"{nombre} es de capacidades pero el módulo no lo define")
            self.assertNotIn(nombre, núcleo,
                             f"{nombre} cambió de dueño pero sigue en el núcleo")
        self.assertNotIn("_TOOLS_NUCLEO",
                         (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
                             encoding="utf-8"),
                         "el núcleo volvió a tener su propia lista de herramientas")

    def test_el_contador_de_rutas(self):
        rutas = {}
        for d in self.con_mapa.descriptores():
            rutas[d.resolucion] = rutas.get(d.resolucion, 0) + 1
        self.assertEqual(rutas, {RESOLUCION_CONTRATO: 30, RESOLUCION_NUCLEO: 6,
                                 RESOLUCION_ALIAS: 1})

    def test_el_barrido_es_politica_de_respaldo_sin_clientes(self):
        """Hoy ninguna herramienta necesita barrer dueños: el contrato nombra a las 31.

        La ruta sigue ahí para el día que un especialista publique un `tool_*` que
        el contrato aún no declare; si esta prueba falla porque alguien llenó las
        tuplas de más, hay que re-leer `contratos/especialista.py`.
        """
        sin_mapa = _banco_de_dobles(mapa={})
        barridas = {d.nombre for d in self.con_mapa.descriptores()
                    if d.resolucion == RESOLUCION_BARRIDO}
        self.assertEqual(barridas, set())
        # Sin mapa, el escaneo hace el trabajo entero: el mismo catálogo, otra ruta.
        self.assertEqual({d.nombre for d in sin_mapa.descriptores()},
                         {d.nombre for d in self.con_mapa.descriptores()})


class PruebaPoliticaDeArgumentos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.banco = _banco_de_dobles(mapa=MAPA)

    def test_los_defaults_del_descriptor_se_aplican(self):
        resultado = self.banco.ejecutar("crear_recurso", {"ruta": "C:/x", "tipo": "archivo"})
        self.assertEqual(resultado["recibidos"]["contenido"], "")

    def test_el_alias_renombra_cuando_procede(self):
        """El alias es para el nombre que el esquema sí ofrece, no para un invento."""
        def handler(ruta, tipo="archivo"):
            return {"ruta": ruta, "tipo": tipo}
        d = DescriptorHerramienta(
            nombre="demo_alias", declarada=True,
            params=(ParametroHerramienta.desde("ruta", {"type": "string", "description": "r"}),
                    ParametroHerramienta.desde("tipo_doc", {"type": "string", "description": "t"})),
            requeridos=("ruta",), resolucion=RESOLUCION_BARRIDO, especialista="codigo")
        preparada = HerramientaMontada(d, handler, dueño="codigo").preparar(
            {"ruta": "C:/x", "tipo_doc": "carpeta"})
        self.assertEqual(preparada.argumentos, {"ruta": "C:/x", "tipo": "carpeta"})

    def test_un_alias_no_declorado_se_descarta_antes_de_renombrarse(self):
        """Fidelidad al despachador: `crear_recurso` no declara `tipo_doc`, así que
        hoy el modelo no puede mandarlo y el alias no llega a verlo."""
        preparada = self.banco.montada("crear_recurso").preparar(
            {"ruta": "C:/x", "tipo": "archivo", "tipo_doc": "carpeta"})
        self.assertIn("tipo_doc", preparada.descartados)
        self.assertEqual(preparada.argumentos["tipo"], "archivo")

    def test_lo_no_declorado_se_descarta_y_se_nombra(self):
        preparada = self.banco.montada("leer_archivo").preparar(
            {"ruta": "C:/x", "inventado": 1})
        self.assertEqual(preparada.descartados, ("inventado",))
        self.assertEqual(list(preparada.argumentos), ["ruta"])

    def test_un_requerido_que_falla_lleva_el_codigo_del_nucleo(self):
        with self.assertRaises(FaltaArgumento) as error:
            self.banco.ejecutar("leer_archivo", {})
        self.assertEqual(error.exception.codigo, "missing_param:ruta")

    def test_un_default_de_python_sustituye_al_requerido(self):
        """Refleja la salida del despachador (:6329-6336): `required` no es una
        condena si el handler ya tiene default en Python."""
        def handler(ruta="por_defecto"):
            return ruta
        d = DescriptorHerramienta(nombre="demo", requeridos=("ruta",),
                                  resolucion=RESOLUCION_BARRIDO, especialista="codigo")
        montada = HerramientaMontada(d, handler, dueño="codigo")
        self.assertEqual(montada.ejecutar({}), "por_defecto")

    def test_contexto_extra_inyecta_y_lo_no_declorado_no_entra(self):
        con_contexto = self.banco.ejecutar("escribir_documento",
                                           {"tema": "t", "nombre_archivo": "n"},
                                           contexto={"tarea_id": "T", "paso_id": "P"})
        self.assertEqual(con_contexto["tarea_id"], "T")
        self.assertEqual(con_contexto["paso_id"], "P")
        sin_contexto = self.banco.montada("leer_archivo").preparar(
            {"ruta": "C:/x"}, contexto={"tarea_id": "T", "paso_id": "P"})
        self.assertNotIn("tarea_id", sin_contexto.argumentos)

    def test_paso_id_cae_al_nombre_de_la_herramienta(self):
        resultado = self.banco.ejecutar("escribir_documento",
                                        {"tema": "t", "nombre_archivo": "n"},
                                        contexto={"tarea_id": "T"})
        self.assertEqual(resultado["paso_id"], "escribir_documento")

    def test_el_normalizador_solo_toca_lo_que_suen_a_ruta(self):
        banco = _banco_de_dobles(mapa=MAPA,
                                 normalizador=lambda v: v.replace("\\", "/"))
        resultado = banco.ejecutar(
            "crear_recurso", {"ruta": "C:\\x\\y", "tipo": "archivo",
                              "contenido": "C:\\sin\\tocar"})
        self.assertEqual(resultado["recibidos"]["ruta"], "C:/x/y")
        self.assertEqual(resultado["recibidos"]["contenido"], "C:\\sin\\tocar",
                         "`contenido` no es una ruta aunque lo parezca")

    def test_preparar_no_muta_el_diccionario_del_llamador(self):
        """El núcleo reutiliza los args del turno registrado; si el banco los
        pisara, la telemetría contaría argumentos que el modelo nunca mandó."""
        originales = {"ruta": "C:/x", "tipo": "archivo", "tipo_doc": "carpeta"}
        copia = dict(originales)
        self.banco.montada("crear_recurso").preparar(originales)
        self.assertEqual(originales, copia)

    def test_un_handler_con_kwargs_no_pierde_nada(self):
        d = DescriptorHerramienta(nombre="flexible",
                                  resolucion=RESOLUCION_BARRIDO, especialista="tareas")
        montada = HerramientaMontada(d, lambda **kw: kw, dueño="tareas")
        preparada = montada.preparar({"uno": 1, "dos": 2})
        self.assertEqual(preparada.argumentos, {"uno": 1, "dos": 2})
        self.assertEqual(preparada.descartados, ())


class PruebaResolucionExacta(unittest.TestCase):
    """El defecto 5 de la Fase A: el despachador empareja por subcadena. El banco
    no, y eso es lo que hace que la Fase C sea segura."""

    @classmethod
    def setUpClass(cls):
        cls.banco = _banco_de_dobles(mapa=MAPA)

    def test_un_nombre_inventado_no_es_una_herramienta(self):
        self.assertIsNone(self.banco.descriptor("buscar_web_larga"))
        with self.assertRaises(HerramientaNoEncontrada) as error:
            self.banco.ejecutar("buscar_web_larga", {"consulta": "x"})
        self.assertEqual(error.exception.codigo, "tool_not_found:buscar_web_larga")

    def test_prefijo_incluido_en_el_pedido_tampoco_cuela(self):
        """`tool_leer_archivo` es el ejecutor; el LLM pide `leer_archivo`."""
        self.assertIsNone(self.banco.descriptor("tool_leer_archivo"))

    def test_contiene_es_exacto(self):
        for nombre in ("leer_archivo", "escribir_codigo"):
            self.assertTrue(self.banco.contiene(nombre))
        self.assertFalse(self.banco.contiene("leer"))
        self.assertFalse(self.banco.contiene(""))


class PruebaPuertosYDobleConformidad(unittest.TestCase):
    def test_el_banco_cumple_su_puerto(self):
        self.assertIsInstance(_banco_de_dobles(mapa=MAPA), PuertoBancoHerramientas)

    def test_cada_montada_cumple_su_puerto(self):
        banco = _banco_de_dobles(mapa=MAPA)
        for nombre in ("leer_archivo", "descargar_archivo", "terminal_diagnostico"):
            self.assertIsInstance(banco.montada(nombre), PuertoHerramienta, nombre)

    def test_la_montada_narra_como_se_monto(self):
        montada = _banco_de_dobles(mapa=MAPA).montada("descargar_archivo")
        texto = repr(montada)
        self.assertIn("descargar_archivo", texto)
        # El corte 1 la sacó del núcleo: el dueño que monta el ejecutable ya es
        # el módulo de capacidades, y la montada lo dice.
        self.assertIn("capacidades", texto)
        self.assertEqual(str(montada.firma), "(url, nombre_archivo=None)")


class PruebaDueños(unittest.TestCase):
    def test_el_dueno_del_nucleo_no_aceuta_lo_que_no_declara(self):
        """Sin acotar, cualquier método público del núcleo parecería herramienta."""
        class NúcleoFalso:
            def investigar(self, **kw):
                return "ok"

            def hablar(self, **kw):
                return "esto no es una herramienta"

        dueño = Dueño.del_núcleo(NúcleoFalso(), nombres=("investigar",))
        # La lista va a mano porque en producción `HERRAMIENTAS_DEL_NUCLEO` está
        # vacía desde el corte de conmutación; lo que se mide aquí es el
        # mecanismo de acotar, no el reparto actual.
        self.assertEqual(dueño.nombres_servidos(), ("investigar",))
        self.assertIsNone(dueño.ejecutable("hablar"))
        self.assertIsNotNone(dueño.ejecutable("investigar"))

    def test_el_dueno_no_evalua_properties(self):
        """`getattr_static`: descubrir herramientas no debe ejecutar nada del dueño."""
        class ConProperty:
            @property
            def tool_espia(self):
                raise AssertionError("el banco evaluó una property al descubrir")

        dueño = Dueño.del_especialista("comunicacion", ConProperty())
        self.assertEqual(dueño.nombres_servidos(), ())
        self.assertIsNone(dueño.ejecutable("espia"))

    def test_una_capacidad_desconocida_es_un_error_del_cableado(self):
        with self.assertRaises(ValueError):
            dueños_de_registro({"especialista_fantasma": object()})

    def test_el_orden_de_los_duenos_es_el_del_registro(self):
        dueños = dueños_de_registro({c: object() for c in
                                     ("codigo", "comunicacion", "tareas", "terminal")})
        self.assertEqual([d.nombre for d in dueños if d.prefijo],
                         ["codigo", "comunicacion", "tareas", "terminal"])
        self.assertEqual([d.nombre for d in dueños if d.prefijo == ""], [])


class PruebaBarrerasAST(unittest.TestCase):
    def test_el_banco_no_conoce_a_nadie_del_proyecto(self):
        """`banco.py` es stdlib + contratos: si importa un especialista, la
        hexagonal se rompió por el sitio más caro."""
        permitidos = {"inspect", "dataclasses", "typing", "contratos"}
        for nodo in ast.walk(_arbol("herramientas/banco.py")):
            if isinstance(nodo, ast.Import):
                for a in nodo.names:
                    self.assertIn(a.name.split(".")[0], permitidos | {"typing"},
                                  f"banco.py importa {a.name}")
            elif isinstance(nodo, ast.ImportFrom) and not nodo.level:
                raiz = (nodo.module or "").split(".")[0]
                self.assertIn(raiz, permitidos, f"banco.py importa {nodo.module}")

    def test_la_fabrica_es_el_unico_sitio_que_nombra_la_clase(self):
        vistos = set()
        for rel in PAQUETES_PRODUCCION:
            for p in (DARK_PYTHON / rel).rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                if "BancoHerramientas" in p.read_text(encoding="utf-8"):
                    vistos.add(p.name)
        self.assertEqual(vistos, {"banco.py", "fabrica.py"},
                         f"{vistos} nombran la clase concreta")

    def test_el_nucleo_es_el_unico_que_importa_el_banco(self):
        """Fase C: la puerta se abrió y solo el orquestador la usa.

        `fabrica.py` importa el banco para construirlo; `dark_nucleo.py` importa la
        fábrica y el error de herramienta. Ningún otro módulo de producción puede
        pedir herramientas por su cuenta: eso volvería a tener dos despachos.
        """
        permitidos = {"fabrica.py", "dark_nucleo.py"}
        for rel in PAQUETES_PRODUCCION:
            for p in (DARK_PYTHON / rel).rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                for nodo in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                    modulos = []
                    if isinstance(nodo, ast.Import):
                        modulos = [a.name for a in nodo.names]
                    elif isinstance(nodo, ast.ImportFrom):
                        if nodo.level == 0:
                            modulos = [nodo.module or ""]
                        else:
                            modulos = ["." * nodo.level + (nodo.module or "")]
                    for mod in modulos:
                        if "banco" in mod:
                            self.assertIn(p.name, permitidos,
                                          f"{p.name} importa {mod}: hay un segundo "
                                          f"camino hacia las herramientas")

    def test_crear_banco_solo_lo_llaman_la_fabrica_y_el_nucleo(self):
        """El núcleo compone el banco una vez (`_banco_herramientas`); nadie más."""
        llamadores = set()
        for rel in PAQUETES_PRODUCCION:
            for p in (DARK_PYTHON / rel).rglob("*.py"):
                if "__pycache__" in p.parts:
                    continue
                if "crear_banco" in p.read_text(encoding="utf-8"):
                    llamadores.add(p.name)
        self.assertEqual(llamadores, {"fabrica.py", "dark_nucleo.py"},
                         f"{llamadores} construyen bancos")

    def test_el_banco_no_empareja_por_subcadena(self):
        """Prohibido reproducir el `func_name in n or n in func_name` del núcleo.

        En las funciones de resolución solo se permite `in` contra una colección
        de claves exactas; cualquier otro `in` sería buscar una herramienta dentro
        del nombre pedido.
        """
        exactas = ("_mapa", "_nombres", "_descriptores", "_montadas")
        vigiladas = {"_bind", "_bind_exacto", "resolver", "contiene", "descriptor",
                     "ejecutar", "sirve", "_dueño_por_capacidad",
                     "_dueño_del_núcleo", "montada"}
        for nodo in ast.walk(_arbol("herramientas/banco.py")):
            if isinstance(nodo, ast.FunctionDef) and nodo.name in vigiladas:
                for compare in ast.walk(nodo):
                    if not isinstance(compare, ast.Compare):
                        continue
                    for op, comparador in zip(compare.ops, compare.comparators):
                        if not isinstance(op, (ast.In, ast.NotIn)):
                            continue
                        nombre = (getattr(comparador, "id", None)
                                  or getattr(comparador, "attr", None) or "")
                        self.assertTrue(
                            any(nombre.endswith(sufijo) for sufijo in exactas),
                            f"{nodo.name} hace un `in` contra {nombre or '?'}: "
                            f"volvió el emparejamiento difuso")

    def test_el_banco_no_reordena_ni_recorta_el_catalogo(self):
        """Otra seña del despachador: `sort(key=len)` sobre candidatos."""
        codigo = (DARK_PYTHON / "herramientas" / "banco.py").read_text(encoding="utf-8")
        for truco in ("sort(key=len", "MANIFEST_BY_NAME", "candidatos"):
            self.assertNotIn(truco, codigo, f"el banco usa {truco!r}")


class PruebaConDueñosReales(unittest.TestCase):
    """Los tres especialistas que se pueden montar sin VLC ni Ollama (los mismos
    que valida la fábrica del R3): aquí probamos que el banco los descubre de
    verdad, con sus firmas reales."""

    def setUp(self):
        try:
            from especialistas import fabrica as esp_fabrica
            from proveedores.manager.fabrica import crear_cliente_manager
        except ImportError as error:
            self.skipTest(f"especialistas no disponibles: {error}")
        sin_uso = lambda *a, **k: None  # noqa: E731
        # Cliente real de R4: estos especialistas ya no aceptan `requests` a mano, así
        # que montar el banco de verdad exige el puerto. Construirlo no toca la red y
        # ninguna prueba de aquí llama al Manager.
        self.cliente = crear_cliente_manager()
        self.dobles = {
            "codigo": esp_fabrica.crear_especialista_codigo(
                http_session=None, chat_provider=None, llm_lock=None,
                cliente_manager=self.cliente,
                liberar_whisper=sin_uso, recargar_whisper=sin_uso,
                preparar_modelo=sin_uso, liberar_modelo=sin_uso),
            "tareas": esp_fabrica.crear_especialista_tareas(
                http_session=None, chat_provider=None, llm_lock=None,
                cliente_manager=self.cliente,
                preparar_modelo=sin_uso, helpers={}),
            "terminal": esp_fabrica.crear_terminal(resumir_cb=sin_uso),
        }

    def tearDown(self):
        self.cliente.cerrar()

    def test_el_banco_descubre_las_herramientas_reales(self):
        banco = crear_banco(especialistas=self.dobles)
        esperado = POR_DUEÑO["codigo"] | POR_DUEÑO["tareas"] | POR_DUEÑO["terminal"]
        montadas = {n for n in esperado if banco.montada(n) is not None}
        self.assertEqual(montadas, esperado,
                         f"sin montar: {sorted(esperado - montadas)}")

    def test_una_herramienta_real_acepta_lo_que_declara(self):
        banco = crear_banco(especialistas=self.dobles)
        montada = banco.montada("leer_archivo")
        # `firma` sale de inspect.signature sobre el método enlazado: self ya no está.
        self.assertEqual(tuple(montada.firma.parameters), ("ruta",))
        preparada = montada.preparar({"ruta": "C:/no/existe/x.txt", "extra": 1})
        self.assertEqual(preparada.descartados, ("extra",))

    def test_el_terminal_real_se_monta_por_el_mapa(self):
        banco = crear_banco(especialistas=self.dobles, mapa=MAPA)
        d = banco.descriptor("terminal_diagnostico")
        self.assertEqual(d.resolucion, RESOLUCION_CONTRATO)
        self.assertEqual(d.especialista, "terminal")
        self.assertEqual(d.ejecutor, "tool_terminal_diagnostico")

    def test_las_herramientas_de_comunicacion_no_inventan_dueno(self):
        """Sin el dueño de comunicación, las declaradas quedan descriptas y sin
        montar: el banco no sustituye a un especialista que no está."""
        banco = crear_banco(especialistas=self.dobles)
        declaradas = sorted(POR_DUEÑO["comunicacion"] & set(ENTRADAS))
        self.assertEqual(
            declaradas,
            ["abrir_aplicacion", "buscar_imagenes", "cerrar_aplicacion",
             "detener_musica", "investigar",
             "reproducir_musica",
             "traducir_archivo", "traducir_texto"],
            "el inventario de comunicación declarada cambió")
        for nombre in declaradas:
            self.assertIsNotNone(banco.descriptor(nombre), nombre)
            self.assertIsNone(banco.montada(nombre), nombre)
        self.assertIn("abrir_aplicacion", banco.sin_ejecutable())


    def test_un_arg_que_cabe_en_la_firma_pero_no_en_el_esquema_no_pasa(self):
        """`escribir_codigo` acepta `tema` en Python sin declararlo al modelo.

        Aquí es donde el filtro del descriptor significa algo: con dueños reales la
        firma del handler deja pasar `tema` y el esquema no lo ofrece.
        """
        banco = crear_banco(especialistas=self.dobles)
        montada = banco.montada("escribir_codigo")
        self.assertIn("tema", tuple(montada.firma.parameters))
        preparada = montada.preparar({"tarea": "x", "tema": "invento del modelo"})
        self.assertNotIn("tema", preparada.argumentos)
        self.assertIn("tema", preparada.descartados)


if __name__ == "__main__":
    unittest.main(verbosity=2)
