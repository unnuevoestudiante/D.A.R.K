"""Prueba de conformidad: el mismo contrato contra dos motores distintos.

El objetivo no es que llama.cpp funcione, sino comprobar que `ChatProvider` no
tiene forma de Ollama. Cada aserción se corre contra los dos adaptadores con
dobles HTTP, así que una asimetría real se ve aquí y no en una conversación.
"""
import ast
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from proveedores.llm.contrato import (  # noqa: E402
    ChatProvider, ChatRequest, METRICAS_GENERACION,
)
from proveedores.llm.ollama import OllamaChatProvider  # noqa: E402
from proveedores.llm.llamacpp import (  # noqa: E402
    LlamaCppProvider, OPCIONES_DE_ARRANQUE,
)
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402


class Respuesta:
    """Doble de una respuesta HTTP, con body o con líneas de stream."""

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
        self.peticiones = []

    def post(self, url, json=None, timeout=None, stream=False, **kw):
        self.peticiones.append({"url": url, "json": json or {},
                               "stream": bool(stream)})
        return self.response

    def get(self, url, timeout=None, **kw):
        self.peticiones.append({"url": url, "get": True})
        return self.response


def _valores(cuerpo):
    """Todas las claves del body, anidadas o no, con sus valores."""
    planos = {}
    for clave, valor in (cuerpo or {}).items():
        if isinstance(valor, dict):
            for sub, sub_valor in _valores(valor).items():
                planos.setdefault(sub, sub_valor)
        else:
            planos[clave] = valor
    return planos


SOLICITUD = ChatRequest(
    model="qwen3:4b",
    messages=[{"role": "system", "content": "sos Dark"},
              {"role": "user", "content": "hola"}],
    options={"temperature": 0.7, "top_p": 0.9, "top_k": 40,
             "max_output_tokens": 220, "repetition_penalty": 1.1,
             "repetition_window": 256, "context_tokens": 8192,
             "cpu_threads": 8, "batch_tokens": 512},
    response_format="json",
    residency="45m",
    reasoning_enabled=False,
)

# Los dos motores responden lo mismo sobre el puerto: mismas cifras, mismas
# decisiones. Las claves del motor solo aparecen en la columna de la izquierda.
RESPUESTAS = {
    "ollama": {
        "payload": {
            "model": "qwen3:4b", "done": True,
            "message": {"content": "{\"ok\":true}"},
            "prompt_eval_count": 635, "prompt_eval_cached_count": 630,
            "eval_count": 42, "prompt_eval_duration": 1_600_000_000,
            "eval_duration": 900_000_000, "done_reason": "stop",
        },
    },
    "llamacpp": {
        "payload": {
            "model": "qwen3:4b",
            "choices": [{"message": {"content": "{\"ok\":true}"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 635, "completion_tokens": 42,
                      "total_tokens": 677,
                      "prompt_tokens_details": {"cached_tokens": 630}},
            "timings": {"prompt_ms": 1600.0, "predicted_ms": 900.0,
                        "cache_n": 630},
        },
    },
}

PROVEEDORES = {
    "ollama": OllamaChatProvider,
    "llamacpp": LlamaCppProvider,
}

LINEAS_STREAM = {
    "ollama": [
        json.dumps({"message": {"content": "{\"o"}, "done": False}).encode(),
        json.dumps({"message": {"content": "k\":true}"}, "done": False}).encode(),
        json.dumps({"done": True, "eval_count": 2,
                    "prompt_eval_count": 635}).encode(),
    ],
    "llamacpp": [
        b'data: {"choices":[{"delta":{"content":"{\\"o"}}]}',
        b'data: {"choices":[{"delta":{"content":"k\\":true}"}}]}',
        # Orden real de llama-server: primero el chunk con finish_reason (sin
        # usage), despues un chunk solo con usage y choices vacios, y al final
        # el centinela. Ningun consumidor del puerto ve los dos primeros.
        b'data: {"choices":[{"delta":{"content":""},"finish_reason":"stop"}]}',
        b'data: {"choices":[],"usage":{"completion_tokens":2,'
        b'"prompt_tokens":635}}',
        b"data: [DONE]",
    ],
}


class _SinAvisos(unittest.TestCase):
    """El adaptador avisa por consola las opciones que no puede mandar.

    En la prueba eso es ruido: el aviso se exige explicitamente en
    `test_tres_opciones_del_contrato_solo_existen_al_arrancar` con un log inyectado.
    """

    def setUp(self):
        silencio = patch("builtins.print", lambda *a, **kw: None)
        silencio.start()
        self.addCleanup(silencio.stop)


class TestConformidadDeLosDosAdaptadores(_SinAvisos):
    """Lo que los dos adaptadores prometen por igual."""

    def _Proveedor(self, nombre, response=None, **kw):
        return PROVEEDORES[nombre](session=Sesion(response or Respuesta()),
                                   base_url="http://motor:1", **kw)

    def test_los_dos_cumplen_el_puerto(self):
        for nombre in PROVEEDORES:
            with self.subTest(motor=nombre):
                self.assertIsInstance(self._Proveedor(nombre), ChatProvider)

    def test_una_solicitud_canonica_llega_con_las_claves_del_motor(self):
        for nombre, esperado in (
            ("ollama", {"num_ctx": 8192, "num_thread": 8, "num_batch": 512,
                        "num_predict": 220, "repeat_penalty": 1.1,
                        "repeat_last_n": 256, "top_k": 40,
                        "temperature": 0.7, "top_p": 0.9}),
            ("llamacpp", {"n_predict": 220, "repeat_penalty": 1.1,
                          "repeat_last_n": 256, "top_k": 40,
                          "temperature": 0.7, "top_p": 0.9}),
        ):
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta())
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                proveedor.complete(SOLICITUD)
                planos = _valores(sesion.peticiones[0]["json"])
                for clave, valor in esperado.items():
                    self.assertEqual(planos.get(clave), valor)

    def test_ningun_motor_recibe_claves_del_contrato(self):
        # top_k/temperature/top_p se deletrean igual en los dos motores: ahí el
        # nombre del contrato ES el nombre del API. Todo lo demás del vocabulario
        # neutro tiene que desaparecer en la traducción; si aparece, un adaptador
        # se saltó su tabla de alias y el motor recibirá opciones que ignora.
        grafia_compartida = {"top_k", "temperature", "top_p"}
        for nombre in PROVEEDORES:
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta())
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                proveedor.complete(SOLICITUD)
                planos = _valores(sesion.peticiones[0]["json"])
                filtradas = (set(SOLICITUD.options) | {"residency",
                                                       "reasoning_enabled",
                                                       "response_format"})
                filtradas -= grafia_compartida
                self.assertEqual(set(planos) & filtradas, set(),
                                 "el vocabulario del contrato se filtró al body "
                                 "del motor: falta una traduccion en el adaptador")

    def test_el_modo_json_se_activa_en_cada_motor(self):
        for nombre, clave, valor in (("ollama", "format", "json"),
                                     ("llamacpp", "response_format",
                                      {"type": "json_object"})):
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta())
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                proveedor.complete(SOLICITUD)
                self.assertEqual(sesion.peticiones[0]["json"][clave], valor)

    def test_un_esquema_json_viaja_por_el_puerto(self):
        # response_format admite un Mapping (esquema JSON), no solo "json".
        # Ollama lo pasa tal cual en `format`; llama.cpp lo envuelve en
        # json_object + schema. El extractor local usa la vía Ollama.
        esquema = {"type": "object",
                   "properties": {"propuestas": {"type": "array"}},
                   "required": ["propuestas"]}
        solicitud = ChatRequest(model="qwen3:4b",
                                messages=[{"role": "user", "content": "hola"}],
                                response_format=esquema)
        sesion = Sesion(Respuesta())
        OllamaChatProvider(session=sesion, base_url="http://motor:1").complete(solicitud)
        self.assertEqual(sesion.peticiones[0]["json"]["format"], esquema)

        sesion = Sesion(Respuesta())
        LlamaCppProvider(session=sesion, base_url="http://motor:1").complete(solicitud)
        self.assertEqual(sesion.peticiones[0]["json"]["response_format"],
                         {"type": "json_object", "schema": esquema})

    def test_apagar_el_razonamiento_llega_al_motor(self):
        for nombre, esperado in (("ollama", ("think", False)),
                                 ("llamacpp", ("reasoning_effort", "none"))):
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta())
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                proveedor.complete(SOLICITUD)
                self.assertEqual(sesion.peticiones[0]["json"][esperado[0]],
                                 esperado[1])

    def test_los_mismos_numeros_salen_por_el_puerto_de_los_dos_motores(self):
        """La asercion fuerte: el contrato entrega cifras comparables."""
        por_motor = {}
        for nombre, caso in RESPUESTAS.items():
            sesion = Sesion(Respuesta(caso["payload"]))
            proveedor = PROVEEDORES[nombre](session=sesion,
                                            base_url="http://motor:1")
            resultado = proveedor.complete(SOLICITUD)
            self.assertEqual(resultado.content, "{\"ok\":true}")
            self.assertTrue(resultado.finished)
            self.assertEqual(resultado.status_code, 200)
            por_motor[nombre] = dict(resultado.metrics)

        for clave in ("prompt_tokens", "completion_tokens",
                      "cached_prompt_tokens", "prefill_ns", "decode_ns",
                      "finish_reason"):
            self.assertEqual(por_motor["ollama"].get(clave),
                             por_motor["llamacpp"].get(clave),
                             f"`{clave}` no coincide entre motores")
        self.assertEqual(por_motor["ollama"]["prompt_tokens"], 635)

    def test_el_evento_de_cierre_trae_las_metricas(self):
        """Lo que el consumidor hace: lee cifras en `finished` y deja de mirar.

        Especialista conversacional consulta las metricas una sola vez, sobre el
        evento `finished`. Si un motor las manda en otro chunk, el adaptador
        tiene que llevarlas hasta ese evento o el turno sale con ceros.
        """
        for nombre in PROVEEDORES:
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta(lines=LINEAS_STREAM[nombre]))
                stream = PROVEEDORES[nombre](session=sesion,
                                            base_url="http://motor:1").stream(SOLICITUD)
                eventos = list(stream.iter_events())
                stream.close()
                self.assertEqual("".join(e.content for e in eventos),
                                 "{\"ok\":true}")
                finales = [e for e in eventos if e.finished]
                self.assertEqual(len(finales), 1, eventos)
                self.assertEqual(finales[0].metrics.get("completion_tokens"), 2)
                self.assertEqual(finales[0].metrics.get("prompt_tokens"), 635)

    def test_lo_que_un_motor_no_mide_no_aparece_inventado(self):
        for nombre in PROVEEDORES:
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta(RESPUESTAS[nombre]["payload"]))
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                metricas = dict(proveedor.complete(SOLICITUD).metrics)
                self.assertTrue(set(metricas) <= set(METRICAS_GENERACION),
                                metricas.keys() - set(METRICAS_GENERACION))

    def test_ambos_streaming_devuelven_el_mismo_texto(self):
        for nombre in PROVEEDORES:
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta(lines=LINEAS_STREAM[nombre]))
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                stream = proveedor.stream(SOLICITUD)
                eventos = list(stream.iter_events())
                stream.close()
                self.assertEqual("".join(e.content for e in eventos),
                                 "{\"ok\":true}")
                self.assertTrue(any(e.finished for e in eventos))
                self.assertTrue(sesion.response.closed,
                                "el stream no se cierra: la conexion queda abierta")

    def test_los_dos_reportan_salud_y_modelos_residentes(self):
        for nombre, payload in (
            ("ollama", {"models": [{"name": "qwen3:4b"}]}),
            ("llamacpp", {"data": [{"id": "qwen3:4b"}]}),
        ):
            with self.subTest(motor=nombre):
                sesion = Sesion(Respuesta(payload))
                proveedor = PROVEEDORES[nombre](session=sesion,
                                                base_url="http://motor:1")
                self.assertTrue(proveedor.health())
                self.assertEqual(list(proveedor.loaded_models()), ["qwen3:4b"])


class TestAsimetriasConocidas(_SinAvisos):
    """Diferencias reales entre motores: quedan escritas, no escondidas."""

    def test_la_residencia_no_existe_por_solicitud_en_llama_cpp(self):
        """Ollama acepta keep_alive por request; llama.cpp lo arranca con --keep-alive.

        Es la asimetria mas incomoda del puerto: `residency` es una capacidad que
        solo un motor tiene.
        """
        sesion = Sesion(Respuesta())
        LlamaCppProvider(session=sesion, base_url="http://motor:1").complete(SOLICITUD)
        body = sesion.peticiones[0]["json"]
        self.assertNotIn("keep_alive", _valores(body))

        sesion = Sesion(Respuesta())
        OllamaChatProvider(session=sesion, base_url="http://motor:1").complete(SOLICITUD)
        self.assertEqual(sesion.peticiones[0]["json"]["keep_alive"], "45m")

    def test_tres_opciones_del_contrato_solo_existen_al_arrancar(self):
        sesion = Sesion(Respuesta())
        avisos = []
        proveedor = LlamaCppProvider(session=sesion, base_url="http://motor:1",
                                     log=avisos.append)
        proveedor.complete(SOLICITUD)
        planos = _valores(sesion.peticiones[0]["json"])
        self.assertEqual(set(OPCIONES_DE_ARRANQUE) & set(planos), set())
        self.assertEqual(len(avisos), 1)
        for opcion in OPCIONES_DE_ARRANQUE:
            self.assertIn(opcion, avisos[0])

    def test_el_cacheo_del_prefijo_se_pide_explicitamente_en_llama_cpp(self):
        """Sin cache_prompt cada turno re-prefila el prompt completo: en Ollama
        el cacheo es implicito y ahi se decide donde recortar."""
        sesion = Sesion(Respuesta())
        LlamaCppProvider(session=sesion, base_url="http://motor:1").complete(SOLICITUD)
        self.assertIs(sesion.peticiones[0]["json"]["cache_prompt"], True)


class TestFabricaElijeMotor(unittest.TestCase):
    def test_el_entorno_selecciona_cada_adaptador(self):
        for valor, clase in (("ollama", OllamaChatProvider),
                             ("llamacpp", LlamaCppProvider),
                             ("llama.cpp", LlamaCppProvider)):
            with self.subTest(provider=valor):
                with patch.dict(os.environ, {"DARK_LLM_PROVIDER": valor}):
                    self.assertIsInstance(
                        crear_proveedor_chat(session=Sesion(Respuesta())), clase)

    def test_sin_variable_sigue_siendo_ollama(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(
                crear_proveedor_chat(session=Sesion(Respuesta())),
                OllamaChatProvider)

    def test_la_lista_de_conocidos_saluda_los_dos(self):
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "vllm"}):
            with self.assertRaisesRegex(ValueError, "llamacpp"):
                crear_proveedor_chat(session=Sesion(Respuesta()))


class TestNadieImportaUnMotorDirectamente(unittest.TestCase):
    PAQUETOS = ("nucleo", "modulos", "herramientas", "proveedores", "voz",
                "overlay", "acceso", "contratos", "especialistas")
    MOTORES = {"ollama", "llamacpp"}

    def test_solo_la_fabrica_importa_algun_adaptador(self):
        permitidos = {Path("proveedores") / "llm" / "fabrica.py"}
        culpables = []
        for paquete in self.PAQUETOS:
            for py in (DARK_PYTHON / paquete).rglob("*.py"):
                rel = py.relative_to(DARK_PYTHON)
                if rel in permitidos or rel.parts[-1] in self.MOTORES:
                    continue
                arbol = ast.parse(py.read_text(encoding="utf-8"), str(rel))
                for nodo in ast.walk(arbol):
                    nombre = ""
                    if isinstance(nodo, ast.ImportFrom):
                        nombre = nodo.module or ""
                    elif isinstance(nodo, ast.Import):
                        nombre = ",".join(a.name for a in nodo.names)
                    if any(f"llm.{m}" in nombre or nombre == m
                           for m in self.MOTORES):
                        culpables.append(f"{rel} -> {nombre}")
        self.assertEqual(culpables, [],
                         "un consumidor volvio a importar un motor: la eleccion "
                         "se hace con DARK_LLM_PROVIDER, no con el nombre")


if __name__ == "__main__":
    unittest.main()
