"""Pruebas del motor remoto y del conmutador API/local.

Lo que se prueba aqui no es que el proveedor funcione: es la regla de
conmutacion. Un fallo del remoto antes del primer token tiene que dar el MISMO
prompt al local con el MISMO timeout, y un remoto que ya emitio no puede
provocar un segundo intento en el mismo turno. Al reves: un enfriamiento por 429
tiene que evitar la ventana de espera, no el turno.
"""
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from proveedores.llm.contrato import ChatProvider, ChatRequest  # noqa: E402
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402
from proveedores.llm.ollama import OllamaChatProvider  # noqa: E402
from proveedores.llm import remoto  # noqa: E402
from proveedores.llm.conmutado import (  # noqa: E402
    ProveedorConmutado, _acotar,
)
from proveedores.llm.remoto import (  # noqa: E402
    ErrorRemoto, RemotoChatProvider, RemotoStream,
)

LOCAL = "qwen3:4b-instruct-2507-q4_K_M"


def sse(*fragmentos, usage=None, done=True):
    """Lineas de un stream OpenAI-compatible, como las devolveria el servidor."""
    lineas = []
    for texto in fragmentos:
        lineas.append("data: " + json.dumps(
            {"choices": [{"delta": {"content": texto}}]}))
    if usage is not None:
        lineas.append("data: " + json.dumps({"choices": [{"delta": {}}],
                                             "usage": usage}))
    if done:
        lineas.append("data: [DONE]")
    return lineas


class Respuesta:
    """Doble de una respuesta HTTP, con body o con lineas de stream."""

    def __init__(self, data=None, lines=(), texto="", estado=200, headers=None):
        self._data = data or {}
        self._lines = lines
        self._texto = texto
        self.status_code = estado
        self.headers = headers or {}
        self.closed = False

    def json(self):
        return self._data

    @property
    def text(self):
        return self._texto

    def iter_lines(self):
        yield from self._lines

    def close(self):
        self.closed = True


class Sesion:
    """Doble de requests.Session: consume una cola de respuestas o errores."""

    def __init__(self, *resultados):
        self.peticiones = []
        self.cabeceras = []
        self._cola = list(resultados)

    def _siguiente(self, url, cuerpo, headers):
        self.peticiones.append({"url": url, "json": cuerpo or {}})
        self.cabeceras.append(headers or {})
        if not self._cola:
            raise AssertionError("la sesion no esperaba mas llamadas")
        siguiente = self._cola.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    def post(self, url, json=None, timeout=None, stream=False, headers=None,
             **kw):
        return self._siguiente(url, json, headers)

    def get(self, url, timeout=None, headers=None, **kw):
        return self._siguiente(url, {}, headers)


def config_usable(**cambios):
    cfg = {
        "enabled": True, "timeout": 60.0, "archivo_existe": True,
        "enfriamientos": {"429": 60.0, "diario": 3600.0, "5xx": 300.0,
                          "auth": 86400.0},
        "providers": [{"name": "groq-chat",
                       "base_url": "https://api.ejemplo.test/v1",
                       "api_key": "clave-de-prueba",
                       "model": "ejemplo/modelo-chat"}],
    }
    cfg.update(cambios)
    return cfg


class Casabase(unittest.TestCase):
    """Config y enfriamientos en blanco en cada prueba, sin red de verdad."""

    def setUp(self):
        self.resetear_estado()
        self.addCleanup(self.resetear_estado)
        for variable in ("DARK_CHAT_API_KEY", "DARK_CHAT_API_MODEL",
                         "DARK_CHAT_API_URL", "DARK_LLM_PROVIDER",
                         "DARK_LLM_LOCAL_PROVIDER", "DARK_API_TTFT_TOPE_SEGUNDOS",
                         "DARK_OLLAMA_URL"):
            os.environ.pop(variable, None)
            self.addCleanup(os.environ.pop, variable, None)

    def resetear_estado(self):
        remoto._cache_config = None
        remoto._cache_ts = 0.0
        remoto._agotados.clear()

    def forzar_config(self, cfg=None):
        remoto._cache_config = cfg if cfg is not None else config_usable()
        remoto._cache_ts = time.time()
        return remoto._cache_config

    def solicitud(self, opciones=None):
        base = {"context_tokens": 2048, "max_output_tokens": 100,
                "temperature": 0.35, "top_p": 0.9, "top_k": 40,
                "cpu_threads": 16}
        base.update(opciones or {})
        return ChatRequest(model=LOCAL,
                           messages=[{"role": "system", "content": "sos Dark"},
                                     {"role": "user", "content": "hola"}],
                           options=base)


# =========================================================================
#  ADAPTADOR REMOTO
# =========================================================================

class TestAdaptadorRemoto(Casabase):
    def test_manda_el_modelo_configurado_no_el_de_la_solicitud(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(lines=sse("Hola")))
        lista = list(RemotoChatProvider(session=sesion)
                     .stream(self.solicitud()).iter_events())
        self.assertEqual(sesion.peticiones[0]["json"]["model"],
                         "ejemplo/modelo-chat")
        self.assertEqual(sesion.peticiones[0]["url"],
                         "https://api.ejemplo.test/v1/chat/completions")
        self.assertEqual("".join(e.content for e in lista), "Hola")

    def test_traduce_opciones_y_omite_las_sin_equivalente(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(lines=sse("x")))
        RemotoChatProvider(session=sesion).stream(self.solicitud())
        cuerpo = sesion.peticiones[0]["json"]
        self.assertEqual(cuerpo["max_tokens"],
                         100 + remoto.HOLGURA_RAZONAMIENTO_TOKENS)
        self.assertEqual(cuerpo["temperature"], 0.35)
        self.assertEqual(cuerpo["top_p"], 0.9)
        for clave_ajena in ("top_k", "context_tokens", "cpu_threads",
                            "repetition_penalty", "num_ctx", "num_predict",
                            "num_thread", "think", "keep_alive", "repeat_penalty"):
            self.assertNotIn(clave_ajena, cuerpo)

    def test_la_holgura_solo_aplica_si_hay_presupuesto(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(lines=sse("x")))
        RemotoChatProvider(session=sesion).stream(
            self.solicitud({"max_output_tokens": None}))
        self.assertNotIn("max_tokens", sesion.peticiones[0]["json"])

    def test_el_aviso_de_opciones_no_repetidas_sale_una_sola_vez(self):
        self.forzar_config()
        avisos = []
        sesion = Sesion(Respuesta(lines=sse("a")), Respuesta(lines=sse("b")))
        proveedor = RemotoChatProvider(session=sesion, log=avisos.append)
        proveedor.stream(self.solicitud())
        proveedor.stream(self.solicitud())
        self.assertEqual(len([a for a in avisos if "top_k" in a]), 1)

    def test_bearer_y_response_format(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(data={"choices": [
            {"message": {"content": "ok"}, "finish_reason": "stop"}]}))
        resultado = RemotoChatProvider(session=sesion).complete(
            self.solicitud(), timeout=20)
        self.assertEqual(
            sesion.cabeceras[0]["Authorization"], "Bearer clave-de-prueba")
        self.assertEqual(resultado.content, "ok")
        self.assertEqual(resultado.metrics["finish_reason"], "stop")

    def test_response_format_json_es_objeto(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(data={"choices": [
            {"message": {"content": "{}"}}]}))
        solicitud = ChatRequest(model=LOCAL, messages=[],
                                response_format="json")
        RemotoChatProvider(session=sesion).complete(solicitud)
        self.assertEqual(sesion.peticiones[0]["json"]["response_format"],
                         {"type": "json_object"})

    def test_stream_pide_usage_y_lee_metricas_del_cierre(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(lines=sse(
            "Buen", "as", usage={"prompt_tokens": 1400,
                                 "completion_tokens": 12,
                                 "prompt_tokens_details": {"cached_tokens": 1345}})))
        eventos = list(RemotoChatProvider(session=sesion)
                       .stream(self.solicitud()).iter_events())
        self.assertEqual(sesion.peticiones[0]["json"]["stream_options"],
                         {"include_usage": True})
        self.assertEqual("".join(e.content for e in eventos), "Buenas")
        final = eventos[-1]
        self.assertTrue(final.finished)
        self.assertEqual(final.metrics["prompt_tokens"], 1400)
        self.assertEqual(final.metrics["cached_prompt_tokens"], 1345)
        self.assertEqual(final.metrics["completion_tokens"], 12)

    def test_un_200_vacio_es_un_fallo_no_un_silencio(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(data={"choices": [
            {"message": {"content": "   "}}]}))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "respuesta vacia")

    def test_429_enfria_al_proveedor_por_minuto(self):
        cfg = self.forzar_config()
        sesion = Sesion(Respuesta(estado=429, texto="Rate limit reached"))
        proveedor = RemotoChatProvider(session=sesion)
        self.assertTrue(proveedor.disponible())
        with self.assertRaises(ErrorRemoto) as ctx:
            proveedor.complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "429 por minuto")
        self.assertEqual(ctx.exception.agotado, cfg["enfriamientos"]["429"])
        self.assertFalse(proveedor.disponible())
        with self.assertRaises(ErrorRemoto):
            proveedor.complete(self.solicitud())
        self.assertEqual(len(sesion.peticiones), 1, "aqui no hay reintento")

    def test_429_diario_enfria_hasta_el_dia_siguiente(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=429, texto="daily limit exceeded"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "429 diario")
        self.assertEqual(ctx.exception.agotado, 3600.0)

    def test_5xx_enfria_y_auth_enfria_un_dia(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=503, texto="overloaded"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "HTTP 503 (server)")
        self.assertEqual(ctx.exception.agotado, 300.0)

        remoto._agotados.clear()
        sesion = Sesion(Respuesta(estado=401, texto="bad key"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "HTTP 401 (auth)")
        self.assertEqual(ctx.exception.agotado, 86400.0)

    def test_un_enfriamiento_bloquea_la_siguiente_llamada(self):
        """El 5xx no se vuelve a intentar: el enfriamiento corta antes del POST."""
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=503, texto="overloaded"))
        proveedor = RemotoChatProvider(session=sesion)
        with self.assertRaises(ErrorRemoto):
            proveedor.complete(self.solicitud())
        with self.assertRaises(ErrorRemoto) as ctx:
            proveedor.complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "sin proveedor de chat disponible")
        self.assertFalse(proveedor.disponible())
        self.assertEqual(len(sesion.peticiones), 1)

    def test_sin_conexion_es_fallo_clasificado_sin_enfriar(self):
        self.forzar_config()
        sesion = Sesion(requests.exceptions.ConnectionError("no dns"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertIn("sin conexion", ctx.exception.motivo)
        self.assertEqual(ctx.exception.agotado, 0.0)
        self.assertTrue(self._sigue_disponible())

    def _sigue_disponible(self):
        return RemotoChatProvider(session=Sesion()).disponible()

    def test_un_400_no_enfria_porque_el_fallo_es_nuestro(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=400, texto="unknown field"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.agotado, 0.0)
        self.assertTrue(self._sigue_disponible())

    def test_sin_config_o_sin_clave_no_hay_remoto(self):
        self.forzar_config(config_usable(enabled=False))
        proveedor = RemotoChatProvider(session=Sesion())
        self.assertFalse(proveedor.disponible())
        self.forzar_config(config_usable(providers=[]))
        self.assertFalse(proveedor.disponible())

    def test_un_remoto_no_reporta_modelos_residentes(self):
        self.forzar_config()
        self.assertEqual(RemotoChatProvider(session=Sesion()).loaded_models(), [])

    def test_claves_de_env_arman_un_proveedor_sin_archivo(self):
        os.environ["DARK_CHAT_API_KEY"] = "k-de-prueba"
        os.environ["DARK_CHAT_API_MODEL"] = "modelo/env"
        sesion = Sesion(Respuesta(lines=sse("ok")))
        proveedor = RemotoChatProvider(session=sesion)
        self.assertTrue(proveedor.disponible())
        self.assertEqual(proveedor.nombre(), "env")
        proveedor.stream(self.solicitud())
        self.assertEqual(sesion.peticiones[0]["json"]["model"], "modelo/env")


# =========================================================================
#  MODO PACIENTE: la cuota gratuita no rompe un trabajo largo
# =========================================================================

def ok(texto="listo", headers=None):
    return Respuesta(data={"choices": [{"message": {"content": texto}}]},
                     headers=headers)


class TestCupoDeCabeceras(Casabase):
    def test_lee_las_duraciones_de_groq(self):
        self.assertEqual(remoto._duracion("7.66s"), 7.66)
        self.assertAlmostEqual(remoto._duracion("2m59.56s"), 179.56)
        self.assertEqual(remoto._duracion("500ms"), 0.5)
        self.assertEqual(remoto._duracion("1h2m"), 3720.0)
        self.assertEqual(remoto._duracion("12"), 12.0)
        self.assertIsNone(remoto._duracion(""))
        self.assertIsNone(remoto._duracion("pronto"))

    def test_lee_el_cupo_sin_importar_mayusculas_y_omite_lo_ausente(self):
        cupo = remoto.leer_cupo({"Retry-After": "3",
                                 "X-RateLimit-Remaining-Tokens": "1200",
                                 "x-ratelimit-reset-tokens": "7.5s"})
        self.assertEqual(cupo, {"retry_after": 3.0, "tokens_restantes": 1200,
                                "reset_tokens": 7.5})
        self.assertEqual(remoto.leer_cupo(None), {})

    def test_el_429_respeta_el_retry_after_y_no_el_fijo(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=429, texto="Rate limit reached",
                                  headers={"retry-after": "7"}))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "429 por minuto")
        self.assertEqual(ctx.exception.agotado, 7 + remoto.MARGEN_ESPERA_SEGUNDOS)
        self.assertFalse(ctx.exception.diario)

    def test_un_retry_after_de_horas_es_cuota_diaria(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=429, texto="Rate limit reached",
                                  headers={"retry-after": "7200"}))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.motivo, "429 diario")
        self.assertTrue(ctx.exception.diario)
        self.assertEqual(ctx.exception.agotado, 7200.0)

    def test_espera_preventiva_solo_si_no_cabe_y_el_reset_es_corto(self):
        remoto._cupos.clear()
        self.addCleanup(remoto._cupos.clear)
        remoto._anotar_cupo("p", {"x-ratelimit-remaining-tokens": "100",
                                  "x-ratelimit-reset-tokens": "20s"})
        self.assertEqual(remoto.espera_preventiva("p", 50), 0.0)
        espera = remoto.espera_preventiva("p", 5000)
        self.assertGreater(espera, 19.0)
        self.assertLessEqual(espera, 20 + remoto.MARGEN_ESPERA_SEGUNDOS)
        # Reset de horas: no se duerme en silencio, que lo diga el 429 diario.
        remoto._anotar_cupo("q", {"x-ratelimit-remaining-requests": "0",
                                  "x-ratelimit-reset-requests": "5h"})
        self.assertEqual(remoto.espera_preventiva("q", 10), 0.0)
        self.assertEqual(remoto.espera_preventiva("desconocido", 10 ** 6), 0.0)


class TestModoPaciente(Casabase):
    def setUp(self):
        super().setUp()
        remoto._cupos.clear()
        self.addCleanup(remoto._cupos.clear)
        self.dormido = []
        self.avisos = []

    def proveedor(self, *respuestas, **kw):
        self.sesion = Sesion(*respuestas)
        return RemotoChatProvider(session=self.sesion, log=lambda *_: None,
                                  dormir=self.dormido.append, **kw)

    def avisar(self, segundos, motivo, nombre):
        self.avisos.append((round(segundos, 2), motivo, nombre))

    def test_un_429_por_minuto_espera_y_repite_la_misma_llamada(self):
        self.forzar_config()
        prov = self.proveedor(
            Respuesta(estado=429, texto="Rate limit reached for tokens per minute",
                      headers={"retry-after": "3"}),
            ok("hecho"))
        resultado = prov.complete_paciente(self.solicitud(), al_esperar=self.avisar)
        self.assertEqual(resultado.content, "hecho")
        self.assertEqual(len(self.sesion.peticiones), 2)
        self.assertEqual(self.sesion.peticiones[0]["json"],
                         self.sesion.peticiones[1]["json"])
        self.assertAlmostEqual(sum(self.dormido), 3 + remoto.MARGEN_ESPERA_SEGUNDOS)
        self.assertEqual(self.avisos, [(4.0, "límite por minuto", "groq-chat")])
        self.assertTrue(prov.disponible(), "tras la espera el proveedor vuelve a estar libre")

    def test_varios_429_seguidos_no_rompen_el_trabajo(self):
        self.forzar_config()
        limite = Respuesta(estado=429, texto="rate limit", headers={"retry-after": "1"})
        prov = self.proveedor(limite, limite, limite, ok())
        self.assertEqual(prov.complete_paciente(self.solicitud()).content, "listo")
        self.assertEqual(len(self.sesion.peticiones), 4)

    def test_no_cambia_de_proveedor_a_mitad_del_trabajo(self):
        segundo = {"name": "otro", "base_url": "https://otro.test/v1",
                   "api_key": "k2", "model": "otro/modelo"}
        self.forzar_config(config_usable(providers=[
            config_usable()["providers"][0], segundo]))
        prov = self.proveedor(
            ok("uno"),
            Respuesta(estado=429, texto="rate limit", headers={"retry-after": "2"}),
            ok("dos"))
        prov.complete_paciente(self.solicitud())
        prov.complete_paciente(self.solicitud())
        urls = {p["url"] for p in self.sesion.peticiones}
        self.assertEqual(urls, {"https://api.ejemplo.test/v1/chat/completions"})
        prov.soltar_trabajo()
        self.assertIsNone(prov._fijado)

    def test_espera_antes_de_llamar_si_el_cupo_no_alcanza(self):
        self.forzar_config()
        prov = self.proveedor(
            ok("a", headers={"x-ratelimit-remaining-tokens": "10",
                             "x-ratelimit-reset-tokens": "30s"}),
            ok("b"))
        prov.complete_paciente(self.solicitud())
        self.assertEqual(self.dormido, [])
        prov.complete_paciente(self.solicitud(), al_esperar=self.avisar)
        self.assertGreater(sum(self.dormido), 29.0)
        self.assertEqual(self.avisos[0][1], "cupo del minuto casi agotado")
        self.assertEqual(len(self.sesion.peticiones), 2, "nunca se provocó el 429")

    def test_el_429_diario_no_se_espera_se_avisa(self):
        self.forzar_config()
        prov = self.proveedor(Respuesta(
            estado=429, texto="Rate limit reached on tokens per day (TPD)"))
        with self.assertRaises(ErrorRemoto) as ctx:
            prov.complete_paciente(self.solicitud())
        self.assertTrue(ctx.exception.diario)
        self.assertEqual(self.dormido, [])

    def test_credencial_invalida_falla_sin_esperar(self):
        self.forzar_config()
        prov = self.proveedor(Respuesta(estado=401, texto="invalid api key"))
        with self.assertRaises(ErrorRemoto) as ctx:
            prov.complete_paciente(self.solicitud())
        self.assertTrue(ctx.exception.diario, "sin otro proveedor, esperar no lo arregla hoy")
        self.assertEqual(len(self.sesion.peticiones), 1)
        self.assertEqual(self.dormido, [])

    def dos_proveedores(self):
        segundo = {"name": "groq", "base_url": "https://groq.test/v1",
                   "api_key": "k2", "model": "qwen"}
        self.forzar_config(config_usable(providers=[
            config_usable()["providers"][0], segundo]))

    def test_una_clave_rechazada_al_empezar_pasa_al_siguiente(self):
        """Gemini contesta una clave inválida con 400, no con 401 (medido el 25-11-2026)."""
        self.dos_proveedores()
        prov = self.proveedor(
            Respuesta(estado=400, texto='{"error": {"message": "Please pass a valid API key"}}'),
            ok("del segundo"))
        self.assertEqual(prov.complete_paciente(self.solicitud()).content, "del segundo")
        self.assertEqual(self.sesion.peticiones[1]["url"], "https://groq.test/v1/chat/completions")
        self.assertEqual(self.dormido, [])

    GRANDE = ('{"error":{"message":"Request too large for model `qwen/qwen3.8-27b` in '
              'organization `org` service tier `on_demand` on output tokens per minute '
              '(OTPM): Limit 1000, Requested 1334. The request\'s expected output tokens '
              'exceed the enforced limit; reduce max_tokens","code":"rate_limit_exceeded"}}')

    def test_si_la_salida_no_cabe_en_el_minuto_se_pide_menos_sin_esperar(self):
        """Medido con Groq el 25-11-2026: reset de 0,001 s y el mismo 429 cada vez."""
        self.forzar_config()
        prov = self.proveedor(
            Respuesta(estado=429, texto=self.GRANDE,
                      headers={"x-ratelimit-reset-tokens": "1ms"}),
            ok("cabe"))
        resultado = prov.complete_paciente(self.solicitud({"max_output_tokens": 3000}))
        self.assertEqual(resultado.content, "cabe")
        self.assertEqual(self.dormido, [], "esperar no lo arregla: no se espera")
        tope = 1000 - remoto.HOLGURA_RAZONAMIENTO_TOKENS - 50
        self.assertEqual(self.sesion.peticiones[1]["json"]["max_tokens"],
                         tope + remoto.HOLGURA_RAZONAMIENTO_TOKENS)
        self.assertTrue(prov.disponible(), "el proveedor no se enfría por esto")

    def test_si_no_cabe_de_ninguna_forma_pasa_al_siguiente_proveedor(self):
        self.dos_proveedores()
        sin_salida = self.GRANDE.replace("output tokens per minute (OTPM)",
                                         "tokens per minute (TPM)")
        prov = self.proveedor(Respuesta(estado=429, texto=sin_salida), ok("del segundo"))
        self.assertEqual(prov.complete_paciente(self.solicitud()).content, "del segundo")
        prov.soltar_trabajo()
        self.assertEqual(prov._descartados, set(), "el descarte es solo de ese trabajo")

    def test_los_choques_seguidos_con_reset_minimo_alargan_la_espera(self):
        self.forzar_config()
        choque = Respuesta(estado=429, texto="Rate limit reached", headers={"retry-after": "0"})
        prov = self.proveedor(choque, choque, choque, choque, ok())
        prov.complete_paciente(self.solicitud())
        self.assertGreaterEqual(sum(self.dormido), 1 + 2 + 4 + 8)

    def test_a_mitad_del_trabajo_no_se_cambia_de_proveedor_ni_por_la_clave(self):
        self.dos_proveedores()
        prov = self.proveedor(ok("uno"), Respuesta(estado=401, texto="revoked"))
        prov.complete_paciente(self.solicitud())
        with self.assertRaises(ErrorRemoto):
            prov.complete_paciente(self.solicitud())
        self.assertEqual(len(self.sesion.peticiones), 2)

    def test_un_400_que_no_es_de_clave_sigue_siendo_nuestro(self):
        self.forzar_config()
        sesion = Sesion(Respuesta(estado=400, texto="unknown field top_k"))
        with self.assertRaises(ErrorRemoto) as ctx:
            RemotoChatProvider(session=sesion).complete(self.solicitud())
        self.assertEqual(ctx.exception.agotado, 0.0)

    def test_red_caida_y_5xx_reintentan_con_esperas_crecientes(self):
        self.forzar_config()
        prov = self.proveedor(requests.exceptions.ConnectionError("sin red"),
                              Respuesta(estado=503, texto="overloaded"),
                              ok("volvió"))
        self.assertEqual(prov.complete_paciente(self.solicitud()).content, "volvió")
        self.assertEqual(sum(self.dormido), 5.0 + 10.0)

    def test_red_caida_de_forma_persistente_termina_fallando(self):
        self.forzar_config()
        caidas = [requests.exceptions.ConnectionError("sin red")] * (remoto.REINTENTOS_RED + 1)
        prov = self.proveedor(*caidas)
        with self.assertRaises(ErrorRemoto):
            prov.complete_paciente(self.solicitud())
        self.assertEqual(len(self.sesion.peticiones), remoto.REINTENTOS_RED + 1)

    def test_cancelar_corta_la_espera(self):
        self.forzar_config()
        prov = self.proveedor(Respuesta(estado=429, texto="rate limit",
                                        headers={"retry-after": "50"}))
        with self.assertRaises(ErrorRemoto) as ctx:
            prov.complete_paciente(self.solicitud(),
                                   cancelado=lambda: len(self.dormido) >= 3)
        self.assertEqual(ctx.exception.motivo, "cancelado")
        self.assertEqual(len(self.dormido), 3)

    def test_todos_enfriados_por_minuto_espera_al_que_se_libera_antes(self):
        self.forzar_config()
        remoto._enfriar("groq-chat", 30)
        prov = self.proveedor(ok())
        self.assertEqual(prov.complete_paciente(self.solicitud()).content, "listo")
        self.assertGreater(sum(self.dormido), 29.0, "respeta lo que quedaba del enfriamiento")

    def test_todos_enfriados_por_el_dia_no_espera(self):
        self.forzar_config()
        remoto._enfriar("groq-chat", 3600 * 5)
        prov = self.proveedor()
        with self.assertRaises(ErrorRemoto) as ctx:
            prov.complete_paciente(self.solicitud())
        self.assertTrue(ctx.exception.diario)


class TestAvisoDeEspera(unittest.TestCase):
    def test_solo_las_esperas_largas_y_no_mas_de_una_cada_dos_minutos(self):
        dichas, reloj = [], [1000.0]
        avisar = remoto.aviso_de_espera(dichas.append, "prueba", reloj=lambda: reloj[0])
        avisar(3, "límite por minuto", "groq")
        self.assertEqual(dichas, [], "una espera corta no se dice")
        avisar(30, "límite por minuto", "groq")
        reloj[0] += 60
        avisar(30, "límite por minuto", "groq")
        self.assertEqual(len(dichas), 1)
        self.assertIn("30 segundos", dichas[0])
        reloj[0] += remoto.AVISO_ESPERA_INTERVALO_SEGUNDOS
        avisar(15, "límite por minuto", "groq")
        self.assertEqual(len(dichas), 2)

    def test_sin_voz_solo_queda_el_registro(self):
        remoto.aviso_de_espera(None)(60, "límite por minuto", "groq")


class TestRolesYFabricaDeTrabajo(Casabase):
    """Cada rol lee su modelo del mismo proveedor; el coder no usa el de chat."""

    def config_en_disco(self, datos):
        import tempfile
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = os.path.join(carpeta.name, "online_coder.json")
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo)
        parche = patch.object(remoto, "_ruta_config", return_value=ruta)
        parche.start()
        self.addCleanup(parche.stop)

    def test_cada_rol_toma_su_clave_de_modelo(self):
        self.config_en_disco({"enabled": True, "providers": [{
            "name": "groq", "provider": "groq", "api_key": "k",
            "model": "openai/gpt-oss-120b", "chat_model": "llama-chat",
            "text_model": "qwen-texto", "vision_model": "llama-vision"}]})
        cfg = remoto._leer_config()
        self.assertEqual([p["model"] for p in cfg["providers"]], ["llama-chat"])
        self.assertEqual(cfg["por_rol"]["codigo"][0]["model"], "openai/gpt-oss-120b")
        self.assertEqual(cfg["por_rol"]["codigo"][0]["name"], "groq:codigo",
                         "cuota y enfriamiento aparte: Groq limita por modelo")
        self.assertEqual(cfg["por_rol"]["texto"][0]["model"], "qwen-texto")
        self.assertEqual(cfg["por_rol"]["vision"][0]["model"], "llama-vision")

    def test_sin_chat_model_el_coder_igual_tiene_motor(self):
        self.config_en_disco({"enabled": True, "providers": [{
            "name": "groq", "provider": "groq", "api_key": "k",
            "model": "openai/gpt-oss-120b"}]})
        self.assertFalse(RemotoChatProvider(session=Sesion()).disponible())
        self.assertTrue(RemotoChatProvider(session=Sesion(), rol="codigo").disponible())

    def test_fabrica_de_trabajo_respeta_la_cadena_del_centro(self):
        from proveedores.llm.fabrica import crear_proveedor_trabajo

        class Cadena:
            def __init__(self, valor):
                self.valor = valor

            def nube_de_trabajo(self):
                return self.valor

        elegido = object()
        self.assertIs(crear_proveedor_trabajo("codigo", por_funcion=Cadena(elegido)), elegido)
        self.assertIsNone(crear_proveedor_trabajo("codigo", por_funcion=Cadena(False)),
                          "«solo local» no sube nada a la nube")
        sin_cadena = crear_proveedor_trabajo("codigo", por_funcion=Cadena(None))
        self.assertIsInstance(sin_cadena, RemotoChatProvider)
        self.assertEqual(sin_cadena._rol, "codigo")


class TestVision(Casabase):
    """Visión gratis (Fase 4 y lo que venga después): un rol más de la misma cadena."""

    def config_en_disco(self, datos):
        import tempfile
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = os.path.join(carpeta.name, "online_coder.json")
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo)
        parche = patch.object(remoto, "_ruta_config", return_value=ruta)
        parche.start()
        self.addCleanup(parche.stop)

    def test_mensaje_con_imagen_lleva_texto_y_un_bloque_de_imagen(self):
        from proveedores.llm.contrato import mensaje_con_imagen
        mensaje = mensaje_con_imagen("¿qué ves?", b"\x89PNG...", mime="image/png")
        self.assertEqual(mensaje["role"], "user")
        self.assertEqual(mensaje["content"][0], {"type": "text", "text": "¿qué ves?"})
        bloque = mensaje["content"][1]
        self.assertEqual(bloque["type"], "image_url")
        self.assertTrue(bloque["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_sin_modelo_de_vision_configurado_no_revienta(self):
        from proveedores.llm.fabrica import preguntar_sobre_imagen
        self.config_en_disco({"enabled": True, "providers": [{
            "name": "groq", "provider": "groq", "api_key": "k", "model": "openai/gpt-oss-120b"}]})
        sesion = Sesion()
        ok, motivo = preguntar_sobre_imagen("¿qué ves?", b"datos", session=sesion)
        self.assertFalse(ok)
        self.assertIn("vision_model", motivo)
        self.assertEqual(sesion.peticiones, [], "sin proveedor, ni se intenta la llamada")

    def test_pregunta_sobre_imagen_manda_el_bloque_y_suelta_el_trabajo(self):
        from proveedores.llm.fabrica import preguntar_sobre_imagen
        self.config_en_disco({"enabled": True, "providers": [{
            "name": "google-gemini", "provider": "gemini", "api_key": "k",
            "vision_model": "gemini-3.5-flash-lite"}]})
        sesion = Sesion(Respuesta({"choices": [{"message": {"content": "Un botón azul"}}]}))
        ok, texto = preguntar_sobre_imagen("¿qué ves?", b"\x89PNG...", session=sesion)
        self.assertEqual((ok, texto), (True, "Un botón azul"))
        cuerpo = sesion.peticiones[0]["json"]
        self.assertEqual(cuerpo["model"], "gemini-3.5-flash-lite")
        bloques = cuerpo["messages"][0]["content"]
        self.assertEqual(bloques[0]["text"], "¿qué ves?")
        self.assertEqual(bloques[1]["type"], "image_url")

    def test_una_clave_rechazada_no_revienta_y_pasa_al_siguiente_proveedor(self):
        from proveedores.llm.fabrica import preguntar_sobre_imagen
        self.config_en_disco({"enabled": True, "providers": [
            {"name": "google-gemini", "provider": "gemini", "api_key": "mala",
             "vision_model": "gemini-3.5-flash-lite"},
            {"name": "groq-vision", "provider": "groq", "api_key": "k",
             "vision_model": "llama-4-scout"},
        ]})
        sesion = Sesion(
            Respuesta(estado=400, texto='{"error": {"message": "API key not valid"}}'),
            Respuesta({"choices": [{"message": {"content": "Un botón azul"}}]}),
        )
        ok, texto = preguntar_sobre_imagen("¿qué ves?", b"datos", session=sesion)
        self.assertEqual((ok, texto), (True, "Un botón azul"))
        self.assertEqual(sesion.peticiones[1]["json"]["model"], "llama-4-scout")


# =========================================================================
#  CONMUTADOR
# =========================================================================

class FlujoFalso:
    """Stream del remoto: emite lo que le den y puede romperse despues."""

    def __init__(self, eventos, estalla=None, status_code=200):
        self._eventos = list(eventos)
        self._estalla = estalla
        self.status_code = status_code
        self.cerrado = False

    def iter_events(self):
        for evento in self._eventos:
            yield evento
        if self._estalla is not None:
            raise self._estalla

    def close(self):
        self.cerrado = True


class PrimarioFalso:
    def __init__(self, disponible=True, *resultados):
        self._disponible = disponible
        self.llamadas = []
        self._resultados = list(resultados)

    def disponible(self):
        return self._disponible

    def nombre(self):
        return "groq-chat"

    def _llamar(self, nombre, request, timeout):
        self.llamadas.append({"via": nombre, "request": request,
                              "timeout": timeout})
        if not self._resultados:
            raise AssertionError("el primario no esperaba mas llamadas")
        siguiente = self._resultados.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente

    def stream(self, request, timeout=None):
        return self._llamar("stream", request, timeout)

    def complete(self, request, timeout=None):
        return self._llamar("complete", request, timeout)


class RespaldoFalso:
    def __init__(self, texto="Local"):
        self.llamadas = []
        self._texto = texto

    def _emitir(self):
        fragmentos = list(self._texto)
        return FlujoFalso([remoto.ChatEvent(content=c) for c in fragmentos]
                          + [remoto.ChatEvent(content="", finished=True)])

    def stream(self, request, timeout=None):
        self.llamadas.append({"via": "stream", "request": request,
                              "timeout": timeout})
        return self._emitir()

    def complete(self, request, timeout=None):
        self.llamadas.append({"via": "complete", "request": request,
                              "timeout": timeout})
        return "completo-local"

    def health(self, timeout=None):
        self.llamadas.append({"via": "health", "timeout": timeout})
        return True

    def loaded_models(self, timeout=None):
        return [LOCAL]


class TestConmutacion(Casabase):
    def setUp(self):
        super().setUp()
        self.avisos = []
        self.solicitud_base = self.solicitud()

    def probar(self, primario, respaldo, tope=8.0):
        return ProveedorConmutado(primario, respaldo, tope_primer_token=tope,
                                  log=self.avisos.append)

    def texto(self, respuesta):
        return "".join(e.content for e in respuesta.iter_events())

    def test_fallo_antes_del_primer_token_usa_el_mismo_prompt_y_su_ventana(self):
        respaldo = RespaldoFalso()
        primario = PrimarioFalso(True, requests.exceptions.ConnectionError("down"))
        respuesta = self.probar(primario, respaldo).stream(
            self.solicitud_base, timeout=(10, 35))
        self.assertEqual(self.texto(respuesta), "Local")
        self.assertEqual(len(respaldo.llamadas), 1)
        self.assertIs(respaldo.llamadas[0]["request"], self.solicitud_base,
                      "el local recibe el prompt exacto: ahi esta la cache KV")
        self.assertEqual(respaldo.llamadas[0]["timeout"], (10, 35),
                         "el local conserva su ventana de lectura")
        self.assertIn("[motor] local", self.avisos[0])

    def test_el_remoto_recibe_el_tope_de_primer_token(self):
        primario = PrimarioFalso(True, RuntimeError("no llega"))
        self.probar(primario, RespaldoFalso(), tope=6.0).stream(
            self.solicitud_base, timeout=(10, 35))
        self.assertEqual(primario.llamadas[0]["timeout"], (10, 6.0))

    def test_remoto_que_emite_se_queda_con_el_turno(self):
        respaldo = RespaldoFalso()
        eventos = [remoto.ChatEvent(content="Ho"), remoto.ChatEvent(content="la"),
                   remoto.ChatEvent(content="", finished=True)]
        primario = PrimarioFalso(True, FlujoFalso(eventos))
        respuesta = self.probar(primario, respaldo).stream(self.solicitud_base)
        self.assertEqual(self.texto(respuesta), "Hola")
        self.assertEqual(respaldo.llamadas, [], "el local no se toca")
        self.assertIn("groq-chat", self.avisos[0])

    def test_romperse_despues_del_primer_evento_no_reintenta(self):
        respaldo = RespaldoFalso()
        primario = PrimarioFalso(
            True, FlujoFalso([remoto.ChatEvent(content="ya")],
                             estalla=requests.exceptions.ReadTimeout("corte")))
        respuesta = self.probar(primario, respaldo).stream(self.solicitud_base)
        con_events = respuesta.iter_events()
        self.assertEqual(next(con_events).content, "ya")
        with self.assertRaises(requests.exceptions.ReadTimeout):
            next(con_events)
        self.assertEqual(respaldo.llamadas, [],
                         "a mitad de frase no hay segundo motor: es el turno del uno")

    def test_el_primer_evento_no_se_pierde_al_reanudar(self):
        primario = PrimarioFalso(
            True, FlujoFalso([remoto.ChatEvent(content="A"),
                              remoto.ChatEvent(content="B")]))
        respuesta = self.probar(primario, RespaldoFalso()).stream(
            self.solicitud_base)
        self.assertEqual(self.texto(respuesta), "AB")
        self.assertEqual(respuesta.status_code, 200)

    def test_stream_que_no_emite_nada_tambien_cae_al_local(self):
        primario = PrimarioFalso(True, FlujoFalso([]))
        respaldo = RespaldoFalso()
        respuesta = self.probar(primario, respaldo).stream(self.solicitud_base)
        self.assertEqual(self.texto(respuesta), "Local")
        self.assertEqual(len(respaldo.llamadas), 1)
        self.assertTrue(primario._resultados == [])

    def test_el_stream_remoto_abandonado_se_cierra(self):
        flujo = FlujoFalso([])
        primario = PrimarioFalso(True, flujo)
        self.probar(primario, RespaldoFalso()).stream(self.solicitud_base)
        self.assertTrue(flujo.cerrado, "el socket del intento fallido se libera")

    def test_enfriado_va_al_local_sin_llamar_al_remoto(self):
        respaldo = RespaldoFalso()
        primario = PrimarioFalso(False)
        self.probar(primario, respaldo).stream(self.solicitud_base)
        self.assertEqual(primario.llamadas, [])
        self.assertEqual(len(respaldo.llamadas), 1)
        self.assertEqual(self.avisos, [], "el enfriamiento no se anuncia")

    def test_complete_con_las_mismas_reglas(self):
        primario = PrimarioFalso(True, ErrorRemoto("429 por minuto"))
        respaldo = RespaldoFalso()
        resultado = self.probar(primario, respaldo).complete(
            self.solicitud_base, timeout=25)
        self.assertEqual(resultado, "completo-local")
        self.assertEqual(primario.llamadas[0]["timeout"], 8.0,
                         "un completo sin stream tambien acota su ventana")
        self.assertEqual(respaldo.llamadas[0]["timeout"], 25)

    def test_complete_del_remoto_pasa_sin_tocar_el_local(self):
        primario = PrimarioFalso(True, "completo-remoto")
        respaldo = RespaldoFalso()
        conmutado = self.probar(primario, respaldo)
        self.assertEqual(conmutado.complete(self.solicitud_base),
                         "completo-remoto")
        self.assertEqual(respaldo.llamadas, [])

    def test_salud_y_residencia_contestan_por_el_local(self):
        primario = PrimarioFalso(True)
        respaldo = RespaldoFalso()
        conmutado = self.probar(primario, respaldo)
        self.assertTrue(conmutado.health(timeout=1))
        self.assertEqual(conmutado.loaded_models(), [LOCAL])
        self.assertEqual(primario.llamadas, [],
                         "el broker pregunta por RAM de esta caja, no por la API")

    def test_es_un_chatprovider(self):
        self.assertIsInstance(self.probar(PrimarioFalso(False), RespaldoFalso()),
                              ChatProvider)

    def test_el_tope_lo_fija_la_variable_de_entorno(self):
        os.environ["DARK_API_TTFT_TOPE_SEGUNDOS"] = "3"
        forzado = ProveedorConmutado(PrimarioFalso(True), RespaldoFalso(),
                                     log=lambda *a: None)
        self.assertEqual(forzado.tope, 3.0)
        del os.environ["DARK_API_TTFT_TOPE_SEGUNDOS"]
        normal = ProveedorConmutado(PrimarioFalso(True), RespaldoFalso(),
                                    log=lambda *a: None)
        self.assertEqual(normal.tope, 8.0)


class TestAcotar(unittest.TestCase):
    def test_formas_de_timeout(self):
        self.assertEqual(_acotar(None, 8.0), 8.0)
        self.assertEqual(_acotar(25, 8.0), 8.0)
        self.assertEqual(_acotar(3, 8.0), 3.0)
        self.assertEqual(_acotar((10, 35), 8.0), (10, 8.0))
        self.assertEqual(_acotar((10, 5), 8.0), (10, 5.0))
        self.assertEqual(_acotar((10, None), 8.0), (10, 8.0))


class TestFabrica(Casabase):
    def test_conmutado_sin_config_devuelve_el_local(self):
        self.forzar_config(config_usable(enabled=False))
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "conmutado"}):
            self.assertIsInstance(crear_proveedor_chat(session=Sesion()),
                                  OllamaChatProvider)

    def test_conmutado_con_config_compone_los_dos_motores(self):
        self.forzar_config()
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "conmutado"}):
            conmutado = crear_proveedor_chat(session=Sesion())
        self.assertIsInstance(conmutado, ProveedorConmutado)
        self.assertIsInstance(conmutado.primario, RemotoChatProvider)
        self.assertIsInstance(conmutado.respaldo, OllamaChatProvider)

    def test_el_respaldo_puede_ser_llama_cpp(self):
        self.forzar_config()
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "conmutado",
                                     "DARK_LLM_LOCAL_PROVIDER": "llamacpp"}):
            conmutado = crear_proveedor_chat(session=Sesion())
        from proveedores.llm.llamacpp import LlamaCppProvider

        self.assertIsInstance(conmutado.respaldo, LlamaCppProvider)

    def test_default_sigue_siendo_ollama_y_un_valor_nuevo_sigue_muriendo(self):
        self.assertIsInstance(crear_proveedor_chat(session=Sesion()),
                              OllamaChatProvider)
        with patch.dict(os.environ, {"DARK_LLM_PROVIDER": "vllm"}):
            with self.assertRaises(ValueError):
                crear_proveedor_chat(session=Sesion())


if __name__ == "__main__":
    unittest.main()
