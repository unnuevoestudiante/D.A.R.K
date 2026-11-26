"""R3 Fase B: `especialistas/fabrica.py` es el único sitio que nombra las clases.

El Núcleo construía a los cinco especialistas importando sus clases y pasando
~30 argumentos propios. La Fase B mueve ese cableado a la fábrica y deja en el
Núcleo solo llamadas a `crear_*` que devuelven puertos. Estos tests vigilan tres
cosas que importan más que el refactor en sí:

  * la pereza: importar la fábrica no puede arrastrar VLC, los temas ni el
    conversacional (ese era el motivo de la importación local en el Núcleo);
  * la barrera: ningún consumidor vuelve a nombrar una clase concreta;
  * el cableado: la fábrica no puede perder ni inventar un argumento, y el
    Núcleo tiene que pasar exactamente los que la fábrica pide.

Ref: especialistas/fabrica.py, contratos/especialista.py, nucleo/dark_nucleo.py.
"""
import ast
import pathlib
import subprocess
import sys
import types
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos import especialista as puertos  # noqa: E402
from especialistas import fabrica  # noqa: E402

# funcion de la fabrica -> (modulo del motor, clase, puerto que devuelve)
MOTORES = {
    "crear_especialista_codigo": ("especialistas.especialista_codigo",
                                  "EspecialistaCodigo", "PuertoCodigo"),
    "crear_especialista_comunicacion": ("especialistas.especialista_comunicacion",
                                        "EspecialistaComunicacion",
                                        "PuertoComunicacion"),
    "crear_especialista_tareas": ("especialistas.especialista_tareas",
                                  "EspecialistaTareas", "PuertoTareas"),
    "crear_especialista_conversacion": ("especialistas.especialista_conversacional",
                                        "EspecialistaConversacional",
                                        "PuertoConversacion"),
    "crear_terminal": ("herramientas.externas.terminal", "DarkTerminal",
                       "PuertoTerminal"),
}
CLASES = {clase for _, clase, _ in MOTORES.values()}
# Paquetes de producción vigilados por la barrera. `test_simple.py` y
# `test_system.py` son scripts sueltos de la raíz y `tests/` puede usar las
# clases como dobles: ambos quedan fuera a propósito.
PAQUETOS_PRODUCCION = ("nucleo", "modulos", "herramientas", "proveedores", "voz",
                       "overlay", "acceso", "contratos", "especialistas")
FABRICA = DARK_PYTHON / "especialistas" / "fabrica.py"


def _arbol(ruta):
    return ast.parse(pathlib.Path(ruta).read_text(encoding="utf-8"))


def _funcion(ruta, nombre):
    for nodo in ast.walk(_arbol(ruta)):
        if isinstance(nodo, ast.FunctionDef) and nodo.name == nombre:
            return nodo
    raise AssertionError(f"no encontré {nombre} en {ruta}")


def _init_motor(modulo, clase):
    ruta = DARK_PYTHON / (modulo.replace(".", "/") + ".py")
    for nodo in ast.walk(_arbol(ruta)):
        if isinstance(nodo, ast.ClassDef) and nodo.name == clase:
            for miembro in nodo.body:
                if isinstance(miembro, ast.FunctionDef) and miembro.name == "__init__":
                    return miembro
    raise AssertionError(f"{clase} no tiene __init__ en {modulo}")


def _kwonly(fn):
    """(nombres keyword-only, los que tienen valor por defecto puesto)."""
    nombres = [a.arg for a in fn.args.kwonlyargs]
    con_defecto = {a.arg for a, d in zip(fn.args.kwonlyargs, fn.args.kw_defaults)
                   if d is not None}
    return nombres, con_defecto


def _kwargs_de_la_llamada(fn):
    for nodo in ast.walk(fn):
        if isinstance(nodo, ast.Call):
            return {k.arg for k in nodo.keywords}
    return set()


class PruebaPereza(unittest.TestCase):
    def test_importar_la_fabrica_no_arrastra_motores(self):
        codigo = (
            "import sys; sys.path.insert(0, {dp!r});"
            "import especialistas.fabrica;"
            "arrastrados=[m for m in {modulos!r} if m in sys.modules];"
            "print('ARRASTRA:' + ','.join(arrastrados))"
        ).format(dp=str(DARK_PYTHON), modulos=[m for m, _, _ in MOTORES.values()])
        proceso = subprocess.run([sys.executable, "-c", codigo],
                                 capture_output=True, text=True, timeout=120)
        linea = next((l for l in proceso.stdout.splitlines()
                      if l.startswith("ARRASTRA:")), None)
        self.assertIsNotNone(linea, f"el subprocess no respondió: {proceso.stderr!r}")
        self.assertEqual(linea, "ARRASTRA:",
                         "la fábrica dejó de ser perezosa: " + linea)

    def test_cada_crearl_importa_dentro_de_la_funcion(self):
        for nombre in MOTORES:
            fn = _funcion(FABRICA, nombre)
            self.assertTrue(any(isinstance(n, (ast.Import, ast.ImportFrom))
                                for n in ast.walk(fn)),
                            f"{nombre} no importa su motor dentro de la función")


class PruebaBarrera(unittest.TestCase):
    def _importaciones(self, ruta):
        salida = []
        for nodo in ast.walk(_arbol(ruta)):
            if isinstance(nodo, ast.ImportFrom):
                for n in nodo.names:
                    salida.append((nodo.module or "", n.name))
            elif isinstance(nodo, ast.Import):
                for n in nodo.names:
                    salida.append((n.name, None))
        return salida

    def test_solo_la_fabrica_importa_las_clases(self):
        infractoras = []
        for paquete in PAQUETOS_PRODUCCION:
            for p in sorted((DARK_PYTHON / paquete).rglob("*.py")):
                if p == FABRICA:
                    continue
                for modulo, nombre in self._importaciones(p):
                    if nombre in CLASES:
                        infractoras.append(
                            f"{p.relative_to(DARK_PYTHON)} <- {modulo}.{nombre}")
        self.assertEqual(infractoras, [],
                         "un consumidor volvió a importar la clase concreta: "
                         + "; ".join(infractoras))

    def test_el_nucleo_no_construye_las_clases(self):
        texto = "\n".join(p.read_text(encoding="utf-8")
                          for p in sorted((DARK_PYTHON / "nucleo").rglob("*.py")))
        for clase in CLASES:
            self.assertNotIn(clase + "(", texto,
                             f"el Núcleo vuelve a construir {clase}")

    def test_la_fabrica_no_expone_las_clases_como_nombre(self):
        """Devuelve puertos: si la clase queda como nombre global del módulo, un
        consumidor podría importarla desde aquí y la barrera no sirve."""
        asignadas = set()
        for nodo in ast.walk(_arbol(FABRICA)):
            if isinstance(nodo, (ast.Assign, ast.AnnAssign)):
                blancos = getattr(nodo, "targets", None) or [nodo.target]
                for t in blancos:
                    if isinstance(t, ast.Name):
                        asignadas.add(t.id)
        for clase in CLASES:
            self.assertNotIn(clase, asignadas)


class PruebaSuperficie(unittest.TestCase):
    def test_la_fabrica_no_inventa_parametros(self):
        for nombre, (modulo, clase, _) in MOTORES.items():
            pedidos, _ = _kwonly(_funcion(FABRICA, nombre))
            reales = {a.arg for a in _init_motor(modulo, clase).args.args}
            reales |= {a.arg for a in _init_motor(modulo, clase).args.kwonlyargs}
            extra = set(pedidos) - reales
            self.assertEqual(extra, set(),
                             f"{nombre} pide {sorted(extra)} que {clase} no acepta")

    def test_la_fabrica_no_deja_fuera_los_obligatorios(self):
        """Un parámetro obligatorio del motor que la fábrica no reenvía es un
        cable muerto: el especialista se construye a medias sin que nadie se entere."""
        for nombre, (modulo, clase, _) in MOTORES.items():
            init = _init_motor(modulo, clase)
            args = [a.arg for a in init.args.args][1:]
            requeridos = set(args[:len(args) - len(init.args.defaults)])
            reenviados = _kwargs_de_la_llamada(_funcion(FABRICA, nombre))
            self.assertTrue(requeridos <= reenviados,
                            f"{nombre} no reenvía {sorted(requeridos - reenviados)} "
                            f"obligatorios de {clase}")

    def test_todo_lo_que_promete_existe(self):
        for nombre in fabrica.__all__:
            self.assertTrue(hasattr(fabrica, nombre), f"__all__ miente: {nombre}")

    def test_cada_funcion_devuelve_su_puerto(self):
        for nombre, (_, _, puerto) in MOTORES.items():
            fn = _funcion(FABRICA, nombre)
            self.assertIsNotNone(fn.returns, f"{nombre} no declara tipo de vuelta")
            self.assertIsInstance(fn.returns, ast.Name)
            self.assertEqual(fn.returns.id, puerto,
                             f"{nombre} devuelve {fn.returns.id}, se esperaba {puerto}")
            self.assertTrue(hasattr(puertos, puerto))

    def test_el_puerto_prometido_es_comprobable(self):
        """Sin `@runtime_checkable` el `isinstance` de los smoke tests miente."""
        contrato = DARK_PYTHON / "contratos" / "especialista.py"
        decorados = set()
        for nodo in ast.walk(_arbol(contrato)):
            if isinstance(nodo, ast.ClassDef) and any(
                    isinstance(d, ast.Name) and d.id == "runtime_checkable"
                    for d in nodo.decorator_list):
                decorados.add(nodo.name)
        for _, _, puerto in MOTORES.values():
            self.assertIn(puerto, decorados,
                          f"{puerto} dejó de ser runtime_checkable")


class PruebaCableadoDelNucleo(unittest.TestCase):
    def _llamadas(self):
        encontradas = []
        for p in sorted((DARK_PYTHON / "nucleo").rglob("*.py")):
            for nodo in ast.walk(_arbol(p)):
                if (isinstance(nodo, ast.Call)
                        and isinstance(nodo.func, ast.Attribute)
                        and isinstance(nodo.func.value, ast.Name)
                        and nodo.func.value.id == "esp_fabrica"):
                    encontradas.append((p, nodo))
        return encontradas

    def test_el_nucleo_pide_los_cinco_especialistas(self):
        usados = {n.func.attr for _, n in self._llamadas()}
        faltan = set(MOTORES) - usados
        self.assertEqual(faltan, set(),
                         f"el Núcleo dejó de pedir: {sorted(faltan)}")

    def test_los_keywords_coinciden_con_la_firma(self):
        """El Núcleo manda los obligatorios y no inventa ninguno; los que tienen
        respaldo en la fábrica (`keep_alive`, `raiz_workspace`) puede omitirlos."""
        for p, nodo in self._llamadas():
            nombre = nodo.func.attr
            if nombre not in MOTORES:
                continue
            esperados, con_defecto = _kwonly(_funcion(FABRICA, nombre))
            enviados = {k.arg for k in nodo.keywords}
            self.assertTrue(set(esperados) - con_defecto <= enviados,
                            f"{p.name}: {nombre} no manda "
                            f"{sorted(set(esperados) - con_defecto - enviados)}")
            self.assertTrue(enviados <= set(esperados),
                            f"{p.name}: {nombre} manda {sorted(enviados - set(esperados))} "
                            f"que la fábrica no acepta")

    def test_escribir_json_atomico_sigue_cableado(self):
        usados = {n.func.attr for _, n in self._llamadas()}
        self.assertIn("escribir_json_atomico", usados,
                      "la primitiva de JSON atómico desapareció del Núcleo")


class PruebaReenvio(unittest.TestCase):
    """Con dobles en sys.modules: la fábrica pasa TODO y no inventa nada."""

    def setUp(self):
        self._guardados = {}
        self._capturados = {}

    def tearDown(self):
        for clave, original in self._guardados.items():
            if original is None:
                sys.modules.pop(clave, None)
            else:
                sys.modules[clave] = original

    def _modulo_falso(self, modulo, clase):
        if modulo not in self._guardados:
            self._guardados[modulo] = sys.modules.get(modulo)
        capturado = {}

        class Doble:
            def __init__(self, **kwargs):
                capturado.update(kwargs)

            @staticmethod
            def _escribir_json_atomico(ruta, datos):
                capturado["json"] = (ruta, datos)

        Doble.__name__ = clase
        ficticio = types.ModuleType(modulo)
        setattr(ficticio, clase, Doble)
        sys.modules[modulo] = ficticio
        self._capturados[modulo] = capturado
        return capturado

    CABLEADO = {
        "crear_especialista_codigo": dict(
            http_session="S", chat_provider="P", cliente_manager="M", llm_lock="L",
            liberar_whisper="lw", recargar_whisper="rw",
            preparar_modelo="pm", liberar_modelo="lm", avisar_espera="ae"),
        "crear_especialista_comunicacion": dict(
            http_session="S", vlc_instance="V", apps_registry_path="r",
            apps_cache_path="c", speak_cb="s", on_reproduccion_cb="o",
            sesion="E"),
        "crear_especialista_tareas": dict(
            http_session="S", chat_provider="P", cliente_manager="M", llm_lock="L",
            preparar_modelo="pm", helpers={"h": None}),
        "crear_especialista_conversacion": dict(
            router="R", cerebro="C", http_session="S", llm_lock="L",
            speak="sp", set_overlay="so", chat_model="m",
            chat_opts={"num_ctx": 1}, keep_alive="45m", chat_provider="P",
            anunciar="an"),
        "crear_terminal": dict(resumir_cb="rc", raiz_workspace=None,
                               almacen_confirmaciones=None),
    }

    def test_cada_crearl_reenvia_exactamente_su_cableado(self):
        for nombre, (modulo, clase, _) in MOTORES.items():
            capturado = self._modulo_falso(modulo, clase)
            try:
                getattr(fabrica, nombre)(**self.CABLEADO[nombre])
            except TypeError as error:
                self.fail(f"{nombre} no acepta el cableado del Núcleo: {error}")
            self.assertEqual(capturado, self.CABLEADO[nombre],
                             f"{nombre} no reenvió exacto lo que le dieron")

    def test_los_parametros_de_mas_reventan(self):
        """Keyword-only sin `**kwargs`: un argumento inventado tiene que ruidar."""
        self._modulo_falso(*MOTORES["crear_terminal"][:2])
        with self.assertRaises(TypeError):
            fabrica.crear_terminal(resumir_cb="rc", inventado=1)

    def test_keep_alive_es_el_unico_con_defecto_de_conversacion(self):
        _, con_defecto = _kwonly(_funcion(FABRICA,
                                        "crear_especialista_conversacion"))
        self.assertEqual(set(con_defecto), {"keep_alive", "chat_provider"},
                         "apareció un respaldo silencioso en la fábrica: cada "
                         "capacidad del especialista debe ser obligatoria salvo "
                         "las que el propio especialista ya respalda")

    def test_escribir_json_atomico_delega_en_el_motor(self):
        capturado = self._modulo_falso("especialistas.especialista_codigo",
                                      "EspecialistaCodigo")
        fabrica.escribir_json_atomico("ruta.json", {"a": 1})
        self.assertEqual(capturado["json"], ("ruta.json", {"a": 1}))


class PruebaConLosMotoresReales(unittest.TestCase):
    """Smoke: los cuatro especialistas ligeros se construyen de verdad y caben
    en su puerto. Conversación no entra: necesita router y cerebro."""

    def test_codigo_tareas_y_terminal_reales(self):
        sin_uso = lambda *a, **k: None  # noqa: E731
        codigo = fabrica.crear_especialista_codigo(
            http_session=None, chat_provider=None, cliente_manager=None,
            llm_lock=None,
            liberar_whisper=sin_uso, recargar_whisper=sin_uso,
            preparar_modelo=sin_uso, liberar_modelo=sin_uso)
        self.assertIsInstance(codigo, puertos.PuertoCodigo)
        tareas = fabrica.crear_especialista_tareas(
            http_session=None, chat_provider=None, cliente_manager=None,
            llm_lock=None,
            preparar_modelo=sin_uso, helpers={})
        self.assertIsInstance(tareas, puertos.PuertoTareas)
        terminal = fabrica.crear_terminal(resumir_cb=sin_uso)
        self.assertIsInstance(terminal, puertos.PuertoTerminal)


if __name__ == "__main__":
    unittest.main()
