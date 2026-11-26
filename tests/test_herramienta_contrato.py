"""R2: el contrato del banco de herramientas, contra la verdad medida.

La Fase A no movió ningún handler: describió los 31 ejecutables que ya existían.
Desde la Fase C el núcleo ya no llega a ellos por reflejo, así que este archivo
vigila dos cosas distintas: que la descripción siga siendo verdad (leyendo los
fuentes con AST — nada se instancia: el núcleo y los especialistas arrastran VLC,
Ollama y disco) y que el despacho viejo esté muerto del todo.

Seis frentes:

  * el contrato es solo stdlib y no conoce a nadie del proyecto;
  * el inventario: 31 `tool_*` repartidos 6/14/9/2/0, 19 nombres en el
    `MANIFEST`, 15 invisibles para el modelo;
  * las cuatro rutas de resolución (núcleo, contrato, alias, barrido), con el
    mapa que hoy deriva de las tuplas del contrato de especialista;
  * conformidad del descriptor: `a_esquema()` tiene que dar el mismo JSON que
    `manifest_tools.tools_schema()`, campo por campo y en orden;
  * quién lee cada campo de una entrada del `MANIFEST` ahora que el despachador
    ya no existe;
  * los defectos que R2 cerró y los que siguen abiertos.

Ref: contratos/herramienta.py, contratos/especialista.py, herramientas/banco.py,
herramientas/fabrica.py, nucleo/dark_nucleo.py (`_ejecutar_herramienta`).
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos import herramienta as hr  # noqa: E402
from contratos.especialista import (  # noqa: E402
    HERRAMIENTAS_CODIGO,
    HERRAMIENTAS_COMUNICACION,
    HERRAMIENTAS_TAREAS,
    HERRAMIENTAS_TERMINAL,
)
from contratos.herramienta import (  # noqa: E402
    ALIAS_DE_ARGUMENTOS,
    ALIAS_DE_NOMBRES,
    CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA,
    CAMPOS_LEIDOS_POR_EL_ROUTER,
    EJECUTABLES_CON_GATE_DE_CODIGO,
    DescriptorHerramienta,
    FUENTE_ESPECIALISTA,
    FUENTE_NUCLEO,
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
    INVISIBLES_AL_MODELO,
    ParametroHerramienta,
    PREFIJO_HERRAMIENTA,
    PuertoBancoHerramientas,
    PuertoHerramienta,
    REGISTRO_ESPECIALISTAS,
    RESOLUCION_ALIAS,
    RESOLUCION_BARRIDO,
    RESOLUCION_CONTRATO,
    RESOLUCION_NUCLEO,
    TIPOS_DE_PARAMETRO,
)

# Los cinco dueños reales de `tool_*` (terminal vive en herramientas/, no en
# especialistas/; conversación no atiende ninguna).
DUEÑOS = {
    "codigo": ("especialistas/especialista_codigo.py", "EspecialistaCodigo"),
    "comunicacion": ("especialistas/especialista_comunicacion.py",
                     "EspecialistaComunicacion"),
    "tareas": ("especialistas/especialista_tareas.py", "EspecialistaTareas"),
    "conversacion": ("especialistas/especialista_conversacional.py",
                     "EspecialistaConversacional"),
    "terminal": ("herramientas/externas/terminal.py", "DarkTerminal"),
}
POR_DUEÑO = {"codigo": 6, "comunicacion": 14, "tareas": 10, "terminal": 2,
             "conversacion": 0}
NUCLEO = ("nucleo/dark_nucleo.py", "DarkNucleo")
EJECUTOR_CAPACIDADES = ("herramientas/internas/ejecutor.py",
                        "EjecutorHerramientas")
MANIFEST_REL = "herramientas/internas/manifest_tools.py"

# El mapa de dueños que usa el banco: `herramientas/fabrica.py` lo deriva de estas
# tuplas, y aquí se reconstruye por su cuenta para que el test sea una fuente
# independiente. `_TOOL_A_ESPECIALISTA` del núcleo ya no existe.
HERRAMIENTAS_POR_TUPLA = {
    "codigo": HERRAMIENTAS_CODIGO,
    "comunicacion": HERRAMIENTAS_COMUNICACION,
    "tareas": HERRAMIENTAS_TAREAS,
    "terminal": HERRAMIENTAS_TERMINAL,
}


def _mapa_del_contrato():
    salida = {}
    for capacidad, tupla in HERRAMIENTAS_POR_TUPLA.items():
        for nombre in tupla:
            salida[nombre] = capacidad
    return salida


_ARBOLES = {}


def _arbol(rel):
    """AST cacheado: dark_nucleo.py son 7600 líneas y esto lo llama cada test."""
    if rel not in _ARBOLES:
        _ARBOLES[rel] = ast.parse((DARK_PYTHON / rel).read_text(encoding="utf-8"))
    return _ARBOLES[rel]


def _clase(rel, nombre):
    for nodo in ast.walk(_arbol(rel)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"clase {nombre} no encontrada en {rel}")


def _funcs(cls_ast):
    return {n.name: n for n in cls_ast.body if isinstance(n, ast.FunctionDef)}


def _herramientas(cls_ast):
    return {n[len(PREFIJO_HERRAMIENTA):] for n in _funcs(cls_ast)
            if n.startswith(PREFIJO_HERRAMIENTA)}


def _manifest():
    """El MANIFEST real, evaluado sin ejecutar la fábrica de schemas."""
    for nodo in _arbol(MANIFEST_REL).body:
        if isinstance(nodo, ast.Assign) and getattr(nodo.targets[0], "id", "") == "MANIFEST":
            return ast.literal_eval(nodo.value)
    raise AssertionError("MANIFEST no encontrado")


def _todas_las_herramientas():
    """{nombre: [dueño, ...]} sobre los 31 `tool_*` reales."""
    salida = {}
    for clave, (rel, nombre) in DUEÑOS.items():
        for h in _herramientas(_clase(rel, nombre)):
            salida.setdefault(h, []).append(clave)
    return salida


def _func(rel, clase, nombre):
    return _funcs(_clase(rel, clase))[nombre]


def _orquestador():
    """El `_ejecutar_herramienta` del núcleo: desde la Fase C solo orquesta."""
    return _func(*NUCLEO, "_ejecutar_herramienta")


def _preparador():
    """`HerramientaMontada.preparar` en el banco: la política de argumentos."""
    return _func("herramientas/banco.py", "HerramientaMontada", "preparar")


def _literales_de(nodo_ast):
    return {n.value for n in ast.walk(nodo_ast)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _descriptor_de(entrada, mapa, herramientas):
    """El descriptor con las rutas de verdad, como las calcula el banco."""
    nombre = entrada["name"]
    if nombre in HERRAMIENTAS_DEL_NUCLEO or nombre in HERRAMIENTAS_DE_CAPACIDADES:
        # Las dos listas son la MISMA ruta: nombre pelado, sin `tool_`. Lo que las
        # distingue es el dueño que define el método, no cómo se monta.
        return DescriptorHerramienta.desde_manifest(
            entrada, fuente=FUENTE_NUCLEO, resolucion=RESOLUCION_NUCLEO)
    if nombre in ALIAS_DE_NOMBRES:
        ejecutado = ALIAS_DE_NOMBRES[nombre]
        return DescriptorHerramienta.desde_manifest(
            entrada, fuente=FUENTE_ESPECIALISTA, resolucion=RESOLUCION_ALIAS,
            especialista=mapa[ejecutado],
            ejecutor=PREFIJO_HERRAMIENTA + ejecutado)
    if nombre in mapa:
        return DescriptorHerramienta.desde_manifest(
            entrada, fuente=FUENTE_ESPECIALISTA, resolucion=RESOLUCION_CONTRATO,
            especialista=mapa[nombre])
    dueños = herramientas.get(nombre, ())
    return DescriptorHerramienta.desde_manifest(
        entrada, fuente=FUENTE_ESPECIALISTA,
        resolucion=RESOLUCION_BARRIDO if dueños else RESOLUCION_CONTRATO,
        especialista=dueños[0] if dueños else None)


class PruebaContratoSoloStdlib(unittest.TestCase):
    def test_el_contrato_importa_stdlib_y_nada_mas(self):
        importados = set()
        for nodo in ast.walk(_arbol("contratos/herramienta.py")):
            if isinstance(nodo, ast.Import):
                importados.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                importados.add(nodo.module if nodo.level == 0 else "RELATIVO")
        self.assertEqual(importados, {"dataclasses", "typing"},
                         f"el contrato arrastra dependencias: {importados}")

    def test_el_contrato_no_instancia_nada_del_proyecto(self):
        """Sin esto la Fase A empezaría a importar el MANIFEST y R2 nacería acoplado."""
        tree = _arbol("contratos/herramienta.py")
        for nodo in ast.walk(tree):
            if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                mod = (nodo.module or "").split(".")[0] if nodo.level == 0 else ""
                for prohibido in ("nucleo", "especialistas", "herramientas",
                                  "modulos", "proveedores", "voz", "overlay"):
                    self.assertNotEqual(mod, prohibido,
                                        f"el contrato importa {nodo.module}")

    def test_todo_lo_que_promete_existe(self):
        for nombre in hr.__all__:
            self.assertTrue(hasattr(hr, nombre), f"__all__ miente: falta {nombre}")

    def test_el_prefijo_es_de_un_dueno_solo(self):
        self.assertEqual(PREFIJO_HERRAMIENTA, "tool_")
        from contratos import especialista as esp
        import contratos
        self.assertIs(esp.PREFIJO_HERRAMIENTA, hr.PREFIJO_HERRAMIENTA)
        self.assertIs(contratos.PREFIJO_HERRAMIENTA, hr.PREFIJO_HERRAMIENTA)


class PruebaInventarioReal(unittest.TestCase):
    def setUp(self):
        self.herramientas = _todas_las_herramientas()
        self.manifest = {e["name"]: e for e in _manifest()}

    def test_treinta_y_un_metodos_tool(self):
        self.assertEqual(len(self.herramientas), 32)  # + planificar_proyecto

    def test_el_reparto_por_dueño(self):
        for clave, esperado in POR_DUEÑO.items():
            rel, nombre = DUEÑOS[clave]
            actual = _herramientas(_clase(rel, nombre))
            self.assertEqual(len(actual), esperado,
                             f"{clave} tiene {len(actual)} herramientas, no {esperado}")

    def test_cinco_herramientas_declaradas_sin_tool_en_ningun_lado(self):
        """21 del MANIFEST - 16 que sí tienen `tool_*` = las cinco sin método propio.

        `descargar_archivo`, `abrir_en_navegador`, `guardar_sitio_web` y
        `cambiar_nombre_archivo` son del núcleo; `terminal_desarrollo` vive por
        alias.
        """
        sin_metodo = {n for n in self.manifest
                      if PREFIJO_HERRAMIENTA + n not in
                      {PREFIJO_HERRAMIENTA + x for x in self.herramientas}}
        self.assertEqual(sin_metodo, {"descargar_archivo", "terminal_desarrollo",
                                      "abrir_en_navegador", "guardar_sitio_web",
                                      "cambiar_nombre_archivo"},
                         f"el inventario cambió: {sin_metodo}")

    def test_las_quince_invisibles_al_modelo(self):
        fuera = set(self.herramientas) - set(self.manifest)
        self.assertEqual(fuera, set(INVISIBLES_AL_MODELO))
        self.assertEqual(len(INVISIBLES_AL_MODELO), 16)

    def test_la_lista_de_invisibles_no_se_repite_consigo_misma(self):
        self.assertEqual(len(INVISIBLES_AL_MODELO), len(set(INVISIBLES_AL_MODELO)))
        for nombre in INVISIBLES_AL_MODELO:
            self.assertIn(nombre, self.herramientas,
                          f"{nombre} está declarada invisible pero no existe")


class PruebaRutasDeResolucion(unittest.TestCase):
    def setUp(self):
        self.mapa = _mapa_del_contrato()
        self.nucleo = set(HERRAMIENTAS_DEL_NUCLEO)
        # La ruta del nombre pelado la comparten dos dueños desde el corte 1.
        self.sin_prefijo = self.nucleo | set(HERRAMIENTAS_DE_CAPACIDADES)
        self.herramientas = _todas_las_herramientas()

    def test_cuatro_rutas_y_su_vocabulario(self):
        self.assertEqual(hr.RESOLUCIONES,
                         (RESOLUCION_NUCLEO, RESOLUCION_CONTRATO,
                          RESOLUCION_ALIAS, RESOLUCION_BARRIDO))
        self.assertEqual(hr.FUENTES, (FUENTE_NUCLEO, FUENTE_ESPECIALISTA))

    def test_el_nucleo_reclama_seis_nombres(self):
        """La lista vive en el contrato; `_TOOLS_NUCLEO` murió con el despachador.

        Son dos listas y un mismo idioma: lo que el núcleo aún ejecuta y lo que ya
        ejecuta el módulo de capacidades. Cada nombre tiene que estar definido en
        el archivo de su dueño y en ningún otro, que es como se ve un cuerpo que
        se quedó atrás después de cambiar de manos.
        """
        self.assertEqual(self.sin_prefijo, {"descargar_archivo", "investigar",
                                            "buscar_imagenes", "abrir_en_navegador",
                                            "guardar_sitio_web",
                                            "cambiar_nombre_archivo"})
        funcs = _funcs(_clase(*NUCLEO))
        for nombre in self.nucleo:
            self.assertIn(nombre, funcs,
                          f"el contrato reclama {nombre} y el núcleo no lo define")
        ejecutor = _funcs(_clase(*EJECUTOR_CAPACIDADES))
        for nombre in HERRAMIENTAS_DE_CAPACIDADES:
            self.assertIn(nombre, ejecutor,
                          f"{nombre} es de capacidades y nadie lo define")
            self.assertNotIn(nombre, funcs,
                             f"{nombre} cambió de dueño y el núcleo lo conserva")

    def test_treinta_y_un_claves_en_el_mapa_del_contrato(self):
        """El mapa es el reparto del banco: los 31 `tool_*`, sin huecos ni inventos."""
        self.assertEqual(len(self.mapa), 32)
        for dueño in self.mapa.values():
            self.assertIn(dueño, REGISTRO_ESPECIALISTAS,
                          f"el mapa manda a {dueño!r}, que el registro no conoce")
        self.assertNotIn("terminal_desarrollo", self.mapa,
                         "no tiene `tool_*`: llega por alias, no por mapa")
        self.assertIn("terminal_desarrollo", ALIAS_DE_NOMBRES)

    def test_el_orden_de_registro_es_el_que_declara_el_contrato(self):
        """Un descriptor en `barrido` promete este orden: si el dict lo cambia, miente."""
        func = _funcs(_clase(*NUCLEO))["_registro_especialistas"]
        for nodo in ast.walk(func):
            if isinstance(nodo, ast.Return) and isinstance(nodo.value, ast.Dict):
                self.assertEqual(tuple(ast.literal_eval(k) for k in nodo.value.keys),
                                 REGISTRO_ESPECIALISTAS)
                return
        self.fail("_registro_especialistas ya no devuelve un dict literal")

    def test_el_barrido_queda_como_politica_de_respaldo(self):
        """Ningún `tool_*` real necesita ya barrer dueños: las tuplas los nombran a todos.

        La ruta sigue en el banco para el día que un especialista publique un método
        que el contrato aún no declare; si esta prueba deja de estar vacía, alguien
        añadió una herramienta sin escribirla en `contratos/especialista.py`.
        """
        self.assertEqual(sorted(n for n in self.herramientas if n not in self.mapa),
                         [])

    def test_dos_herramientas_de_comunicacion_son_codigo_muerto(self):
        """El dueño sin prefijo gana antes que el mapa.

        `investigar` y `buscar_imagenes` están en la tupla de comunicación (y por eso
        en el mapa) y existen como `tool_*`, pero el banco resuelve los seis nombres
        sin prefijo antes de mirar especialistas. Salir de esa lista los reviviría.
        """
        for nombre in ("investigar", "buscar_imagenes"):
            self.assertIn(nombre, self.mapa,
                          f"{nombre} salió de la tupla de comunicación: el código "
                          f"muerto dejó de estar sombreado")
            self.assertIn(nombre, self.sin_prefijo)
            self.assertIn(PREFIJO_HERRAMIENTA + nombre,
                          _funcs(_clase(*DUEÑOS["comunicacion"])),
                          f"tool_{nombre} fue borrado: ya no hay código muerto")

    def test_la_aritmetica_de_las_cuatro_rutas(self):
        """29 por contrato + 6 por núcleo + 2 por alias + 0 por barrido = 37 nombres.

        Con el rename de `buscar_web` a `investigar`, la tabla de alias pasó de
        un par a dos: el de `terminal_desarrollo` (nombre declarado → ejecutable
        con otro nombre) y el del nombre antiguo (nombre que ya nadie declara →
        herramienta actual). El total sube en uno porque el nombre viejo es una
        puerta más, no una herramienta más: seguía habiendo 32 ejecutables, y con
        `abrir_en_navegador` (K.3.2) son 33; `guardar_sitio_web` (K.3.5b) es el
        tercero que solo existe en el núcleo, y los deja en 34;
        `cambiar_nombre_archivo` (residuo #1) es el cuarto y el tercero del
        núcleo, y los deja en 35.

        Los 37 nombres no son 37 descriptores: `buscar_web` es una puerta que no
        se declara al modelo, así que el banco publica 36.
        """
        por_alias = set(ALIAS_DE_NOMBRES)
        por_nucleo = self.sin_prefijo
        por_contrato = {n for n in self.mapa if n not in por_nucleo}
        self.assertEqual(len(por_contrato), 30)  # + planificar_proyecto
        self.assertEqual(len(por_alias), 2)
        self.assertEqual(por_nucleo, {"descargar_archivo", "investigar",
                                      "buscar_imagenes", "abrir_en_navegador",
                                      "guardar_sitio_web",
                                      "cambiar_nombre_archivo"})
        # 38 desde que Tareas planifica proyectos (`planificar_proyecto`).
        self.assertEqual(len(por_contrato | por_nucleo | por_alias), 38)

    def test_la_resolucion_por_nucleo_no_usa_prefijo(self):
        d = DescriptorHerramienta(nombre="descargar_archivo",
                                  fuente=FUENTE_NUCLEO, resolucion=RESOLUCION_NUCLEO)
        self.assertEqual(d.ejecutor, "descargar_archivo")
        self.assertEqual(d.inconsistencias(), ())

    def test_un_alias_sin_ejecutable_se_admite_solo(self):
        """El ejecutor de un alias no se puede derivar: si falta, el descriptor avisa."""
        d = DescriptorHerramienta(nombre="pedida", resolucion=RESOLUCION_ALIAS,
                                  especialista="terminal")
        self.assertEqual(d.ejecutor, "")
        self.assertIn("resolución por alias sin ejecutable", d.inconsistencias())
        raro = DescriptorHerramienta(nombre="pedida", resolucion=RESOLUCION_ALIAS,
                                     especialista="terminal", ejecutor="sin_prefijo")
        self.assertIn("alias hacia un ejecutable sin prefijo: sin_prefijo",
                      raro.inconsistencias())


class PruebaDeQuienLeeLosCampos(unittest.TestCase):
    """Muerto el despachador, la lectura de una entrada del `MANIFEST` está repartida.

    Tres lectores y uno que ya no lee nada: el descriptor (`desde_manifest`) traduce
    la entrada a vocabulario del banco, `HerramientaMontada.preparar` arma los
    argumentos, y el núcleo solo decide si puede y delega. Si el orquestador vuelve a
    leer `params`, R2 se está deshaciendo.
    """

    def setUp(self):
        self.descriptor = _func("contratos/herramienta.py",
                                "DescriptorHerramienta", "desde_manifest")
        self.orquestador = _orquestador()
        self.preparador = _preparador()

    def test_el_descriptor_lee_los_cuatro_campos_que_declara_el_contrato(self):
        literales = _literales_de(self.descriptor)
        for campo in CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA:
            self.assertIn(campo, literales,
                          f"`{campo}` ya no se lee al describir: hay que re-escribir "
                          f"el contrato y el descriptor")

    def test_el_orquestador_no_lee_ningun_campo_del_manifest(self):
        """El núcleo pasa el contexto y el dict de argumentos; no arma la llamada."""
        literales = _literales_de(self.orquestador)
        for campo in (CAMPOS_LEIDOS_PARA_ARMAR_LA_LLAMADA
                      + CAMPOS_LEIDOS_POR_EL_ROUTER):
            self.assertNotIn(campo, literales,
                             f"el núcleo volvió a leer `{campo}` por su cuenta")

    def test_los_campos_del_router_no_se_leen_en_el_banco(self):
        """Viven en las derivaciones de manifest_tools, no en quien ejecuta."""
        for campo in CAMPOS_LEIDOS_POR_EL_ROUTER:
            self.assertNotIn(campo, _literales_de(self.preparador))

    def test_cada_campo_del_router_tiene_su_lector(self):
        """Viven en las derivaciones de manifest_tools, no en el despachador."""
        lectores = set()
        for nodo in ast.walk(_arbol(MANIFEST_REL)):
            if isinstance(nodo, ast.Subscript) and isinstance(nodo.slice, ast.Constant):
                lectores.add(nodo.slice.value)
            elif (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                  and nodo.func.attr == "get" and nodo.args
                  and isinstance(nodo.args[0], ast.Constant)):
                lectores.add(nodo.args[0].value)
        for campo in CAMPOS_LEIDOS_POR_EL_ROUTER:
            self.assertIn(campo, lectores, f"{campo} no lo consume nadie")

    def test_el_MANIFEST_no_declara_handler(self):
        for entrada in _manifest():
            self.assertNotIn("handler", entrada,
                             f"{entrada['name']} volvió a declarar `handler`")
        self.assertNotIn("handler", _literales_de(self.preparador),
                         "el banco ahora sí lee `handler`: la tabla de alias dejó de "
                         "ser la dueña del par nombre-ejecutable")

    def test_el_contrato_ya_no_publica_campos_muertos(self):
        self.assertFalse(hasattr(hr, "CAMPOS_MUERTOS"))

    def test_la_tabla_de_alias_la_declara_el_contrato_y_la_aplica_el_banco(self):
        """El viejo `ALIAS_ARGS` del despachador: hoy es vocabulario, no una copia."""
        self.assertIn("ALIAS_DE_ARGUMENTOS",
                      {n.id for n in ast.walk(self.preparador)
                       if isinstance(n, ast.Name)},
                      "el banco ya no aplica la tabla del contrato")
        for nodo in ast.walk(_arbol("herramientas/banco.py")):
            self.assertNotEqual(
                getattr(nodo.targets[0], "id", "") if isinstance(nodo, ast.Assign) else "",
                "ALIAS_ARGS", "el banco se declaró su propia tabla de renombrados")

    def test_un_alias_de_argumento_renombra_a_lo_que_un_handler_acepta(self):
        """El origen no es un parámetro declarado (si lo fuera, el renombrado iría al
        revés) y el destino sí lo acepta algún ejecutable: si no, el rename se tira
        en el descarte por firma y la tabla es decorativa."""
        declarados = set()
        for entrada in _manifest():
            declarados |= set(entrada["params"])
        firmados = set()
        for dueño, (rel, clase) in DUEÑOS.items():
            for nombre, func in _funcs(_clase(rel, clase)).items():
                if nombre.startswith(PREFIJO_HERRAMIENTA):
                    firmados |= {a.arg for a in func.args.args}
                    firmados |= {a.arg for a in func.args.kwonlyargs}
        for nombre, func in _funcs(_clase(*NUCLEO)).items():
            if nombre in HERRAMIENTAS_DEL_NUCLEO:
                firmados |= {a.arg for a in func.args.args}
        for nombre, func in _funcs(_clase(*EJECUTOR_CAPACIDADES)).items():
            if nombre in HERRAMIENTAS_DE_CAPACIDADES:
                firmados |= {a.arg for a in func.args.args}
        for origen, destino in ALIAS_DE_ARGUMENTOS.items():
            self.assertNotIn(origen, declarados, f"{origen} sí es un parámetro real")
            self.assertIn(destino, firmados,
                          f"{origen} se renombra a {destino}, que ningún ejecutable acepta")

    def test_la_llamada_es_por_palabra_clave(self):
        """`self._handler(**…argumentos)`: si algún día pasa a posicional, el descriptor
        y el banco tienen que saberlo antes de envolverse."""
        ejecutar = _func("herramientas/banco.py", "HerramientaMontada", "ejecutar")
        for nodo in ast.walk(ejecutar):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and nodo.func.attr == "_handler"):
                self.assertTrue(any(k.arg is None for k in nodo.keywords),
                                "`_handler()` dejó de llamarse con **kwargs")
                return
        self.fail("el banco ya no llama a `_handler(...)`")


class PruebaConformidadDelDescriptor(unittest.TestCase):
    """El descriptor tiene que producir el JSON que hoy ve el modelo, idéntico."""

    def setUp(self):
        import herramientas.internas.manifest_tools as tm
        self.tm = tm
        mapa = _mapa_del_contrato()
        self.herramientas = _todas_las_herramientas()
        self.entradas = _manifest()
        self.descriptores = [_descriptor_de(e, mapa, self.herramientas)
                             for e in self.entradas]

    def test_la_misma_lista_en_el_mismo_orden(self):
        self.assertEqual([d.nombre for d in self.descriptores],
                         list(self.tm.MANIFEST_BY_NAME))
        self.assertEqual(len(self.entradas), 21)

    def test_el_esquema_es_byte_a_byte_el_que_ya_se_envia(self):
        esperado = self.tm.tools_schema()
        for d, e in zip(self.descriptores, esperado):
            self.assertEqual(d.a_esquema(), e,
                             f"el descriptor de {d.nombre} ya no describe lo mismo")

    def test_el_conjunto_de_descriptores_reemplaza_al_array_completo(self):
        self.assertEqual([d.a_esquema() for d in self.descriptores],
                         self.tm.tools_schema())

    def test_descriptores_sin_inconsistencias(self):
        for d in self.descriptores:
            self.assertEqual(d.inconsistencias(), (),
                             f"{d.nombre}: {d.inconsistencias()}")

    def test_los_flags_del_enrutador_viajan(self):
        for entrada, d in zip(self.entradas, self.descriptores):
            self.assertEqual(d.respuesta_directa,
                             bool(entrada.get("respuesta_directa", False)), d.nombre)
            self.assertEqual(d.background, bool(entrada.get("background", False)),
                             d.nombre)
            self.assertEqual(d.contexto_extra,
                             bool(entrada.get("contexto_extra", False)), d.nombre)
            self.assertEqual(d.prompt_line, entrada.get("prompt_line", ""), d.nombre)
            self.assertTrue(d.visible_al_modelo, d.nombre)

    def test_keywords_muertas_ausentes_de_manifest_y_descriptor(self):
        for entrada in self.entradas:
            with self.subTest(nombre=entrada["name"]):
                self.assertNotIn("keywords", entrada)
        self.assertNotIn(
            "keywords", DescriptorHerramienta.__dataclass_fields__)

    def test_nombres_de_parametro_en_orden_de_declarcion(self):
        for entrada, d in zip(self.entradas, self.descriptores):
            self.assertEqual(d.nombres_params(), tuple(entrada["params"]), d.nombre)


class PruebaParametroAnidado(unittest.TestCase):
    def test_el_objeto_lleva_propiedades_y_bloquea_los_extras(self):
        param = ParametroHerramienta.desde(
            "args", {"type": "object", "description": "estructurados",
                     "properties": {"nombre": {"type": "string",
                                               "description": "el proceso"}}})
        esquema = param.a_esquema()
        self.assertEqual(esquema["properties"],
                         {"nombre": {"type": "string", "description": "el proceso"}})
        self.assertFalse(esquema["additionalProperties"])
        self.assertEqual(param.propiedades[0].nombre, "nombre")

    def test_sin_propiedades_no_hay_rareza_de_tipo(self):
        """Regresión: construir la sub-propiedad con positional hacia `type` un dict."""
        param = ParametroHerramienta.desde(
            "args", {"type": "object", "description": "d",
                     "properties": {"ruta": {"type": "string", "description": "r"}}})
        self.assertEqual(param.propiedades[0].tipo, "string")

    def test_enum_viaja_como_lista(self):
        param = ParametroHerramienta.desde(
            "operacion", {"type": "string", "description": "op",
                          "enum": ["espacio_disco", "estado_git"]})
        self.assertEqual(param.a_esquema()["enum"], ["espacio_disco", "estado_git"])

    def test_el_vocabulario_de_tipos_cubre_lo_que_usa_el_MANIFEST(self):
        usados = {p.tipo for e in _manifest() for p in
                  DescriptorHerramienta.desde_manifest(
                      e, fuente=FUENTE_ESPECIALISTA, resolucion=RESOLUCION_CONTRATO,
                      especialista="x").params}
        self.assertTrue(usados <= set(TIPOS_DE_PARAMETRO),
                        f"el MANIFEST usa tipos fuera del vocabulario: {usados}")


class PruebaDefectosConocidos(unittest.TestCase):
    """Lo que R2 tiene que arreglar, fijado para que no se herede en silencio."""

    def test_terminal_desarrollo_no_tiene_ejecutable_propio(self):
        """Defecto 3, cerrado por alias: el `tool_*` que se deriva del nombre no existe.

        El ejecutable real es `tool_terminal_coder` y solo se llega a él porque
        `ALIAS_DE_NOMBRES` lo declara. La Fase D borró el campo `handler` del
        `MANIFEST` (defecto 2), así que la tabla de alias es hoy el único sitio que
        sabe ese par; si alguien crea `tool_terminal_desarrollo` hay que re-leer el
        contrato.
        """
        entrada = {e["name"]: e for e in _manifest()}["terminal_desarrollo"]
        self.assertNotIn("handler", entrada,
                         "`handler` volvió al `MANIFEST`: es una clave que no lee nadie")
        self.assertEqual(ALIAS_DE_NOMBRES["terminal_desarrollo"], "terminal_coder")
        self.assertIn("terminal_coder", _mapa_del_contrato())
        self.assertNotIn("terminal_desarrollo", _mapa_del_contrato())
        self.assertNotIn(PREFIJO_HERRAMIENTA + "terminal_desarrollo",
                         _funcs(_clase(*DUEÑOS["terminal"])),
                         "alguien creó el manejador: el defecto 3 ya no existe "
                         "y hay que re-leer el contrato")

    def test_el_gate_de_la_terminal_va_por_ejecutable(self):
        """Defecto 6, cerrado en la Fase D: las dos puertas de la terminal son una.

        `terminal_desarrollo` llega por alias y `terminal_coder` por su nombre real;
        ambas montan `tool_terminal_coder`. El permiso del núcleo se comprueba contra
        el ejecutable resuelto, y el orquestador tiene que resolver ANTES de pedir
        permiso —con el orden invertido, un nombre nuevo de la misma capacidad se
        colaba sin gate, que es exactamente como se descubrió el hueco—.
        """
        self.assertEqual(EJECUTABLES_CON_GATE_DE_CODIGO, ("tool_terminal_coder",))

        def _linea_de_llamada(nodo, attr):
            return min(n.lineno for n in ast.walk(nodo)
                       if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                       and n.func.attr == attr)

        cuerpo = _orquestador()
        self.assertLess(_linea_de_llamada(cuerpo, "resolver"),
                        _linea_de_llamada(cuerpo, "_puede_usar"),
                        "el permiso volvió antes de la resolución: el gate otra vez "
                        "mira el nombre pedido y no la capacidad")

        permiso = _func(*NUCLEO, "_puede_usar")
        self.assertIn("EJECUTABLES_CON_GATE_DE_CODIGO",
                      {n.id for n in ast.walk(permiso) if isinstance(n, ast.Name)},
                      "_puede_usar dejó de consultar la tabla de capacidades")
        self.assertNotIn("terminal_desarrollo", _literales_de(permiso),
                         "_puede_usar volvió a comparar contra el nombre pedido")

    def test_el_orquestador_ya_no_empareja_por_subcadena(self):
        """Defecto 5 cerrado: el nombre se resuelve exacto y, si no, tool_not_found."""
        self.assertIn("resolver", {n.func.attr for n in ast.walk(_orquestador())
                                   if isinstance(n, ast.Call)
                                   and isinstance(n.func, ast.Attribute)})
        self.assertIn("tool_not_found:", _literales_de(_orquestador()))
        nucleo = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8")
        self.assertNotIn("MANIFEST_BY_NAME", nucleo,
                         "el núcleo volvió a buscar herramientas por su cuenta")

    def test_la_tabla_de_alias_solo_apunta_a_ejecutables_reales(self):
        """Defecto 5, ya resuelto por diseño: la traducción de nombres es una tabla.

        El emparejamiento difuso aceptaba cualquier subcadena; un alias solo puede
        declarar un nombre hacia algo que existe en el banco.

        Con `buscar_web` → `investigar` la tabla admitió un segundo tipo de origen:
        el de un nombre que ya NO está declarado al modelo porque la herramienta
        cambió de sitio. Lo que sigue siendo obligatorio es el destino —una
        herramienta que alguien implementa— y que no haya cadenas de alias.
        """
        nombres = {e["name"] for e in _manifest()}
        herramientas = _todas_las_herramientas()
        self.assertEqual(ALIAS_DE_NOMBRES, {
            "terminal_desarrollo": "terminal_coder",
            "buscar_web": "investigar",
        })
        for origen, destino in ALIAS_DE_NOMBRES.items():
            self.assertIn(
                destino, herramientas,
                f"el alias {origen} apunta a {destino}, que nadie implementa")
            self.assertNotIn(
                origen, ALIAS_DE_NOMBRES.values(),
                f"alias encadenado: {origen} es destino de otro alias")
        # Los origenes declarados siguen siendolo; los retirados no pueden volver
        # al MANIFEST sin quitar antes su fila de la tabla.
        declarados = {o for o in ALIAS_DE_NOMBRES if o in nombres}
        self.assertEqual(declarados, {"terminal_desarrollo"})
        self.assertNotIn("buscar_web", nombres)

    def test_el_alias_no_puede_perder_un_argumento_declarado(self):
        """`terminal_desarrollo` se ejecuta como `tool_terminal_coder`: la firma del
        destino tiene que aceptar todo lo que el origen declara al modelo."""
        entrada = {e["name"]: e for e in _manifest()}["terminal_desarrollo"]
        ejecutable = PREFIJO_HERRAMIENTA + ALIAS_DE_NOMBRES["terminal_desarrollo"]
        firma = _funcs(_clase(*DUEÑOS["terminal"]))[ejecutable]
        aceptados = {a.arg for a in firma.args.args}
        declarados = set(entrada["params"]) | set(entrada.get("defaults", {}))
        self.assertTrue(declarados <= aceptados,
                        f"{sorted(declarados - aceptados)} no lo acepta {ejecutable}")


class PruebaPuertosEstadoDiana(unittest.TestCase):
    def test_son_protocols_comprobables_en_tiempo_de_ejecucion(self):
        self.assertTrue(PuertoHerramienta._is_runtime_protocol)
        self.assertTrue(PuertoBancoHerramientas._is_runtime_protocol)

    def test_un_doble_fabricado_cumple_la_forma(self):
        class HerramientaDoble:
            def __init__(self, descriptor):
                self.descriptor = descriptor

            def ejecutar(self, argumentos, contexto=None):
                return ("ok", argumentos, contexto)

        d = DescriptorHerramienta(nombre="demo",
                                 resolucion=RESOLUCION_BARRIDO,
                                 especialista="comunicacion")
        self.assertIsInstance(HerramientaDoble(d), PuertoHerramienta)

    def test_el_banco_es_el_unico_que_nombra_los_puertos_fuera_de_contratos(self):
        """Fase B: el banco puede citarlos; el núcleo y los especialistas no.

        Si mañana `dark_nucleo.py` empieza a hablar de `PuertoHerramienta` antes de
        la Fase C, alguien está mezclando los dos despachos.
        """
        diana = DARK_PYTHON / "herramientas" / "banco.py"
        for ruta in DARK_PYTHON.rglob("*.py"):
            if "__pycache__" in ruta.parts or "contratos" in ruta.parts:
                continue
            texto = ruta.read_text(encoding="utf-8")
            nombra = ("PuertoHerramienta" in texto
                      or "PuertoBancoHerramientas" in texto)
            self.assertEqual(nombra, ruta == diana,
                             f"{ruta.name} nombra los puertos diana")

    def test_el_nucleo_ya_pasa_por_el_banco_y_el_reflejo_murió(self):
        """El estado real tras la Fase C: una sola puerta, y el núcleo la abre."""
        self.assertTrue((DARK_PYTHON / "herramientas" / "banco.py").exists())
        self.assertTrue((DARK_PYTHON / "herramientas" / "fabrica.py").exists())
        nucleo = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(
            encoding="utf-8")
        self.assertIn("crear_banco", nucleo)
        self.assertIn("herramientas import fabrica as banco_fabrica", nucleo)
        for muerto in ("_TOOL_A_ESPECIALISTA", "_TOOLS_NUCLEO"):
            self.assertNotIn(muerto, nucleo,
                             f"{muerto} volvió al núcleo: hay dos despachos otra vez")
        for nodo in ast.walk(_orquestador()):
            if isinstance(nodo, ast.Call):
                self.assertNotEqual(
                    getattr(nodo.func, "attr", ""), "getattr",
                    "el orquestador volvió a resolver handlers por reflejo")


if __name__ == "__main__":
    unittest.main(verbosity=2)
