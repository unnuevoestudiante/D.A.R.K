"""R3 Fase A: un puerto por especialista, y que el puerto diga la verdad.

Los cinco especialistas ya existen como sistemas separados; lo que no existe es
el contrato. Este archivo fija, leyendo los fuentes reales con AST (sin
instanciar nada: los constructores arrastran VLC, Ollama y disco), tres cosas:

  * la superficie de cada `Puerto*` es exactamente lo que el núcleo llama hoy;
  * las tuplas `HERRAMIENTAS_*` coinciden con los `tool_*` realmente definidos y
    con el mapa que `herramientas/fabrica.py` le da al banco — desde la Fase C de
    R2 el `_TOOL_A_ESPECIALISTA` del despachador ya no existe;
  * las dos fugas documentadas en `contratos/especialista.py` siguen mididas: el
    `terminal_desarrollo` declarado sin manejador, que hoy cierra
    `ALIAS_DE_NOMBRES`, y el `temas` que el núcleo atraviesa hasta GestorContexto,
    que sigue abierto.

Ref: contratos/especialista.py, contratos/herramienta.py, herramientas/fabrica.py,
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

from contratos import especialista as esp  # noqa: E402
from contratos.especialista import (  # noqa: E402
    PREFIJO_HERRAMIENTA,
    HERRAMIENTAS_CODIGO,
    HERRAMIENTAS_COMUNICACION,
    HERRAMIENTAS_TAREAS,
    HERRAMIENTAS_TERMINAL,
    PuertoCodigo,
    PuertoComunicacion,
    PuertoConversacion,
    PuertoEspecialista,
    PuertoTareas,
    PuertoTerminal,
)
from contratos.herramienta import (  # noqa: E402
    ALIAS_DE_NOMBRES,
    HERRAMIENTAS_DEL_NUCLEO,
    HERRAMIENTAS_DE_CAPACIDADES,
)
from herramientas.fabrica import mapa_de_dueños  # noqa: E402

# (archivo, clase real que implementa el puerto)
FUENTES = {
    "codigo": ("especialistas/especialista_codigo.py", "EspecialistaCodigo", PuertoCodigo),
    "comunicacion": ("especialistas/especialista_comunicacion.py",
                     "EspecialistaComunicacion", PuertoComunicacion),
    "tareas": ("especialistas/especialista_tareas.py", "EspecialistaTareas", PuertoTareas),
    "conversacion": ("especialistas/especialista_conversacional.py",
                     "EspecialistaConversacional", PuertoConversacion),
    "terminal": ("herramientas/externas/terminal.py", "DarkTerminal", PuertoTerminal),
}
HERRAMIENTAS = {
    "codigo": HERRAMIENTAS_CODIGO,
    "comunicacion": HERRAMIENTAS_COMUNICACION,
    "tareas": HERRAMIENTAS_TAREAS,
    "terminal": HERRAMIENTAS_TERMINAL,
    "conversacion": (),
}
NUCLEO = ("nucleo/dark_nucleo.py", "DarkNucleo")


def _arbol(rel):
    return ast.parse((DARK_PYTHON / rel).read_text(encoding="utf-8"))


def _clase(rel, nombre):
    for nodo in ast.walk(_arbol(rel)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"clase {nombre} no encontrada en {rel}")


def _funcs(clase_ast):
    return {n.name: n for n in clase_ast.body if isinstance(n, ast.FunctionDef)}


def _firma(fn_ast):
    """(posicionales, kwonly, defaults) como texto, para comparar sin tipos."""
    a = fn_ast.args
    pos = [x.arg for x in a.posonlyargs + a.args]
    kw = [x.arg for x in a.kwonlyargs]
    def _v(d):
        return ast.dump(d)
    defs = [_v(d) for d in a.defaults]
    kwdefs = {k: _v(v) for k, v in zip(a.kw_defaults, kw)}
    extras = []
    if a.vararg:
        extras.append("*" + a.vararg.arg)
    if a.kwarg:
        extras.append("**" + a.kwarg.arg)
    return pos, kw, defs, kwdefs, extras


def _es_property(fn_ast):
    return any(isinstance(d, ast.Name) and d.id == "property"
               for d in fn_ast.decorator_list)


def _herramientas(clase_ast):
    return {n[len(PREFIJO_HERRAMIENTA):]
            for n, f in _funcs(clase_ast).items()
            if n.startswith(PREFIJO_HERRAMIENTA)}


def _llamada_nucleo(nombre_func):
    """La llamada `esp_fabrica.<nombre_func>(...)` dentro del núcleo.

    Antes de la Fase B estas búsquedas iban contra el nombre de la clase; ahora
    el núcleo compone por la fábrica y la única forma de seguir midiendo el
    cableado real es leer la llamada.
    """
    for nodo in ast.walk(_clase(*NUCLEO)):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == nombre_func):
            return nodo
    raise AssertionError(f"el núcleo ya no llama a {nombre_func}")


class PruebaContratoSoloStdlib(unittest.TestCase):
    def test_only_typing_import(self):
        """La única dependencia absoluta es `typing`.

        Desde R2 Fase A hay además un hermanito relativo permitido:
        `from .herramienta import PREFIJO_HERRAMIENTA`, para que la convención
        `tool_` tenga un solo dueño. Desde R4 Fase C se suma `.manager`, porque
        `PuertoTareas.obtener_tareas()` dejó de devolver el dict crudo del Task
        Manager y devuelve `Tarea`: el tipo del dato lo sigue definiendo el contrato
        del servidor, no el del especialista. Cualquier otro import relativo aquí
        habría que ir a buscarlo al contrato implicado.
        """
        tree = _arbol("contratos/especialista.py")
        importados = set()
        relativos = set()
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.Import):
                importados.update(a.name.split(".")[0] for a in nodo.names)
            elif isinstance(nodo, ast.ImportFrom):
                if nodo.level == 0:
                    importados.add(nodo.module or "")
                else:
                    relativos.add(nodo.module or "")
        # Solo biblioteca estándar: `typing` para los puertos y, desde que el
        # contrato lee y escribe la especificación de Tareas → Coder, lo justo
        # para parser de texto y comparar cifras exactas. Un módulo se añade aquí a conciencia.
        self.assertEqual(importados, {"typing", "dataclasses", "re", "unicodedata", "decimal"},
                         f"el contrato arrastra dependencias: {importados}")
        self.assertEqual(relativos, {"herramienta", "manager"},
                         f"el contrato importa otros hermanos: {relativos}")

    def test_ningun_contrato_importa_el_proyecto(self):
        for p in sorted((DARK_PYTHON / "contratos").glob("*.py")):
            for nodo in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
                if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                    if isinstance(nodo, ast.ImportFrom) and nodo.level:
                        continue
                    # `import x` no tiene `.module`: sus nombres van en `names`.
                    modulos = ([nodo.module or ""] if isinstance(nodo, ast.ImportFrom)
                               else [a.name for a in nodo.names])
                    for mod in modulos:
                        for prohibido in ("nucleo", "especialistas", "herramientas",
                                          "modulos", "proveedores", "voz", "overlay",
                                          "acceso"):
                            self.assertFalse(
                                mod.split(".")[0] == prohibido,
                                f"{p.name} importa {mod}: los puertos no conocen motores")

    def test_prefijo_es_el_de_la_convencion(self):
        self.assertEqual(PREFIJO_HERRAMIENTA, "tool_")
        for nombre in (HERRAMIENTAS_CODIGO + HERRAMIENTAS_COMUNICACION
                       + HERRAMIENTAS_TAREAS + HERRAMIENTAS_TERMINAL):
            self.assertFalse(nombre.startswith(PREFIJO_HERRAMIENTA),
                             f"{nombre}: las tuplas llevan el nombre SIN prefijo, "
                             f"que es como lo pide el LLM")


class PruebaReexportos(unittest.TestCase):
    def test_todo_lo_que_promete_existe(self):
        for nombre in esp.__all__:
            self.assertTrue(hasattr(esp, nombre), f"__all__ miente: falta {nombre}")

    def test_el_paquete_reexporta_el_mismo_objeto(self):
        import contratos
        for nombre in esp.__all__:
            self.assertIs(getattr(contratos, nombre), getattr(esp, nombre),
                          f"contratos.{nombre} es otro objeto")

    def test_los_seis_puertos_y_cuatro_tuplas_estan_en_all(self):
        esperado = {"PuertoEspecialista", "PuertoCodigo", "PuertoComunicacion",
                    "PuertoConversacion", "PuertoTareas", "PuertoTerminal",
                    "HERRAMIENTAS_CODIGO", "HERRAMIENTAS_COMUNICACION",
                    "HERRAMIENTAS_TAREAS", "HERRAMIENTAS_TERMINAL",
                    "PREFIJO_HERRAMIENTA",
                    # el traspaso Tareas → Coder
                    "MARCA_SUPUESTO", "STACKS", "SeccionEspecificacion",
                    "SECCIONES_ESPECIFICACION", "Especificacion", "leer_especificacion",
                    "escribir_especificacion", "huecos_especificacion",
                    # el mundo que el coder compone para el motor inmersivo
                    "OBJETOS_INMERSIVOS", "VARIANTES", "AMBIENTES", "RECORRIDOS", "TIPOGRAFIAS", "CARACTERES_SONIDO",
                    "FRASES_DE_RELLENO", "contraste", "validar_mundo", "ESTILO",
                    # el mundo que el coder compone para el kit de apps de React
                    "NAVEGACIONES", "BLOQUES_APP", "validar_app"}
        self.assertEqual(set(esp.__all__), esperado)

    def test_tuplas_sin_repetidos(self):
        for nombre, tupla in (("codigo", HERRAMIENTAS_CODIGO),
                              ("comunicacion", HERRAMIENTAS_COMUNICACION),
                              ("tareas", HERRAMIENTAS_TAREAS),
                              ("terminal", HERRAMIENTAS_TERMINAL)):
            self.assertEqual(len(tupla), len(set(tupla)),
                             f"HERRAMIENTAS_{nombre.upper()} tiene duplicados")


class PruebaSuperficieDeHerramientas(unittest.TestCase):
    def test_cada_tupla_contra_el_source(self):
        for clave, (rel, clase, _) in FUENTES.items():
            con = _herramientas(_clase(rel, clase))
            self.assertEqual(con, set(HERRAMIENTAS[clave]),
                             f"{rel}: la tupla del contrato ya no describe los "
                             f"`tool_*` reales (solo en tupla: "
                             f"{sorted(con ^ set(HERRAMIENTAS[clave]))})")

    def test_total_de_herramientas_resolubles(self):
        todas = set()
        for clave, (rel, clase, _) in FUENTES.items():
            todas |= _herramientas(_clase(rel, clase))
        self.assertEqual(len(todas), 32)  # + planificar_proyecto (plan-coder-v2)
        self.assertNotIn("terminal_desarrollo", todas)

    def test_conversacion_no_atiende_herramientas(self):
        rel, clase, _ = FUENTES["conversacion"]
        self.assertEqual(_herramientas(_clase(rel, clase)), set())

    def test_puerto_especialista_es_un_marcador(self):
        """No se pueden declarar métodos de nombre dinámico: la base es solo
        documental, existe para nombrar la convención, no para filtrar."""
        self.assertEqual(
            set(_funcs(_clase("contratos/especialista.py",
                              "PuertoEspecialista"))), set())
        self.assertTrue(isinstance(object(), PuertoEspecialista))

    def test_el_mapa_del_banco_coincide_con_las_tuplas(self):
        """Desde la Fase C el mapa lo deriva `herramientas/fabrica.py` de estas
        tuplas: si manda a un dueño, tiene que ser el que declara el `tool_*`.
        `_TOOL_A_ESPECIALISTA` del despachador ya no existe; aquí no se consulta."""
        mapa = mapa_de_dueños()
        dueño = self._dueño_por_tupla()
        self.assertEqual(len(mapa), 32)
        for nombre, destino in mapa.items():
            self.assertIn(nombre, dueño,
                          f"{nombre}: el mapa lo manda a {destino} y ningún "
                          f"especialista define `tool_{nombre}`")
            self.assertEqual(destino, dueño[nombre],
                             f"{nombre}: el mapa dice {destino}, el método está "
                             f"en {dueño[nombre]}")
        self.assertEqual(set(mapa) - set(dueño), set())
        self.assertNotIn("terminal_desarrollo", mapa,
                         "no tiene `tool_*`: llega por alias, no por mapa")

    def test_ya_no_hay_herramientas_que_viajen_por_barrido(self):
        """El barrido era la ruta de los nueve nombres sin mapa; hoy las tuplas los
        declaran todos y la ruta queda como respaldo de fábrica."""
        self.assertEqual(
            sorted(set(self._dueño_por_tupla()) - set(mapa_de_dueños())), [],
            "algún `tool_*` volvió a vivir solo del barrido: hay que escribirlo "
            "en `contratos/especialista.py`")

    def test_seis_nombres_sombra_el_nucleo(self):
        """La ruta pelada se resuelve antes que el mapa: gana el atributo del dueño
        sin prefijo y el `tool_*` del especialista queda como código muerto.

        Desde el corte 1 son dos dueños los que cobran por nombre pelado (el
        núcleo y el módulo de capacidades), así que la cuenta de seis se lee en las
        dos listas del contrato.
        """
        nucleo = set(HERRAMIENTAS_DEL_NUCLEO)
        sin_prefijo = nucleo | set(HERRAMIENTAS_DE_CAPACIDADES)
        self.assertEqual(sin_prefijo, {"descargar_archivo", "investigar",
                                       "buscar_imagenes", "abrir_en_navegador",
                                       "guardar_sitio_web",
                                       "cambiar_nombre_archivo"})
        funcs = _funcs(_clase(*NUCLEO))
        for nombre in nucleo:
            self.assertIn(nombre, funcs,
                          f"el contrato reclama {nombre} y el núcleo no lo define")
        for nombre in ("investigar", "buscar_imagenes"):
            self.assertIn(nombre, mapa_de_dueños(),
                          f"{nombre} salió de la tupla de comunicación: el código "
                          f"muerto dejó de estar sombreado")
            self.assertIn(PREFIJO_HERRAMIENTA + nombre,
                          _funcs(_clase(*FUENTES["comunicacion"][:2])))

    @staticmethod
    def _dueño_por_tupla():
        dueño = {}
        for clave, tupla in HERRAMIENTAS.items():
            for nombre in tupla:
                dueño[nombre] = clave
        return dueño


class PruebaManifiesto(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(DARK_PYTHON))
        from herramientas.internas import manifest_tools
        self.manifest = {e["name"] for e in manifest_tools.MANIFEST}

    def test_cada_nombre_del_manifest_resuelve_algo(self):
        """Cerrada la fuga: las 21 entradas del `MANIFEST` tienen ejecutable, mapa,
        núcleo o alias.
        """
        todas = set()
        for clave, (rel, clase, _) in FUENTES.items():
            todas |= _herramientas(_clase(rel, clase))
        roto = (self.manifest - todas - set(HERRAMIENTAS_DEL_NUCLEO)
                - set(HERRAMIENTAS_DE_CAPACIDADES) - set(ALIAS_DE_NOMBRES))
        self.assertEqual(roto, set(),
                         f"herramientas declaradas al LLM sin ningún sitio donde "
                         f"caer: {sorted(roto)}")

    def test_terminal_desarrollo_llega_por_alias(self):
        """El `MANIFEST` promete un ejecutable que no existe: lo cierra la tabla.

        La Fase D borró el campo `handler` que documentaba ese par; `ALIAS_DE_NOMBRES`
        es desde entonces el único sitio que lo declara.
        """
        from herramientas.internas import manifest_tools
        entrada = {e["name"]: e for e in manifest_tools.MANIFEST}["terminal_desarrollo"]
        self.assertNotIn("handler", entrada,
                         "`handler` volvió al `MANIFEST`: hay una clave sin lector")
        rel, clase = FUENTES["terminal"][0], FUENTES["terminal"][1]
        self.assertNotIn("terminal_desarrollo", _herramientas(_clase(rel, clase)))
        self.assertEqual(ALIAS_DE_NOMBRES["terminal_desarrollo"], "terminal_coder")
        self.assertEqual(mapa_de_dueños()["terminal_coder"], "terminal")

    def test_el_orquestador_no_resuelve_nombres(self):
        """Fase C: el núcleo ya ni lee `handler` ni arma el `tool_*`; eso es del banco."""
        func = _funcs(_clase(*NUCLEO))["_ejecutar_herramienta"]
        literales = {n.value for n in ast.walk(func)
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertNotIn("handler", literales,
                         "el orquestador ahora sí lee `handler`: las tuplas del "
                         "contrato y `terminal_desarrollo` cambian de significado")
        self.assertNotIn(PREFIJO_HERRAMIENTA, literales,
                         "el núcleo volvió a resolver por convención `tool_*`")

    def test_quedan_herramientas_invisibles_al_llm(self):
        todas = set()
        for clave, (rel, clase, _) in FUENTES.items():
            todas |= _herramientas(_clase(rel, clase))
        fuera = todas - self.manifest
        self.assertEqual(len(fuera), 16)
        self.assertIn("terminal_coder", fuera)
        self.assertIn("listar_tareas", fuera)
        self.assertIn("crear_tarea", fuera)


class PruebaConformidadDeLosPuertos(unittest.TestCase):
    """La firma del puerto tiene que ser la del código real, sin instanciar."""

    def _comparar(self, puerto, rel, clase_nombre):
        reales = _funcs(_clase(rel, clase_nombre))
        puerto_ast = _clase("contratos/especialista.py", puerto.__name__)
        faltan = []
        for nombre, esperado in _funcs(puerto_ast).items():
            if nombre == "__init__" or _es_property(esperado):
                # Un property del puerto es un atributo de instancia en el
                # especialista: se comprueba aparte, en su propio test.
                continue
            real = reales.get(nombre)
            if real is None:
                faltan.append(nombre)
                continue
            self.assertEqual(_firma(real)[:3], _firma(esperado)[:3],
                             f"{clase_nombre}.{nombre}: la firma real "
                             f"{_firma(real)[:3]} != la del puerto "
                             f"{_firma(esperado)[:3]}")
        self.assertEqual(faltan, [],
                         f"{clase_nombre} no implementa {faltan} del puerto")

    def test_puerto_codigo(self):
        self._comparar(PuertoCodigo, *FUENTES["codigo"][:2])

    def test_puerto_comunicacion(self):
        self._comparar(PuertoComunicacion, *FUENTES["comunicacion"][:2])

    def test_puerto_tareas(self):
        self._comparar(PuertoTareas, *FUENTES["tareas"][:2])

    def test_puerto_terminal(self):
        self._comparar(PuertoTerminal, *FUENTES["terminal"][:2])

    def test_puerto_conversacion(self):
        self._comparar(PuertoConversacion, *FUENTES["conversacion"][:2])

    def test_temas_es_attributo_del_especialista(self):
        """La fuga del puerto: `self.temas` lo pone el __init__, no es property."""
        rel, clase, _ = FUENTES["conversacion"]
        init = _funcs(_clase(rel, clase))["__init__"]
        asignados = set()
        for nodo in ast.walk(init):
            if isinstance(nodo, ast.Attribute) and isinstance(nodo.ctx, ast.Store):
                asignados.add(nodo.attr)
        self.assertIn("temas", asignados)

    def test_puertos_son_runtime_checkable(self):
        class DobleConversacion:
            temas = object()

            def saludar_inicio(self): ...
            def solicitar_creacion_contrasena(self): ...
            def marcar_inicio_sesion(self): ...
            def procesar_turno(self, texto, desde_modulo=False): ...

        class DobleTareas:
            def obtener_tareas(self): return {}
            def crear_tarea(self, descripcion, prioridad=2, modulo=0, pasos=None): ...
            def iniciar_tarea(self, tarea_id): ...

        self.assertIsInstance(DobleConversacion(), PuertoConversacion)
        self.assertIsInstance(DobleTareas(), PuertoTareas)
        self.assertNotIsInstance(object(), PuertoTareas)


class PruebaAcoplamientoInvertido(unittest.TestCase):
    """Lo que cada especialista recibe del núcleo: la deuda que mira la Fase C."""

    def test_tres_especialistas_aceptan_kwargs_sobrantes(self):
        """Permite repartir un mismo contexto sin que nadie reviente."""
        for clave in ("codigo", "comunicacion", "tareas"):
            rel, clase, _ = FUENTES[clave]
            _, _, _, _, extras = _firma(_funcs(_clase(rel, clase))["__init__"])
            self.assertIn("**_kwargs", extras, f"{clase} dejó de tragar kwargs")

    def test_conversacion_y_terminal_no(self):
        for clave in ("conversacion", "terminal"):
            rel, clase, _ = FUENTES[clave]
            _, _, _, _, extras = _firma(_funcs(_clase(rel, clase))["__init__"])
            self.assertNotIn("**_kwargs", extras,
                             f"{clase} ahora sí traga kwargs: la fábrica puede "
                             f"pasarle un contexto común")

    def test_conversacion_recibe_el_router(self):
        """La fuga inversa: el núcleo se inyecta a sí mismo (`router=self`)."""
        rel, clase, _ = FUENTES["conversacion"]
        pos, _, _, _, _ = _firma(_funcs(_clase(rel, clase))["__init__"])
        self.assertEqual(pos[:2], ["self", "router"])
        # Desde la Fase B el núcleo no nombra la clase: la construye la fábrica,
        # así que se busca la llamada `esp_fabrica.crear_especialista_conversacion`.
        construccion = _llamada_nucleo("crear_especialista_conversacion")
        router = next(k for k in construccion.keywords if k.arg == "router")
        self.assertIsInstance(router.value, ast.Name)
        self.assertEqual(router.value.id, "self",
                         "`router` ya no es el núcleo: la Fase C puede cerrar la fuga")

    def test_metodos_del_nucleo_que_conversacion_usa(self):
        """`router=self`: si el núcleo borra uno de estos, el puerto miente."""
        rel, clase, _ = FUENTES["conversacion"]
        reales = _funcs(_clase(*NUCLEO))
        usados = set()
        for nodo in ast.walk(_clase(rel, clase)):
            if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                    and isinstance(nodo.func.value, ast.Attribute)
                    and nodo.func.value.attr == "router"):
                usados.add(nodo.func.attr)
        self.assertEqual(usados, {
            "cancelar_tarea_bg_si_activa", "ejecutar_comando",
            "encolar_tarea_con_callback", "es_loop_degenerado",
            "interrupcion_pedida", "limpiar_interrupcion"},
            "cambió la lista de las 6 capacidades que conversación pide al núcleo "
            "(Fase C: convertirlas en un puerto y cerrar router=self)")
        for nombre in sorted(usados):
            self.assertIn(nombre, reales,
                          f"conversacion llama a router.{nombre} y el núcleo no lo tiene")

    def test_tareas_recibe_callbacks_no_el_nucleo(self):
        """El especialista de tareas no ve DarkNucleo: ve funciones sueltas."""
        rel, clase, _ = FUENTES["tareas"]
        pos, _, _, _, _ = _firma(_funcs(_clase(rel, clase))["__init__"])
        self.assertIn("helpers", pos)
        self.assertNotIn("router", pos,
                         "tareas recibió el núcleo entero: la fábrica tiene que "
                         "seguir pasando capacidades, no el router")
        dict_helpers = self._kw_de_construccion("esp_tareas", "helpers")
        claves = {ast.literal_eval(k) for k in dict_helpers.keys}
        self.assertEqual(claves, {
            "cargar_partial", "decir_filler", "guardar_partial",
            "llm_pedido_chat", "resolver_ruta", "ruta_permitida",
            "sanear_nombre", "tarea_bg_cancel", "filtrar_voz", "pregunta_hueco"},
            "cambió la lista de las 10 capacidades que tareas pide al núcleo; las "
            "cuatro de sub-pasos que había aquí antes las borró la R4 Fase C2 porque "
            "nadie las llamaba, y `buscar_resultados_web`/`obtener_texto_pagina` se "
            "fueron con la isla web del núcleo: ningún lector las leía y el único "
            "dueño de esas dos capacidades es el ejecutor")
        self.assertEqual(len(dict_helpers.values), len(claves))

    def test_registro_de_especialistas_sin_conversacion(self):
        func = _funcs(_clase(*NUCLEO))["_registro_especialistas"]
        devuelto = next(n for n in ast.walk(func)
                        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))
        claves = {ast.literal_eval(k) for k in devuelto.value.keys}
        self.assertEqual(claves, {"codigo", "comunicacion", "tareas", "terminal"},
                         "conversacion no atiende herramientas: si entra aquí, "
                         "las tuplas del contrato tienen que recontarse")

    @staticmethod
    def _kw_de_construccion(atributo, nombre_kw):
        """El dict literal pasado como `nombre_kw` al construir self.<atributo>."""
        construccion = _llamada_nucleo("crear_especialista_tareas")
        for kw in construccion.keywords:
            if kw.arg == nombre_kw and isinstance(kw.value, ast.Dict):
                return kw.value
        raise AssertionError(f"no encontré {nombre_kw}={{...}} en la "
                             f"construcción de self.{atributo}")


# =========================================================================
#  ESPECIFICACIÓN: el MD que Tareas escribe y el Coder adopta
# =========================================================================

COMPLETA = """# Especificación: Diario de gastos

## 1. Visión
Una app para anotar gastos del hogar y ver en qué se va el dinero.

## 2. Usuarios y escenarios
Una pareja que anota cada compra desde el móvil al salir de la tienda.

## 3. Pantallas y flujo
- Inicio: total del mes y últimos gastos.
- Nuevo gasto: importe, categoría y nota.

## 4. Datos
Gasto: importe, categoría, fecha y nota; en localStorage.

## 5. Funcionalidades
- MVP: anotar y listar gastos.
- Después: gráficas por categoría.

## 6. Dirección visual
Sobria, densa, tipografía con cifras tabulares. [supuesto] Tema oscuro.

## 7. Stack
React con Vite, porque hay estado y varias vistas.

## 8. Criterios de aceptación
- Un gasto anotado sigue ahí al recargar.

## 9. Fuera de alcance
Cuentas de usuario y sincronización.
"""


class PruebaEspecificacion(unittest.TestCase):
    def test_lee_las_nueve_secciones_y_no_quedan_huecos(self):
        e = esp.leer_especificacion(COMPLETA)
        self.assertEqual(e.titulo, "Diario de gastos")
        self.assertEqual(len(e.secciones), 9)
        self.assertEqual(esp.huecos_especificacion(e), ())
        self.assertEqual(e.stack(), "react")
        self.assertEqual(e.supuestos(), ("Sobria, densa, tipografía con cifras tabulares. Tema oscuro.",))

    def test_el_md_escrito_se_vuelve_a_leer_igual(self):
        e = esp.leer_especificacion(COMPLETA)
        reescrito = esp.escribir_especificacion(e)
        self.assertEqual(esp.leer_especificacion(reescrito), e)
        self.assertEqual(esp.escribir_especificacion(esp.leer_especificacion(reescrito)), reescrito)

    def test_tolera_titulos_sin_numero_ni_acentos_ni_mayusculas(self):
        e = esp.leer_especificacion("## vision\nAlgo\n\n## DIRECCION VISUAL\nClara")
        self.assertEqual(e.seccion("vision"), "Algo")
        self.assertEqual(e.seccion("visual"), "Clara")

    def test_una_seccion_desconocida_no_se_pierde(self):
        e = esp.leer_especificacion(COMPLETA + "\n## Notas de la reunión\nLlamar a Ana.\n")
        self.assertEqual(e.extra, (("Notas de la reunión", "Llamar a Ana."),))
        self.assertIn("## Notas de la reunión\n\nLlamar a Ana.", esp.escribir_especificacion(e))

    def test_los_huecos_salen_en_orden_y_con_motivo(self):
        e = esp.leer_especificacion(
            "# App\n## Visión\nAlgo\n## Pantallas y flujo\nUna sola pantalla\n"
            "## Stack\nLo que sea más rápido\n")
        huecos = dict(esp.huecos_especificacion(e))
        self.assertEqual(huecos["pantallas"], "necesita una lista")
        self.assertIn("no nombra un stack", huecos["stack"])
        self.assertEqual(huecos["usuarios"], "vacía")
        self.assertNotIn("vision", huecos)
        claves = [c for c, _ in esp.huecos_especificacion(e)]
        orden = [s.clave for s in esp.SECCIONES_ESPECIFICACION]
        self.assertEqual(claves, sorted(claves, key=orden.index))

    def test_un_pendiente_escrito_sigue_siendo_un_hueco(self):
        vacia = esp.escribir_especificacion(esp.Especificacion(titulo="Nada"))
        self.assertIn("_Pendiente:", vacia)
        self.assertEqual(len(esp.huecos_especificacion(esp.leer_especificacion(vacia))), 9)

    def test_con_seccion_rehace_una_sin_tocar_el_resto(self):
        e = esp.leer_especificacion(COMPLETA)
        nueva = e.con_seccion("stack", "Vanilla: se abre con doble clic.")
        self.assertEqual(nueva.stack(), "vanilla")
        self.assertEqual(e.stack(), "react", "la original no cambia")
        with self.assertRaises(KeyError):
            e.con_seccion("inventada", "x")

    def test_titulos_alternativos_solo_si_nombran_una_seccion(self):
        """Un lote real de Groq (25-11-2026) llegó con títulos que el lector no veía."""
        md = "\n".join([
            "## 1. Visión", "**Visión general:** algo que no es título.",
            "### Fase 1", "sigue siendo visión",
            "### 7. Stack tecnológico:", "React con Vite.",
            "**8. Criterios de aceptación (MVP)**", "- Guarda al recargar.",
            "## Fuera de alcance:", "Nada de nube.",
        ])
        e = esp.leer_especificacion(md)
        self.assertEqual(e.seccion("vision"), "**Visión general:** algo que no es título.\n"
                                              "### Fase 1\nsigue siendo visión")
        self.assertEqual(e.seccion("stack"), "React con Vite.")
        self.assertEqual(e.seccion("criterios"), "- Guarda al recargar.")
        self.assertEqual(e.seccion("fuera_de_alcance"), "Nada de nube.")
        self.assertEqual(e.extra, ())

    def test_el_stack_acepta_como_lo_escriben_los_modelos(self):
        def stack(texto):
            return esp.Especificacion(secciones={"stack": texto}).stack()
        self.assertEqual(stack("Vite + TypeScript, con componentes."), "react")
        self.assertEqual(stack("HTML, CSS y JavaScript sin framework."), "vanilla")
        self.assertEqual(stack("Una herramienta con Tkinter."), "python")
        self.assertEqual(stack("React con Vite; vanilla no alcanzaría."), "react",
                         "gana la primera mención")
        self.assertEqual(stack("Lo que sea más rápido"), "")

    def test_cada_seccion_trae_su_pregunta_para_el_modo_guiado(self):
        claves = [s.clave for s in esp.SECCIONES_ESPECIFICACION]
        self.assertEqual(len(set(claves)), 9)
        for s in esp.SECCIONES_ESPECIFICACION:
            self.assertTrue(s.pregunta.endswith("?"), s.clave)


# =========================================================================
#  MUNDO INMERSIVO: lo que el coder compone para el motor del kit
# =========================================================================

def mundo_valido(**cambios):
    mundo = {
        "titulo": "Cumbre Andina",
        "descripcion": "Fotografía de alta montaña en los Andes.",
        "tipografia": "tecnica",
        "paleta": {"fondo": "#0a0a0f", "texto": "#e0e0e0", "acento": "#4ea8de",
                   "colores": ["#1f3a71", "#8ab6d6", "#b0c4de"]},
        "sonido": {"caracter": "profundo"},
        "estaciones": [
            {"indice": "01 · Horizonte", "titulo": "Cumbre Andina",
             "texto": "Amanecer sobre la cumbre más alta.", "objeto": {"tipo": "nebulosa"}},
            {"indice": "02 · Logística", "titulo": "Logística y equipo", "lado": "izquierda",
             "texto": "Guía, 4x4, oxígeno y refugio.",
             "objeto": {"tipo": "nucleo", "ficha": {"titulo": "Todo incluido", "breve": "Listo para subir"},
                        "satelites": [{"titulo": "Guía", "breve": "Treinta años en la cordillera"}]}},
            {"indice": "03 · Contacto", "titulo": "Reserva", "texto": "Escríbenos.",
             "objeto": {"tipo": "ninguno"},
             "llamada": {"texto": "Solicita información", "enlace": "mailto:hola@cumbre.test"}},
        ],
    }
    mundo.update(cambios)
    return mundo


def app_valida(**cambios):
    app = {
        "titulo": "Bitácora",
        "descripcion": "Notas rápidas.",
        "personalidad": "tecnica",
        "fondo3d": True,
        "persistencia": True,
        "modelos": [{
            "id": "notas", "titulo": "Notas", "registros": [],
            "campos": [
                {"id": "titulo", "etiqueta": "Título", "tipo": "texto", "obligatorio": True},
                {"id": "texto", "etiqueta": "Texto", "tipo": "area"},
            ],
        }],
        "secciones": [
            {"titulo": "Notas", "bloques": [
                {"tipo": "estadisticas", "indicadores": [
                    {"etiqueta": "Notas", "formato": "numero",
                     "calculo": {"operacion": "conteo", "modelo": "notas"}},
                ]},
                {"tipo": "lista", "modelo": "notas", "campo_titulo": "titulo",
                 "campo_detalle": "texto", "vacio": "Todavía no hay notas."},
                {"tipo": "formulario", "modelo": "notas", "boton_abrir": "Nueva nota"},
            ]},
        ],
    }
    app.update(cambios)
    return app


def app_con_datos(**cambios):
    app = {
        "titulo": "Cartera",
        "descripcion": "Seguimiento de aportes y recuperaciones.",
        "personalidad": "sobria",
        "navegacion": "superior",
        "fondo3d": False,
        "persistencia": True,
        "clave_almacenamiento": "cartera_data",
        "direccion_visual": {
            "densidad": "compacta", "cabecera": "marca", "forma": "angular",
            "paleta": {"fondo": "#101010", "texto": "#f5f1e8",
                       "acento": "#d9a92b", "linea": "#3a3a3a"},
        },
        "modelos": [{
            "id": "movimientos", "titulo": "Movimientos", "registros": [],
            "campos": [
                {"id": "proyecto", "etiqueta": "Proyecto", "tipo": "texto", "obligatorio": True},
                {"id": "monto", "etiqueta": "Monto", "tipo": "numero", "obligatorio": True, "min": 0},
                {"id": "fecha", "etiqueta": "Fecha", "tipo": "fecha", "obligatorio": True},
            ],
        }],
        "secciones": [{"id": "resumen", "titulo": "Resumen", "bloques": [
            {"tipo": "estadisticas", "indicadores": [
                {"etiqueta": "Aportes", "formato": "moneda", "moneda": "COP",
                 "calculo": {"operacion": "suma", "modelo": "movimientos", "campo": "monto"}},
                {"etiqueta": "Registros", "formato": "numero",
                 "calculo": {"operacion": "conteo", "modelo": "movimientos"}},
            ]},
            {"tipo": "formulario", "modelo": "movimientos", "boton_abrir": "Nuevo movimiento"},
            {"tipo": "tabla", "modelo": "movimientos", "vacio": "Aún no hay movimientos.",
             "columnas": [{"id": "proyecto", "titulo": "Proyecto"},
                          {"id": "monto", "titulo": "Monto"},
                          {"id": "fecha", "titulo": "Fecha"}]},
            {"tipo": "grafico", "visualizacion": "linea", "titulo": "Evolución",
             "modelo": "movimientos", "eje_x": "fecha", "agrupacion": "mes", "acumulado": True,
             "calculo": {"operacion": "suma", "campo": "monto"}},
        ]}],
    }
    app.update(cambios)
    return app


class PruebaAppReact(unittest.TestCase):
    def test_una_app_bien_formada_no_tiene_errores(self):
        app, errores = esp.validar_app(app_valida())
        self.assertEqual(errores, ())
        self.assertEqual(app["navegacion"], "superior")
        self.assertEqual(app["secciones"][0]["id"], "notas")

    def test_la_navegacion_se_decide_sola_por_el_numero_de_secciones(self):
        crudo = app_valida(secciones=[
            {"titulo": f"Pantalla {i}", "bloques": [
                {"tipo": "texto", "origen": "plan", "texto": "Contenido real."}]}
            for i in range(7)])
        app, errores = esp.validar_app(crudo)
        self.assertEqual(errores, ())
        self.assertEqual(app["navegacion"], "lateral")

    def test_una_navegacion_explicita_del_modelo_se_respeta(self):
        app, errores = esp.validar_app(app_valida(navegacion="lateral"))
        self.assertEqual(errores, ())
        self.assertEqual(app["navegacion"], "lateral", "el modelo puede apartarse de la regla por defecto")

    def test_personalidad_invalida_cae_a_tecnica(self):
        app, errores = esp.validar_app(app_valida(personalidad="futurista"))
        self.assertTrue(any("«personalidad» debe ser una de" in e for e in errores))
        self.assertEqual(app["personalidad"], "tecnica")

    def test_fondo3d_puede_apagarse(self):
        app, errores = esp.validar_app(app_valida(fondo3d=False))
        self.assertEqual(errores, ())
        self.assertFalse(app["fondo3d"])

    def test_estructura_rota_y_bloques_inventados(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"][0] = {"tipo": "mapa"}
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("«tipo» debe ser uno de" in e for e in errores))
        _, errores = esp.validar_app({"titulo": "x", "secciones": []})
        self.assertTrue(any("de 1 a 8 pantallas" in e for e in errores))
        self.assertEqual(esp.validar_app("no es json")[1], ("la app debe ser un objeto JSON",))

    def test_formulario_y_estadisticas_necesitan_su_contenido(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [{"tipo": "formulario", "campos": []}]
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("formulario" in e and "modelo" in e for e in errores))
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "estadisticas", "origen": "plan", "chips": []}]
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("necesita al menos un chip" in e for e in errores))

    def test_catalogo_nuevo_de_bloques_normaliza_tabla_grafico_progreso_agenda_y_kanban(self):
        bloques = [
            {"tipo": "tabla", "origen": "plan", "columnas": [
                {"id": "fecha", "titulo": "Fecha"}, {"id": "tarea", "titulo": "Tarea"}],
             "filas": [{"fecha": "27 nov", "tarea": "Enviar informe"}]},
            {"tipo": "grafico", "origen": "plan", "visualizacion": "barras", "titulo": "Gasto mensual",
             "datos": [{"etiqueta": "Enero", "valor": 120},
                       {"etiqueta": "Febrero", "valor": 95}]},
            {"tipo": "progreso", "origen": "plan", "etiqueta": "Lectura", "valor": 32,
             "total": 50, "unidad": "páginas"},
            {"tipo": "agenda", "origen": "plan", "eventos": [{"fecha": "2026-11-27", "hora": "15:30",
             "titulo": "Revisión", "detalle": "Presentar el borrador"}]},
            {"tipo": "kanban", "origen": "plan", "columnas": [
                {"id": "pendiente", "titulo": "Pendiente"}, {"id": "hecho", "titulo": "Hecho"}],
             "tarjetas": [{"id": "t1", "titulo": "Preparar borrador",
                           "columna": "pendiente"}]},
        ]
        app, errores = esp.validar_app(app_valida(secciones=[
            {"titulo": "Resumen", "bloques": bloques}]))
        self.assertEqual(errores, ())
        self.assertEqual([b["tipo"] for b in app["secciones"][0]["bloques"]],
                         ["tabla", "grafico", "progreso", "agenda", "kanban"])
        self.assertEqual(app["secciones"][0]["bloques"][1]["datos"][0]["valor"], 120)
        self.assertEqual(app["secciones"][0]["bloques"][3]["eventos"][0]["hora"], "15:30")
        self.assertEqual(app["secciones"][0]["bloques"][4]["tarjetas"][0]["columna"], "pendiente")

    def test_bloques_nuevos_rechazan_estructuras_fuera_de_su_contrato(self):
        casos = (
            ({"tipo": "tabla", "origen": "plan", "columnas": [{"id": "fecha", "titulo": "Fecha"},
              {"id": "tarea", "titulo": "Tarea"}], "filas": [{"fecha": "hoy"}]}, "exactamente"),
            ({"tipo": "grafico", "origen": "plan", "visualizacion": "anillo", "datos": [
              {"etiqueta": "A", "valor": -1}, {"etiqueta": "B", "valor": 2}]}, "no pueden ser negativos"),
            ({"tipo": "progreso", "origen": "plan", "etiqueta": "Lectura", "valor": 51, "total": 50}, "0 ≤ valor ≤ total"),
            ({"tipo": "agenda", "origen": "plan", "eventos": [{"fecha": "2026-02-30", "titulo": "Cierre"}]}, "fecha real"),
            ({"tipo": "kanban", "origen": "plan", "columnas": [
              {"id": "pendiente", "titulo": "Pendiente"}, {"id": "hecho", "titulo": "Hecho"}],
              "tarjetas": [{"id": "t1", "titulo": "A", "columna": "perdido"}]}, "columna existente"),
            ({"tipo": "tabla", "origen": "plan", "columnas": [
              {"id": "ID", "titulo": "Identificador"},
              {"id": "monto", "titulo": "Monto"}], "filas": []}, "id técnico de la columna"),
            ({"tipo": "tabla", "origen": "plan", "columnas": [
              {"id": "id", "titulo": "Identificador"},
              {"id": "id", "titulo": "Otro id"}], "filas": []}, "id técnico de la columna"),
        )
        for bloque, esperado in casos:
            with self.subTest(tipo=bloque["tipo"]):
                _, errores = esp.validar_app(app_valida(secciones=[
                    {"titulo": "Resumen", "bloques": [bloque]}]))
                self.assertTrue(any(esperado in error for error in errores), errores)

    def test_app_con_modelos_validos_queda_vacia_y_conectada(self):
        app, errores = esp.validar_app(app_con_datos())
        self.assertEqual(errores, ())
        self.assertTrue(app["persistencia"])
        self.assertEqual(app["modelos"][0]["registros"], [])
        self.assertEqual(app["secciones"][0]["bloques"][0]["indicadores"][0]["calculo"]["campo"], "monto")
        self.assertEqual(app["secciones"][0]["bloques"][3]["datos"], [])

    def test_formulario_sin_modelo_no_es_una_funcion_finja(self):
        crudo = app_valida()
        crudo.pop("modelos")
        crudo["persistencia"] = False
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("formulario" in e and "modelo" in e for e in errores), errores)

    def test_formulario_no_puede_omitir_un_campo_obligatorio(self):
        crudo = app_con_datos()
        crudo["secciones"][0]["bloques"][1]["campos"] = ["proyecto"]
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("obligatorio" in error for error in errores), errores)

    def test_datos_estaticos_exigen_procedencia_del_plan(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "estadisticas", "chips": [{"etiqueta": "Saldo", "valor": "1250000"}]},
            {"tipo": "lista", "items": [{"titulo": "Proyecto Alfa"}], "vacio": "Nada"},
            {"tipo": "tabla", "columnas": [{"id": "nombre", "titulo": "Nombre"},
             {"id": "valor", "titulo": "Valor"}], "filas": [{"nombre": "Alfa", "valor": 10}]},
        ]
        _, errores = esp.validar_app(crudo)
        self.assertGreaterEqual(sum("origen" in e for e in errores), 3, errores)

    def test_ni_cifras_ni_registros_estaticos_ajenos_al_plan_pasan(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "lista", "origen": "plan", "vacio": "Nada",
             "items": [{"titulo": "Proyecto Omega", "detalle": "Inversión inventada"}]},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Una cartera para registrar proyectos propios.")
        self.assertTrue(any("no consta en el plan" in e for e in errores), errores)

        crudo = app_con_datos()
        crudo["modelos"][0]["registros"] = [
            {"origen": "plan", "valores": {"proyecto": "Proyecto Omega", "monto": 999, "fecha": "2026-11-27"}},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Cartera con proyectos propios; fecha 2026-11-27.")
        self.assertTrue(any("no consta en el plan" in e for e in errores), errores)

    def test_los_detalles_opcionales_vacios_no_son_datos_inventados(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "agenda", "origen": "plan",
             "eventos": [{"fecha": "2026-11-27", "titulo": "Revisión"}]},
            {"tipo": "kanban", "origen": "plan",
             "columnas": [{"id": "pendiente", "titulo": "Pendiente"},
                          {"id": "hecho", "titulo": "Hecho"}],
             "tarjetas": [{"id": "t1", "titulo": "Preparar", "columna": "pendiente"}]},
        ]
        _, errores = esp.validar_app(
            crudo, plan_texto="Revisión el 2026-11-27 y tarjeta Preparar.")
        self.assertEqual(errores, ())

    def test_texto_estatico_exige_origen_y_no_inventa_cifras(self):
        crudo = app_valida()
        bloque = {"tipo": "texto", "texto": "El saldo inventado es 999999."}
        crudo["secciones"][0]["bloques"] = [bloque]
        _, errores = esp.validar_app(crudo, plan_texto="App sin datos.")
        self.assertTrue(any("origen" in error for error in errores), errores)

        bloque["origen"] = "plan"
        _, errores = esp.validar_app(crudo, plan_texto="App sin datos.")
        self.assertTrue(any("no consta en el plan" in error for error in errores), errores)

        bloque["texto"] = "El capital aprobado es 1250."
        _, errores = esp.validar_app(crudo, plan_texto="App con capital 1250.")
        self.assertEqual(errores, ())

    def test_un_identificador_textual_no_se_convierte_en_numero(self):
        crudo = app_con_datos()
        crudo["modelos"][0]["registros"] = [
            {"origen": "plan", "valores": {
                "proyecto": "00123", "monto": 10, "fecha": "2026-11-27"}},
        ]
        _, errores = esp.validar_app(
            crudo, plan_texto="ID 123, monto 10 y fecha 2026-11-27.")
        self.assertTrue(any("proyecto" in error and "no consta en el plan" in error
                            for error in errores), errores)

    def test_un_nombre_no_se_autoriza_por_ser_prefijo_de_otro(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "lista", "origen": "plan", "items": [{"titulo": "Proyecto Alfa"}]},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Cartera con Proyecto Alfajor.")
        self.assertTrue(any("no consta en el plan" in error for error in errores), errores)

    def test_un_texto_no_ascii_no_se_autoriza_por_normalizarse_vacio(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "lista", "origen": "plan", "items": [{"titulo": "東京"}]},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Cartera sin nombres propios.")
        self.assertTrue(any("no consta en el plan" in error for error in errores), errores)
        _, errores = esp.validar_app(crudo, plan_texto="Cartera con el proyecto 東京.")
        self.assertEqual(errores, ())

    def test_el_plan_exige_formulario_y_calculo_conectados(self):
        crudo = app_con_datos()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "texto", "origen": "plan", "texto": "Registra gastos."},
        ]
        _, errores = esp.validar_app(
            crudo, plan_texto="Registrar gastos y calcular el total.")
        self.assertTrue(any("formulario" in error for error in errores), errores)
        self.assertTrue(any("c[áa]lculo" in error or "calcul" in error for error in errores), errores)

    def test_guardar_exige_un_formulario_conectado(self):
        crudo = app_con_datos()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "texto", "origen": "plan", "texto": "Guardar gastos."},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Guardar gastos.")
        self.assertTrue(any("formulario" in error for error in errores), errores)

    def test_negaciones_y_exclusiones_no_exigen_controles(self):
        crudo = app_valida(persistencia=False)
        crudo.pop("modelos")
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "texto", "origen": "plan", "texto": "App informativa."},
        ]
        plan = (
            "# Especificación: Consulta\n\n"
            "## 1. Visión\nApp informativa.\n\n"
            "## 5. Funcionalidades\nNo editar ni eliminar registros.\n\n"
            "## 9. Fuera de alcance\nRegistrar gastos y calcular totales.\n"
        )
        _, errores = esp.validar_app(crudo, plan_texto=plan)
        self.assertEqual(errores, ())

    def test_totalmente_no_es_una_peticion_de_calculo(self):
        crudo = app_con_datos()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "texto", "origen": "plan", "texto": "App informativa."},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Una app totalmente informativa.")
        self.assertEqual(errores, ())

    def test_un_idioma_invalido_no_rompe_el_formato_del_kit(self):
        crudo = app_valida()
        crudo["idioma"] = "español"
        app, errores = esp.validar_app(crudo)
        self.assertTrue(any("idioma" in error for error in errores), errores)
        self.assertEqual(app["idioma"], "es")

    def test_kanban_dinamico_exige_persistencia(self):
        crudo = app_con_datos()
        crudo["persistencia"] = False
        crudo["modelos"][0]["campos"].append({
            "id": "estado", "etiqueta": "Estado", "tipo": "seleccion",
            "opciones": ["Pendiente", "Hecho"],
        })
        crudo["secciones"][0]["bloques"].append({
            "tipo": "kanban", "modelo": "movimientos", "campo_titulo": "proyecto",
            "campo_columna": "estado", "columnas": [
                {"id": "pendiente", "titulo": "Pendiente", "valor": "Pendiente"},
                {"id": "hecho", "titulo": "Hecho", "valor": "Hecho"},
            ],
        })
        _, errores = esp.validar_app(crudo, plan_texto="Mover y guardar tarjetas.")
        self.assertTrue(any("kanban" in error and "persistente" in error
                            for error in errores), errores)

    def test_un_numero_no_se_autoriza_por_ser_parte_de_otro(self):
        crudo = app_con_datos()
        crudo["modelos"][0]["registros"] = [
            {"origen": "plan", "valores": {
                "proyecto": "Proyecto Norte", "monto": 125, "fecha": "2026-11-27"}},
        ]
        plan = "Cartera con Proyecto Norte, monto 1250 y fecha 2026-11-27."
        _, errores = esp.validar_app(crudo, plan_texto=plan)
        self.assertTrue(any("monto" in error and "no consta en el plan" in error
                            for error in errores), errores)

        crudo["modelos"][0]["registros"][0]["valores"]["monto"] = 1250
        app, errores = esp.validar_app(crudo, plan_texto=plan)
        self.assertEqual(errores, ())
        self.assertEqual(app["modelos"][0]["registros"][0]["valores"]["monto"], 1250)

        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "estadisticas", "origen": "plan",
             "chips": [{"etiqueta": "Saldo", "valor": 125}]},
        ]
        _, errores = esp.validar_app(crudo, plan_texto="Informe con saldo 1250.")
        self.assertTrue(any("no consta en el plan" in error for error in errores), errores)

        for valor, cifra in ((1250, "1.250"), (1250.5, "1.250,5"),
                             (1250.5, "1,250.5"), (0.125, "0,125")):
            with self.subTest(valor=valor, cifra=cifra):
                crudo = app_con_datos()
                crudo["modelos"][0]["registros"] = [
                    {"origen": "plan", "valores": {
                        "proyecto": "Proyecto Norte", "monto": valor, "fecha": "2026-11-27"}},
                ]
                plan = f"Cartera con Proyecto Norte, monto ${cifra} y fecha 2026-11-27."
                _, errores = esp.validar_app(crudo, plan_texto=plan)
                self.assertEqual(errores, ())

    def test_kanban_tiene_una_columna_para_cada_estado_del_modelo(self):
        crudo = app_con_datos()
        crudo["modelos"][0]["campos"].append({
            "id": "estado", "etiqueta": "Estado", "tipo": "seleccion",
            "opciones": ["Pendiente", "En curso", "Hecho"],
        })
        tablero = {"tipo": "kanban", "modelo": "movimientos", "campo_titulo": "proyecto",
                   "campo_columna": "estado", "columnas": [
                       {"id": "pendiente", "titulo": "Pendiente", "valor": "Pendiente"},
                       {"id": "hecho", "titulo": "Hecho", "valor": "Hecho"},
                   ]}
        crudo["secciones"][0]["bloques"].append(tablero)
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("cada opción" in error for error in errores), errores)

        tablero["columnas"].append(
            {"id": "en-curso", "titulo": "En curso", "valor": "En curso"})
        _, errores = esp.validar_app(crudo)
        self.assertEqual(errores, ())

    def test_los_interruptores_no_aceptan_texto_como_booleano(self):
        for clave in ("fondo3d", "persistencia"):
            with self.subTest(clave=clave):
                crudo = app_con_datos()
                crudo[clave] = "false"
                _, errores = esp.validar_app(crudo)
                self.assertTrue(any(clave in error and "true o false" in error
                                    for error in errores), errores)

        with self.subTest(clave="obligatorio"):
            crudo = app_con_datos()
            crudo["modelos"][0]["campos"][0]["obligatorio"] = "false"
            _, errores = esp.validar_app(crudo)
            self.assertTrue(any("obligatorio" in error and "true o false" in error
                                for error in errores), errores)

        with self.subTest(clave="acumulado"):
            crudo = app_con_datos()
            crudo["secciones"][0]["bloques"][3]["acumulado"] = "false"
            _, errores = esp.validar_app(crudo)
            self.assertTrue(any("acumulado" in error and "true o false" in error
                                for error in errores), errores)

    def test_modelos_y_bloques_no_apuntan_a_campos_inexistentes(self):
        crudo = app_con_datos()
        crudo["secciones"][0]["bloques"][0]["indicadores"][0]["calculo"]["campo"] = "inexistente"
        crudo["secciones"][0]["bloques"][1]["modelo"] = "otro"
        crudo["secciones"][0]["bloques"][3]["calculo"]["operacion"] = "adivinar"
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("campo" in e and "inexistente" in e for e in errores), errores)
        self.assertTrue(any("modelo" in e and "otro" in e for e in errores), errores)
        self.assertTrue(any("operacion" in e for e in errores), errores)

    def test_plan_con_persistencia_no_se_entrega_como_prototipo_estatico(self):
        crudo = app_valida()
        crudo.pop("modelos")
        crudo["persistencia"] = False
        crudo["secciones"][0]["bloques"] = [{"tipo": "texto", "texto": "Registra tus movimientos."}]
        _, errores = esp.validar_app(
            crudo, plan_texto="MVP: registrar movimientos. Los datos se guardan en localStorage y sobreviven al recargar.")
        self.assertTrue(any("modelos" in e and "persist" in e for e in errores), errores)

    def test_direccion_visual_si_es_personal_y_corrige_contraste(self):
        app, errores = esp.validar_app(app_con_datos())
        self.assertEqual(errores, ())
        self.assertEqual(app["direccion_visual"]["cabecera"], "marca")
        self.assertGreaterEqual(esp.contraste(app["direccion_visual"]["paleta"]["texto"],
                                              app["direccion_visual"]["paleta"]["fondo"]), 7)
        crudo = app_con_datos()
        crudo["direccion_visual"]["densidad"] = "infinita"
        _, errores = esp.validar_app(crudo)
        self.assertTrue(any("densidad" in e for e in errores), errores)

    def test_emojis_y_relleno_son_errores_de_estilo(self):
        crudo = app_valida()
        crudo["secciones"][0]["bloques"] = [
            {"tipo": "texto", "origen": "plan", "texto": "Bienvenido a tu app 🚀"}]
        _, errores = esp.validar_app(crudo)
        self.assertTrue(all(e.startswith(esp.ESTILO) for e in errores))
        self.assertTrue(any("emojis" in e for e in errores))
        self.assertTrue(any("relleno" in e for e in errores))


class PruebaMundoInmersivo(unittest.TestCase):
    def test_un_mundo_bien_formado_no_tiene_errores(self):
        mundo, errores = esp.validar_mundo(mundo_valido())
        self.assertEqual(errores, ())
        self.assertEqual(mundo["estaciones"][1]["objeto"]["satelites"][0]["titulo"], "Guía")
        self.assertEqual(mundo["estaciones"][2]["llamada"]["enlace"], "mailto:hola@cumbre.test")

    def test_rellena_por_defecto_y_normaliza_colores(self):
        crudo = mundo_valido(tipografia=None, sonido=None)
        crudo["paleta"]["acento"] = "#4AD"
        mundo, errores = esp.validar_mundo(crudo)
        self.assertEqual(errores, ())
        self.assertEqual((mundo["tipografia"], mundo["sonido"]["caracter"]), ("tecnica", "profundo"))
        self.assertEqual(mundo["paleta"]["acento"], "#44aadd")

    def test_la_portada_lleva_el_nombre_aunque_el_modelo_la_titule_distinto(self):
        crudo = mundo_valido()
        crudo["estaciones"][0]["titulo"] = "El Horizonte"
        mundo, errores = esp.validar_mundo(crudo)
        self.assertEqual(errores, ())
        self.assertEqual(mundo["estaciones"][0]["titulo"], "Cumbre Andina")

    def test_una_paleta_ilegible_se_corrige_sin_volver_al_modelo(self):
        """Medido el 25-11-2026: un acento café sobre fondo oscuro tumbó una web tres veces."""
        crudo = mundo_valido()
        crudo["paleta"].update(fondo="#f4ede1", texto="#3a2a20", acento="#5a3a28")
        mundo, errores = esp.validar_mundo(crudo)
        self.assertEqual(errores, ())
        paleta = mundo["paleta"]
        self.assertGreaterEqual(esp.contraste(paleta["texto"], paleta["fondo"]), 7)
        self.assertGreaterEqual(esp.contraste(paleta["acento"], paleta["fondo"]), 4.5)
        self.assertNotEqual(paleta["acento"], "#ffffff", "se aclara, no se reemplaza por blanco")

    def test_los_colores_de_los_objetos_se_ven_y_no_deslumbran(self):
        """Medido el 25-11-2026: #e5e5e5 se volvía un resplandor y #121212 no se veía."""
        crudo = mundo_valido()
        crudo["paleta"]["colores"] = ["#121212", "#e5e5e5", "#8c5238"]
        mundo, errores = esp.validar_mundo(crudo)
        self.assertEqual(errores, ())
        fondo = mundo["paleta"]["fondo"]
        for c in mundo["paleta"]["colores"]:
            self.assertGreaterEqual(esp.contraste(c, fondo), 2.5, c)
            self.assertLess(esp.contraste(c, "#000000"), esp.contraste("#e5e5e5", "#000000"), c)
        self.assertEqual(mundo["paleta"]["colores"][2], "#8c5238", "un color correcto no se toca")

    def test_estructura_rota_y_objetos_inventados(self):
        crudo = mundo_valido()
        crudo["estaciones"][0]["objeto"] = {"tipo": "dragon"}
        crudo["estaciones"][2]["objeto"] = {"tipo": "cristal", "satelites": [{"titulo": "x"}]}
        _, errores = esp.validar_mundo(crudo)
        self.assertTrue(any("«dragon» no existe" in e for e in errores))
        self.assertTrue(any("solo el «nucleo» tiene satélites" in e for e in errores))
        _, errores = esp.validar_mundo({"titulo": "x", "estaciones": [{"titulo": "una"}]})
        self.assertTrue(any("de 2 a 7 estaciones" in e for e in errores))
        self.assertEqual(esp.validar_mundo("no es json")[1], ("el mundo debe ser un objeto JSON",))

    def test_el_cierre_necesita_su_llamada(self):
        crudo = mundo_valido()
        del crudo["estaciones"][2]["llamada"]
        _, errores = esp.validar_mundo(crudo)
        self.assertIn("la última estación cierra con una «llamada» (texto y enlace)", errores)

    def test_el_texto_con_tramoya_o_relleno_es_error_de_estilo_y_dice_donde(self):
        """Medido el 25-11-2026: «Formulario de baja fricción», «Galería interactiva»."""
        crudo = mundo_valido()
        crudo["estaciones"][1]["texto"] = "Bienvenido a la galería interactiva 🚀"
        _, errores = esp.validar_mundo(crudo)
        self.assertTrue(errores)
        self.assertTrue(all(e.startswith(esp.ESTILO) for e in errores))
        self.assertTrue(any("estación 2, texto" in e and "emojis" in e for e in errores))
        self.assertTrue(any("bienvenido a" in e for e in errores))
        self.assertTrue(any("galería" in e and "interactiva" in e for e in errores))

    def test_la_descripcion_para_buscadores_no_se_revisa_como_texto_visible(self):
        _, errores = esp.validar_mundo(mundo_valido(descripcion="Landing de un estudio de fotografía"))
        self.assertEqual(errores, ())

    def test_centro_solo_donde_no_tapa_un_objeto(self):
        crudo = mundo_valido()
        crudo["estaciones"][1]["lado"] = "centro"      # tiene núcleo: el motor elige lado
        crudo["estaciones"][2]["lado"] = "centro"      # cierre: vale
        mundo, errores = esp.validar_mundo(crudo)
        self.assertEqual(errores, ())
        self.assertNotIn("lado", mundo["estaciones"][1])
        self.assertEqual(mundo["estaciones"][2]["lado"], "centro")

    def test_los_textos_largos_se_recortan_por_palabra(self):
        crudo = mundo_valido()
        crudo["estaciones"][1]["texto"] = "palabra " * 80
        mundo, _ = esp.validar_mundo(crudo)
        texto = mundo["estaciones"][1]["texto"]
        self.assertLessEqual(len(texto), 321)
        self.assertTrue(texto.endswith("palabra…"))

    def test_el_stack_inmersivo_se_reconoce(self):
        def stack(texto):
            return esp.Especificacion(secciones={"stack": texto}).stack()
        self.assertEqual(stack("Inmersivo: un mundo 3D que se recorre."), "inmersivo")
        self.assertEqual(stack("Una web WebGL con Three.js"), "inmersivo")
        self.assertIn("inmersivo", esp.STACKS)


class PruebaVariedadDelMundo(unittest.TestCase):
    """Que una web no sea la fotocopia de otra (pedido del usuario, 25-11-2026)."""

    def estacion(self, tipo, variante=None, **extra):
        objeto = {"tipo": tipo, **({"variante": variante} if variante else {}), **extra}
        return {"titulo": tipo, "texto": "algo concreto", "objeto": objeto}

    def mundo(self, *estaciones, **cambios):
        base = mundo_valido(estaciones=list(estaciones))
        base["estaciones"][-1]["llamada"] = {"texto": "Escríbenos", "enlace": "mailto:a@b.test"}
        base.update(cambios)
        return base

    def test_variante_por_defecto_y_variante_inventada(self):
        mundo, errores = esp.validar_mundo(self.mundo(
            self.estacion("nebulosa"), self.estacion("cristal", "pompa")))
        self.assertEqual(mundo["estaciones"][0]["objeto"]["variante"], "nube")
        self.assertTrue(any("«pompa» no existe para «cristal»" in e for e in errores))

    def test_todas_las_formas_por_defecto_es_un_error_de_estilo(self):
        _, errores = esp.validar_mundo(self.mundo(
            self.estacion("nebulosa"), self.estacion("cristal"), self.estacion("anillos")))
        self.assertTrue(any(e.startswith(esp.ESTILO) and "formas son las de por defecto" in e
                            for e in errores))
        _, errores = esp.validar_mundo(self.mundo(
            self.estacion("nebulosa", "espiral"), self.estacion("cristal"), self.estacion("anillos")))
        self.assertFalse(any("formas son las de por defecto" in e for e in errores))

    def test_nucleo_esfera_y_teseracto_juntos_son_la_firma_de_dark(self):
        _, errores = esp.validar_mundo(self.mundo(
            self.estacion("nucleo"), self.estacion("hipercubo", "teseracto")))
        self.assertTrue(any("firma de D.A.R.K." in e for e in errores))
        _, errores = esp.validar_mundo(self.mundo(
            self.estacion("nucleo", "faceta"), self.estacion("hipercubo", "teseracto")))
        self.assertFalse(any("firma de D.A.R.K." in e for e in errores))

    def test_ambiente_y_recorrido(self):
        mundo, errores = esp.validar_mundo(self.mundo(self.estacion("nebulosa", "velo"),
                                                      self.estacion("ninguno")))
        self.assertEqual((mundo["ambiente"], mundo["recorrido"]), ("estrellas", "avance"))
        _, errores = esp.validar_mundo(self.mundo(self.estacion("ninguno"), self.estacion("ninguno"),
                                                  ambiente="lluvia", recorrido="salto"))
        self.assertTrue(any("«ambiente»" in e for e in errores))
        self.assertTrue(any("«recorrido»" in e for e in errores))

    def test_las_fotos_necesitan_consulta_y_al_menos_dos(self):
        fotos = [{"consulta": "andes summit", "titulo": "Cumbre"}, {"titulo": "sin consulta"}]
        _, errores = esp.validar_mundo(self.mundo(self.estacion("fotos", fotos=fotos),
                                                  self.estacion("ninguno")))
        self.assertTrue(any("necesita «consulta»" in e for e in errores))
        self.assertTrue(any("de 2 a 8 fotos" in e for e in errores))
        _, errores = esp.validar_mundo(self.mundo(self.estacion("cristal", fotos=fotos),
                                                  self.estacion("ninguno")))
        self.assertTrue(any("solo el objeto «fotos» lleva fotos" in e for e in errores))

    def test_unas_fotos_bien_formadas_pasan(self):
        fotos = [{"consulta": "andes summit sunrise", "titulo": "Cumbre", "breve": "6.961 m"},
                 {"consulta": "glacier blue ice", "titulo": "Glaciar"}]
        mundo, errores = esp.validar_mundo(self.mundo(self.estacion("fotos", "pila", fotos=fotos),
                                                      self.estacion("ninguno")))
        self.assertEqual(errores, ())
        self.assertEqual(mundo["estaciones"][0]["objeto"]["fotos"][1]["consulta"], "glacier blue ice")


if __name__ == "__main__":
    unittest.main()
