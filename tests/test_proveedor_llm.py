"""Pruebas del límite común entre D.A.R.K. y los proveedores de chat."""
import ast
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from proveedores.llm.contrato import (  # noqa: E402
    ChatRequest, apagar_razonamiento, sin_razonamiento,
)
from proveedores.llm.ollama import (  # noqa: E402
    OllamaChatProvider, _metrics,
)
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402


class Respuesta:
    status_code = 200

    def __init__(self, data=None, lines=()):
        self._data = data or {}
        self._lines = lines
        self.closed = False

    def json(self):
        return self._data

    def iter_lines(self):
        yield from self._lines

    def close(self):
        self.closed = True


class Sesion:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class PruebasProveedorOllama(unittest.TestCase):
    def test_complete_traduce_solicitud_comun_y_normaliza_respuesta(self):
        session = Sesion(Respuesta({
            "model": "local-model",
            "done": True,
            "message": {"content": "respuesta"},
            "eval_count": 12,
            "prompt_eval_count": 30,
        }))
        provider = OllamaChatProvider(session, base_url="http://llm.test")
        result = provider.complete(ChatRequest(
            model="local-model",
            messages=[{"role": "user", "content": "hola"}],
            options={"context_tokens": 4096, "max_output_tokens": 100,
                     "cpu_threads": 6, "repetition_penalty": 1.1,
                     "temperature": 0.2},
            response_format="json", residency="5m",
            reasoning_enabled=False,
        ), timeout=(2, 10))

        self.assertEqual(result.content, "respuesta")
        self.assertTrue(result.finished)
        self.assertEqual(result.model, "local-model")
        self.assertEqual(result.metrics["completion_tokens"], 12)
        url, call = session.calls[0]
        self.assertEqual(url, "http://llm.test/api/chat")
        self.assertEqual(call["json"]["options"], {
            "num_ctx": 4096, "num_predict": 100, "num_thread": 6,
            "repeat_penalty": 1.1, "temperature": 0.2,
        })
        self.assertEqual(call["json"]["format"], "json")
        self.assertFalse(call["json"]["think"])
        self.assertEqual(call["timeout"], (2, 10))

    def test_stream_emite_eventos_comunes_y_cierra_respuesta(self):
        response = Respuesta(lines=[
            b'{"message":{"content":"Hola"},"done":false}',
            b'{"message":{"content":" mundo."},"done":false}',
            b'{"done":true,"eval_count":9}',
        ])
        session = Sesion(response)
        stream = OllamaChatProvider(session).stream(ChatRequest(
            model="local-model", messages=[], options={"max_output_tokens": 20},
        ), timeout=(1, 5))

        events = list(stream.iter_events())
        self.assertEqual([event.content for event in events],
                         ["Hola", " mundo.", ""])
        self.assertTrue(events[-1].finished)
        self.assertEqual(events[-1].metrics["completion_tokens"], 9)
        stream.close()
        self.assertTrue(response.closed)
        self.assertTrue(session.calls[0][1]["stream"])

    def test_loaded_models_y_health_son_capacidades_del_adaptador(self):
        response = Respuesta({"models": [
            {"name": "qwen3:4b"}, {"name": "llama:8b"}, {"name": ""},
        ]})
        provider = OllamaChatProvider(Sesion(response))
        self.assertEqual(provider.loaded_models(), ["qwen3:4b", "llama:8b"])
        self.assertTrue(provider.health(timeout=1))

    def test_fabrica_selecciona_por_configuracion_y_rechaza_no_instalados(self):
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "ollama"}):
            self.assertIsInstance(crear_proveedor_chat(session=Sesion(Respuesta())),
                                  OllamaChatProvider)
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "inexistente"}):
            with self.assertRaisesRegex(ValueError, "inexistente"):
                crear_proveedor_chat(session=Sesion(Respuesta()))


class TestMarcaDeRazonamiento(unittest.TestCase):
    """Las etiquetas de cadena de pensamiento solo viven en el contrato."""

    # Construidas por partes: en este archivo no debe aparecer la etiqueta
    # escrita del todo, es justo lo que la barrera busca en el codigo de produccion.
    APERTURA = "<" + "think"
    CIERRE = "<" + "/think"
    UNICO_PERMITIDO = Path("proveedores") / "llm" / "contrato.py"

    def _bloque(self, cuerpo="razono"):
        return self.APERTURA + ">" + cuerpo + self.CIERRE + ">"

    def test_sin_marca_devuelve_el_texto_igual(self):
        self.assertEqual(sin_razonamiento("Digame, que necesita?"),
                         "Digame, que necesita?")

    def test_none_y_vacio_no_reventan(self):
        for valor in (None, ""):
            self.assertEqual(sin_razonamiento(valor), "")

    def test_quita_el_bloque_completo_deja_el_texto(self):
        texto = "  " + self._bloque() + " respuesta  "
        self.assertEqual(sin_razonamiento(texto), "respuesta")

    def test_quita_varios_bloques_sin_comerse_lo_de_entre_medio(self):
        texto = "a" + self._bloque("x") + "b" + self._bloque("y") + "c"
        self.assertEqual(sin_razonamiento(texto), "abc")

    def test_una_apertura_sin_cierre_no_tira_texto(self):
        """El stream corta por donde quiere: un bloque sin cerrar se deja
        intacto antes que tragarse la respuesta del usuario."""
        texto = "a" + self.APERTURA + ">pensamiento sin fin b"
        self.assertEqual(sin_razonamiento(texto), texto)

    def test_cubre_las_dos_familias_y_mayusculas(self):
        thinking = "<" + "thinking" + ">" + "<" + "/thinking" + ">"
        mayusculas = "<" + "THINK" + ">" + "<" + "/THINK" + ">"
        self.assertEqual(sin_razonamiento("x" + thinking + " y"), "x y")
        self.assertEqual(sin_razonamiento("x" + mayusculas + " y"), "x y")

    def test_recibe_fragmentos_acumulados_no_un_token(self):
        """Es la forma en que lo usa el camino de voz: el buffer ya esta junto."""
        texto = " " + self._bloque() + "hola mundo"
        self.assertEqual(sin_razonamiento(texto), "hola mundo")

    def test_la_marca_no_se_repite_fuera_del_contrato(self):
        raiz = DARK_PYTHON
        encontradas = []
        for paquete in ("nucleo", "modulos", "herramientas", "proveedores",
                        "voz", "overlay", "acceso", "contratos",
                        "especialistas"):
            for py in (raiz / paquete).rglob("*.py"):
                if py.relative_to(raiz) == self.UNICO_PERMITIDO:
                    continue
                texto = py.read_text(encoding="utf-8", errors="replace")
                if self.APERTURA in texto:
                    encontradas.append(str(py.relative_to(raiz)))
        self.assertEqual(
            encontradas, [],
            "la etiqueta de razonamiento volvio a copiarse en consumidores; "
            "use proveedores.llm.contrato.sin_razonamiento()")


class TestFabricaUnicaPuertaDelMotor(unittest.TestCase):
    """La fábrica es el único sitio de producción que nombra el motor."""

    PAQUETOS = ("nucleo", "modulos", "herramientas", "proveedores", "voz",
                "overlay", "acceso", "contratos", "especialistas")
    UNICO_PERMITIDO = Path("proveedores") / "llm" / "fabrica.py"

    def _importadores_del_motor(self):
        """Archivos de producción que importan el módulo del adaptador."""
        culpables = []
        for paquete in self.PAQUETOS:
            for py in (DARK_PYTHON / paquete).rglob("*.py"):
                rel = py.relative_to(DARK_PYTHON)
                if rel == self.UNICO_PERMITIDO:
                    continue
                arbol = ast.parse(py.read_text(encoding="utf-8"), str(rel))
                if self._toca_el_motor(arbol):
                    culpables.append(str(rel))
        return sorted(set(culpables))

    @staticmethod
    def _toca_el_motor(arbol):
        """Import absolute o relativo del modulo del motor, en cualquier funcion."""
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                nombre = nodo.module or ""
                if nombre.endswith("llm.ollama"):
                    return True
                if nodo.level and nombre in {"ollama", "llm.ollama"}:
                    return True
            elif isinstance(nodo, ast.Import):
                if any(a.name.endswith("llm.ollama") for a in nodo.names):
                    return True
        return False

    def test_nadie_fuera_de_la_fabrica_importa_el_adaptador(self):
        self.assertEqual(
            self._importadores_del_motor(), [],
            "un consumidor volvió a importar el módulo del motor: con eso el "
            "proveedor se elige por nombre de archivo y no por configuracion")

    def test_importar_la_fabrica_no_arrastra_el_motor(self):
        lineas = [
            "import sys; sys.path.insert(0, {0!r})",
            "import proveedores.llm.fabrica",
            "print('ARRASTRA:' + ','.join(",
            "m for m in sys.modules if m.endswith('llm.ollama')))",
        ]
        codigo = (chr(10).join(lineas) + chr(10)).format(str(DARK_PYTHON))
        proceso = subprocess.run([sys.executable, "-c", codigo],
                                 capture_output=True, text=True)
        self.assertEqual(proceso.returncode, 0, proceso.stderr)
        linea = [l for l in proceso.stdout.splitlines()
                 if l.startswith("ARRASTRA:")][-1]
        self.assertEqual(
            linea, "ARRASTRA:",
            "la fábrica importa el motor arriba: pedir el puerto no debe "
            "cargar requests ni ningún peso del adaptador")

    def test_la_fabrica_devuelve_algo_que_cumple_el_puerto(self):
        from proveedores.llm.contrato import ChatProvider

        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "ollama"}):
            proveedor = crear_proveedor_chat(session=Sesion(Respuesta()))
        self.assertIsInstance(proveedor, ChatProvider)

    def test_el_error_dice_donde_se_registra_un_adaptador_nuevo(self):
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "vllm"}):
            with self.assertRaisesRegex(ValueError, "fabrica.py"):
                crear_proveedor_chat(session=Sesion(Respuesta()))


class TestMetricasDelProveedor(unittest.TestCase):
    """El puerto habla en conceptos; Ollama solo se nombra en el adaptador."""

    CARGA_OLLAMA = {
        "total_duration": 9_000_000_000,
        "load_duration": 1_000_000_000,
        "prompt_eval_count": 635,
        "prompt_eval_cached_count": 630,
        "prompt_eval_duration": 1_600_000_000,
        "eval_count": 42,
        "eval_duration": 2_500_000_000,
        "done_reason": "stop",
    }
    PAQUETOS = ("nucleo", "modulos", "herramientas", "proveedores", "voz",
                "overlay", "acceso", "contratos", "especialistas")

    def test_el_adaptador_traduce_todas_las_metricas(self):
        from proveedores.llm.contrato import METRICAS_GENERACION

        traducidas = _metrics(dict(self.CARGA_OLLAMA))
        self.assertEqual(set(traducidas), set(METRICAS_GENERACION))

    def test_los_valores_pasan_iguales_y_en_la_unidad_del_proveedor(self):
        traducidas = _metrics(dict(self.CARGA_OLLAMA))
        self.assertEqual(traducidas["prompt_tokens"], 635)
        self.assertEqual(traducidas["cached_prompt_tokens"], 630)
        self.assertEqual(traducidas["completion_tokens"], 42)
        self.assertEqual(traducidas["prefill_ns"], 1_600_000_000)
        self.assertEqual(traducidas["finish_reason"], "stop")

    def test_un_proveedor_que_no_mide_no_obliga_a_nada(self):
        self.assertEqual(_metrics({"eval_count": 3}), {"completion_tokens": 3})
        self.assertEqual(_metrics({}), {})

    def test_el_tracer_persiste_el_esquema_de_siempre(self):
        """El registro de latencia conserva las claves historicas y su orden,
        aunque por dentro el puerto hable en canonico."""
        from herramientas.internas.tracer import InferenceTrace

        eventos = []

        class Traza:
            def record_inference(self, event):
                eventos.append(event)

        solicitud = InferenceTrace(Traza(), "chat", "qwen3:4b", True)
        solicitud.set_metricas_generacion(_metrics(dict(self.CARGA_OLLAMA)))
        solicitud.finish("response_completed")
        persistido = eventos[0]["ollama"]
        self.assertEqual(list(persistido), [
            "prompt_eval_count", "prompt_eval_cached_count",
            "prompt_eval_duration", "eval_count", "eval_duration",
            "total_duration", "load_duration",
        ])
        self.assertEqual(persistido["prompt_eval_count"], 635)
        self.assertEqual(persistido["prompt_eval_duration"], 1_600_000_000)

    def test_las_claves_de_ollama_no_salven_del_adaptador_ni_del_tracer(self):
        permitidos = {Path("proveedores") / "llm" / "ollama.py",
                      Path("herramientas") / "internas" / "tracer.py"}
        marcadores = ("prompt_eval_count", "eval_duration", "done_reason",
                      "total_duration")
        culpables = []
        for paquete in self.PAQUETOS:
            for py in (DARK_PYTHON / paquete).rglob("*.py"):
                rel = py.relative_to(DARK_PYTHON)
                if rel in permitidos:
                    continue
                texto = py.read_text(encoding="utf-8", errors="replace")
                if any(m in texto for m in marcadores):
                    culpables.append(str(rel))
        self.assertEqual(
            culpables, [],
            "un consumidor volvio a leer metricas con vocabulario de Ollama; "
            "use las claves canonicas de METRICAS_GENERACION")


class TestFamiliaDeModeloSoloEnElContrato(unittest.TestCase):
    """Nadie fuera del contrato decide por nombre de modelo."""

    def test_devuelve_false_para_las_familias_con_cadena(self):
        self.assertIs(apagar_razonamiento("qwen3:4b-instruct-2507-q4_K_M"), False)
        self.assertIs(apagar_razonamiento("Qwen3:4B"), False)

    def test_devuelve_none_para_lo_que_no_la_emite(self):
        self.assertIsNone(apagar_razonamiento("llama:8b"))
        self.assertIsNone(apagar_razonamiento(""))
        self.assertIsNone(apagar_razonamiento(None))

    def test_ningun_consumidor_pregunta_por_la_familia(self):
        permitidos = {Path("proveedores") / "llm" / "contrato.py"}
        culpables = []
        for paquete in ("nucleo", "modulos", "herramientas", "proveedores",
                        "voz", "overlay", "acceso", "contratos",
                        "especialistas"):
            for py in (DARK_PYTHON / paquete).rglob("*.py"):
                rel = py.relative_to(DARK_PYTHON)
                if rel in permitidos:
                    continue
                texto = py.read_text(encoding="utf-8", errors="replace")
                if '"qwen3" in' in texto:
                    culpables.append(str(rel))
        self.assertEqual(
            culpables, [],
            "volvio la prueba de familia en un consumidor: use "
            "proveedores.llm.contrato.apagar_razonamiento(modelo)")

    def test_todo_reasoning_enabled_sale_de_una_sola_funcion(self):
        """La unica decision permitida es llamar al helper o un literal fijo."""
        vistos = 0
        for paquete in ("nucleo", "modulos", "herramientas", "especialistas",
                        "proveedores"):
            for py in (DARK_PYTHON / paquete).rglob("*.py"):
                arbol = ast.parse(py.read_text(encoding="utf-8"), str(py))
                for nodo in ast.walk(arbol):
                    if not isinstance(nodo, ast.Call):
                        continue
                    for kw in nodo.keywords:
                        if kw.arg != "reasoning_enabled":
                            continue
                        v = kw.value
                        permitida = (isinstance(v, ast.Constant) or (
                            isinstance(v, ast.Call)
                            and isinstance(v.func, ast.Name)
                            and v.func.id == "apagar_razonamiento"))
                        vistos += 1
                        self.assertTrue(
                            permitida,
                            f"{py.name}:{nodo.lineno} decide reasoning_enabled "
                            "con una expresion que no es el helper")
        self.assertGreaterEqual(
            vistos, 8,
            "la barrera no examino ninguna solicitud: se fue el keyword y el "
            "test paso sin comprobar nada")


if __name__ == "__main__":
    unittest.main()
