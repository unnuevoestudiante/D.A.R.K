"""Flujo de proveedores: clave en el mismo paso, para qué sirve cada modelo, abrir la página de claves,
Anthropic nativo y la separación de pensamiento y voz."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import (AdaptadorPensamiento, AdaptadorVoces, Biblioteca, DirectorCentro, EstadoPrimerArranque,
                    ErrorBiblioteca, Preferencias, SeccionClaves)
from centro import flujo
from credenciales import AlmacenMemoria, ServicioClaves, catalogo
from proveedores.llm import remoto
from proveedores.llm.cadena import crear_candidato
from proveedores.llm.contrato import ChatRequest
from voz.proveedores_voz import AudioPcm, VocesDeWindows

SECRETO = "sk-ant-SECRETO-que-no-debe-salir"


class Resp:
    def __init__(self, codigo=200, cuerpo=None, texto="", lineas=None):
        self.status_code, self._c, self.text, self._l = codigo, cuerpo, texto, lineas or []
        self.content = b"audio"

    def json(self):
        return self._c

    def iter_lines(self):
        yield from self._l

    def close(self):
        pass


class Sesion:
    """Responde con la forma propia de cada API: la de mensajes de Anthropic o la «chat completions» de las demás."""

    def __init__(self, respuesta=None):
        self.respuesta = respuesta
        self.llamadas = []

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.llamadas.append({"url": url, "headers": dict(headers or {}), "json": json})
        if self.respuesta is not None:
            return self.respuesta
        if url.endswith("/messages"):
            return Resp(200, {"model": "m", "content": [{"type": "text", "text": "listo"}]})
        return Resp(200, {"model": "m", "choices": [{"message": {"content": "listo"}}]})

    def get(self, url, headers=None, timeout=None):
        return self.respuesta


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.prefs = Preferencias(self.dir / "p.json")
        self.claves = ServicioClaves(AlmacenMemoria())
        self.sesion = Sesion()

    def pensamiento(self):
        return Biblioteca(AdaptadorPensamiento(
            self.prefs, lambda: self.claves, lambda: (True, []), sesion=lambda: self.sesion,
            catalogo=lambda: [], ram=lambda: 16 * 1024 ** 3, libre=lambda: 10 ** 12), self.prefs)

    def agregar(self, b, datos, aceptado=True):
        return b.esperar(b.agregar("nube", datos, aceptado=aceptado).id)

    def asignacion(self, destino, funcion):
        return self.prefs.obtener(f"asignaciones.{destino}.{funcion}")


class TestClaveEnElMismoPaso(Base):
    def datos(self, **extra):
        return {"cuenta": "anthropic", "modelo": "claude-sonnet-5-5", "funciones": ["chat"], "clave": SECRETO, **extra}

    def test_la_clave_se_pega_con_el_modelo_y_se_guarda_si_la_prueba_sale_bien(self):
        b = self.pensamiento()
        t = self.agregar(b, self.datos())
        self.assertEqual(t.estado, "ok")
        self.assertEqual(self.claves.leer("anthropic"), SECRETO)
        self.assertEqual(self.sesion.llamadas[0]["headers"]["x-api-key"], SECRETO)

    def test_si_la_prueba_falla_la_clave_nueva_no_se_guarda_ni_queda_nada(self):
        self.sesion = Sesion(Resp(401, texto="bad"))
        b = self.pensamiento()
        t = self.agregar(b, self.datos())
        self.assertEqual(t.estado, "error")
        self.assertIn("No se guardó nada", t.error)
        self.assertFalse(self.claves.existe("anthropic"))
        self.assertEqual(b.listar(), [])
        self.assertIsNone(self.asignacion("pensamiento", "chat"))

    def test_si_ya_habia_una_clave_y_la_nueva_falla_se_restaura_la_anterior(self):
        self.claves.guardar("anthropic", "clave-anterior-buena")
        self.sesion = Sesion(Resp(401, texto="bad"))
        self.agregar(self.pensamiento(), self.datos())
        self.assertEqual(self.claves.leer("anthropic"), "clave-anterior-buena")

    def test_la_clave_nunca_aparece_en_preferencias_revision_ni_trabajo(self):
        b = self.pensamiento()
        revision = b.revisar("nube", self.datos())
        self.assertNotIn(SECRETO, json.dumps(revision.como_dict()))
        t = self.agregar(b, self.datos())
        self.assertNotIn(SECRETO, json.dumps(t.como_dict()))
        self.assertNotIn(SECRETO, json.dumps(self.prefs.todo()))
        self.assertNotIn(SECRETO, json.dumps(b.listar()))

    def test_sin_clave_ni_guardada_ni_pegada_dice_que_hacer(self):
        with self.assertRaises(ErrorBiblioteca) as ctx:
            self.pensamiento().revisar("nube", self.datos(clave=""))
        self.assertIn("Clave de API", str(ctx.exception))
        self.assertIn("Anthropic", str(ctx.exception))

    def test_una_clave_guardada_antes_no_hace_falta_pegarla_de_nuevo(self):
        self.claves.guardar("anthropic", SECRETO)
        b = self.pensamiento()
        t = self.agregar(b, self.datos(clave=""))
        self.assertEqual(t.estado, "ok")

    def test_una_clave_con_espacios_se_rechaza_antes_de_tocar_nada(self):
        with self.assertRaises(ErrorBiblioteca):
            self.pensamiento().revisar("nube", self.datos(clave="sk ant con espacios"))
        self.assertEqual(self.sesion.llamadas, [])

    def test_otro_proveedor_exige_nombre_y_direccion_https(self):
        b = self.pensamiento()
        base = {"cuenta": "otro", "modelo": "m", "funciones": ["chat"], "clave": SECRETO}
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("nube", base)  # sin nombre
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("nube", {**base, "nombre_cuenta": "mi-prov"})  # sin dirección
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("nube", {**base, "nombre_cuenta": "mi-prov", "base_url": "http://x.com/v1"})
        b.revisar("nube", {**base, "nombre_cuenta": "mi-prov", "base_url": "https://x.com/v1"})

    def test_los_proveedores_del_catalogo_traen_su_direccion_y_formato(self):
        b = self.pensamiento()
        for proveedor, esperado in (("deepseek", "https://api.deepseek.com/chat/completions"),
                                    ("openai", "https://api.openai.com/v1/chat/completions"),
                                    ("anthropic", "https://api.anthropic.com/v1/messages")):
            self.sesion = Sesion()
            b = self.pensamiento()
            self.agregar(b, {"cuenta": proveedor, "modelo": "m1", "funciones": ["chat"], "clave": "clave-valida-123"})
            self.assertEqual(self.sesion.llamadas[0]["url"], esperado)


class TestParaQueSirve(Base):
    def test_la_nube_exige_marcar_para_que_se_quiere(self):
        for malo in (None, [], ["inventada"], "chat"):
            with self.assertRaises(ErrorBiblioteca, msg=repr(malo)):
                self.pensamiento().revisar("nube", {"cuenta": "groq", "modelo": "m", "clave": "clave-valida-123",
                                                    "funciones": malo})

    def test_se_asigna_a_las_funciones_marcadas_y_lo_dice(self):
        b = self.pensamiento()
        t = self.agregar(b, {"cuenta": "groq", "modelo": "m", "clave": "clave-valida-123",
                             "funciones": ["chat", "codigo"]})
        self.assertEqual(t.mensaje, "Listo. Quedó asignado a: Conversar, Programar.")
        self.assertEqual(self.asignacion("pensamiento", "chat"), {"politica": "nube_primero", "cadena": ["nube:groq:m"]})
        self.assertEqual(self.asignacion("pensamiento", "codigo")["cadena"], ["nube:groq:m"])
        self.assertIsNone(self.asignacion("pensamiento", "nucleo"))  # las no marcadas no se tocan

    def test_un_segundo_modelo_va_al_final_de_la_cadena_sin_duplicarse(self):
        b = self.pensamiento()
        self.agregar(b, {"cuenta": "groq", "modelo": "a", "clave": "clave-valida-123", "funciones": ["chat"]})
        self.agregar(b, {"cuenta": "groq", "modelo": "b", "funciones": ["chat", "nucleo"]})
        self.assertEqual(self.asignacion("pensamiento", "chat")["cadena"], ["nube:groq:a", "nube:groq:b"])
        self.assertEqual(self.asignacion("pensamiento", "nucleo")["cadena"], ["nube:groq:b"])

    def test_un_modelo_de_nube_en_una_funcion_solo_local_la_vuelve_hibrida_para_que_sirva(self):
        self.prefs.reemplazar_biblioteca("modelosPensamiento", [{"id": "ollama:x", "origen": "ollama", "etiqueta": "x"}])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_local", "cadena": ["ollama:x"]})
        t = self.agregar(self.pensamiento(), {"cuenta": "groq", "modelo": "m", "clave": "clave-valida-123",
                                              "funciones": ["chat"]})
        self.assertEqual(t.estado, "ok")
        self.assertEqual(self.asignacion("pensamiento", "chat"),
                         {"politica": "local_primero", "cadena": ["ollama:x", "nube:groq:m"]})

    def test_un_local_en_una_funcion_solo_nube_la_vuelve_hibrida(self):
        self.prefs.reemplazar_biblioteca("modelosPensamiento", [{"id": "nube:g:m", "origen": "nube"}])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_nube", "cadena": ["nube:g:m"]})
        flujo.asignar(self.prefs, "pensamiento", "chat", "ollama:x", es_nube=False)
        self.assertEqual(self.asignacion("pensamiento", "chat")["politica"], "nube_primero")

    def test_un_modelo_local_del_catalogo_sin_marcar_nada_se_asigna_segun_su_rol(self):
        from centro.ollama_local import ModeloCatalogo
        catalogo_falso = [ModeloCatalogo("cod:7b", "coder", "standard", "sha256:" + "a" * 64, 100, "Apache-2.0", "x")]

        class Cliente:
            def __init__(self):
                self.estado = {}

            def instalados(self):
                return dict(self.estado)

            def descargar(self, etiqueta, progreso, cancelado, limite_bytes=None):
                self.estado[etiqueta] = {"digest": "a" * 64, "size": 1}
        b = Biblioteca(AdaptadorPensamiento(self.prefs, lambda: self.claves, lambda: (True, []), cliente=Cliente(),
                                            catalogo=lambda: catalogo_falso, ram=lambda: 16 * 1024 ** 3,
                                            libre=lambda: 10 ** 12), self.prefs)
        t = b.esperar(b.agregar("catalogo", {"modelo": "cod:7b"}, aceptado=True).id)
        self.assertEqual(t.estado, "ok")
        self.assertEqual(t.mensaje, "Listo. Quedó asignado a: Programar.")
        self.assertEqual(self.asignacion("pensamiento", "codigo"), {"politica": "local_primero", "cadena": ["ollama:cod:7b"]})

    def test_un_local_sin_marcar_ni_rol_conocido_queda_en_la_biblioteca_y_lo_dice(self):
        class Cliente:
            def instalados(self):
                return {"raro:1b": {"digest": "x", "size": 1}}
        b = Biblioteca(AdaptadorPensamiento(self.prefs, lambda: self.claves, lambda: (True, ["raro:1b"]),
                                            cliente=Cliente(), catalogo=lambda: []), self.prefs)
        t = b.esperar(b.agregar("ollama", {"etiqueta": "raro:1b"}, aceptado=False).id)
        self.assertIn("elíjale abajo", t.mensaje)
        self.assertIsNone(self.asignacion("pensamiento", "chat"))


class TestVocesDeProveedor(Base):
    def voces(self):
        adaptador = AdaptadorVoces(lambda: self.claves, lambda: self.sesion, windows=VocesDeWindows(lambda *a, **k: "", "linux"),
                                   preferencias=self.prefs)
        return Biblioteca(adaptador, self.prefs)

    def datos(self, **extra):
        return {"proveedor": "elevenlabs", "voz_id": "21m00Tcm4TlvDq8ikWAM", "clave": "xi-clave-valida", **extra}

    def test_la_clave_va_en_el_mismo_paso_y_solo_se_guarda_si_la_voz_suena(self):
        b = self.voces()
        t = b.esperar(b.agregar("nube", self.datos(), aceptado=True).id)
        self.assertEqual(t.estado, "ok")
        self.assertEqual(self.claves.leer("elevenlabs"), "xi-clave-valida")

    def test_si_el_proveedor_rechaza_no_queda_clave_ni_voz(self):
        self.sesion = Sesion(Resp(401))
        b = self.voces()
        t = b.esperar(b.agregar("nube", self.datos(), aceptado=True).id)
        self.assertEqual(t.estado, "error")
        self.assertFalse(self.claves.existe("elevenlabs"))
        self.assertEqual(b.listar(), [])

    def test_la_primera_voz_agregada_pasa_a_ser_la_voz_de_dark_y_la_segunda_no_la_pisa(self):
        b = self.voces()
        t = b.esperar(b.agregar("nube", self.datos(), aceptado=True).id)
        self.assertIn("Desde ahora hablo con esa voz", t.mensaje)
        self.assertEqual(self.asignacion("vozSalida", "principal")["cadena"], ["voz:nube:elevenlabs:21m00Tcm4TlvDq8ikWAM"])
        t2 = b.esperar(b.agregar("nube", self.datos(voz_id="otraVozValida12", clave=""), aceptado=True).id)
        self.assertIn("la deja como mi voz cuando guste", t2.mensaje)
        self.assertEqual(len(self.asignacion("vozSalida", "principal")["cadena"]), 1)

    def test_los_proveedores_de_voz_no_se_mezclan_con_los_de_pensamiento(self):
        origen = self.voces().descripcion()["origenes"][0]
        self.assertEqual(origen["campos"][0]["opciones"], ["elevenlabs", "fishaudio"])
        self.assertEqual([p.id for p in catalogo.de_tipo("voz")], ["elevenlabs", "fishaudio"])
        self.assertNotIn("anthropic", [p.id for p in catalogo.de_tipo("voz")])


class TestAbrirPaginaDeClaves(Base):
    def test_abre_solo_direcciones_del_catalogo(self):
        abiertas = []
        mensaje = flujo.abrir_pagina_de_claves("anthropic", lambda url: abiertas.append(url) or True)
        self.assertEqual(abiertas, ["https://console.anthropic.com/settings/keys"])
        self.assertIn("Anthropic", mensaje)
        self.assertNotIn("sk-", mensaje)

    def test_un_identificador_desconocido_o_malicioso_no_abre_nada(self):
        abiertas = []
        for malo in ("", None, "otro", "http://evil.com", "../x", "javascript:alert(1)", "mi-proveedor"):
            with self.assertRaises(ErrorBiblioteca, msg=repr(malo)):
                flujo.abrir_pagina_de_claves(malo, lambda url: abiertas.append(url) or True)
        self.assertEqual(abiertas, [])

    def test_si_el_navegador_no_abre_lo_dice_y_da_la_direccion(self):
        with self.assertRaises(ErrorBiblioteca) as ctx:
            flujo.abrir_pagina_de_claves("openai", lambda url: False)
        self.assertIn("https://platform.openai.com/api-keys", str(ctx.exception))

    def test_todas_las_paginas_del_catalogo_son_https(self):
        self.assertTrue(all(p.url_claves.startswith("https://") and p.base_url.startswith("https://") for p in catalogo.TODOS))

    def test_la_operacion_del_director_abre_la_pagina_y_avisa(self):
        abiertas = []
        d = DirectorCentro(self.prefs, EstadoPrimerArranque(self.dir / "f.json"), capacidades=lambda: None,
                           aceptacion=lambda: None, abrir_url=lambda u: abiertas.append(u) or True)
        r = d.operar("proveedor_abrir", {"proveedor": "deepseek"})
        self.assertTrue(r["ok"])
        self.assertEqual(abiertas, ["https://platform.deepseek.com/api_keys"])
        self.assertFalse(d.operar("proveedor_abrir", {"proveedor": "http://evil.com"})["ok"])
        self.assertEqual(len(abiertas), 1)

    def test_los_campos_de_proveedor_traen_el_boton_que_abre_la_pagina(self):
        for biblioteca, campo in ((self.pensamiento(), "cuenta"),):
            nube = next(o for o in biblioteca.descripcion()["origenes"] if o["id"] == "nube")
            c = next(c for c in nube["campos"] if c["id"] == campo)
            self.assertEqual(c["accion"]["op"], "proveedor_abrir")
            self.assertEqual(c["accion"]["depende"], campo)


class TestSeccionClaves(Base):
    def test_las_claves_se_agrupan_en_pensamiento_y_voz_y_cada_proveedor_tiene_su_enlace(self):
        s = SeccionClaves(lambda: self.claves, lambda: self.dir / "x.json")
        self.claves.guardar("mi-proveedor", "clave-valida-123")
        datos = s.datos()
        grupos = {p["id"]: p["grupo"] for p in datos["proveedores"]}
        self.assertEqual(grupos["anthropic"], "pensamiento")
        self.assertEqual(grupos["elevenlabs"], "voz")
        self.assertEqual(grupos["mi-proveedor"], "otro")
        self.assertTrue(next(p for p in datos["proveedores"] if p["id"] == "groq")["tieneEnlace"])
        self.assertFalse(next(p for p in datos["proveedores"] if p["id"] == "mi-proveedor")["tieneEnlace"])
        self.assertEqual([g["id"] for g in datos["grupos"]], ["pensamiento", "voz", "otro"])
        self.assertNotIn("clave-valida-123", json.dumps(datos))


# ---------------------------------------------------------------- Anthropic nativo
def linea(**kw):
    return ("data: " + json.dumps(kw)).encode()


class TestAnthropicNativo(unittest.TestCase):
    FIJO = {"name": "anthropic/m#abc", "base_url": "https://api.anthropic.com/v1", "api_key": SECRETO,
            "model": "claude-sonnet-5-5", "formato": "anthropic"}

    def provider(self, sesion):
        return remoto.RemotoChatProvider(session=sesion, log=lambda *_: None, fijo=dict(self.FIJO))

    def pedido(self, **kw):
        base = {"model": "x", "messages": [{"role": "system", "content": "Eres D.A.R.K."},
                                           {"role": "user", "content": "hola"},
                                           {"role": "assistant", "content": "buenas"},
                                           {"role": "user", "content": "¿y tú?"}]}
        base.update(kw)
        return ChatRequest(**base)

    def test_cabeceras_y_cuerpo_de_la_api_de_mensajes(self):
        s = Sesion(Resp(200, {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "Buenos días."}],
                              "usage": {"input_tokens": 12, "output_tokens": 3}, "stop_reason": "end_turn"}))
        r = self.provider(s).complete(self.pedido(options={"max_output_tokens": 50, "temperature": 0.2}))
        llamada = s.llamadas[0]
        self.assertEqual(llamada["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(llamada["headers"]["x-api-key"], SECRETO)
        self.assertEqual(llamada["headers"]["anthropic-version"], "2023-06-01")
        self.assertNotIn("Authorization", llamada["headers"])
        cuerpo = llamada["json"]
        self.assertEqual(cuerpo["system"], "Eres D.A.R.K.")  # el sistema va aparte
        self.assertEqual([m["role"] for m in cuerpo["messages"]], ["user", "assistant", "user"])
        self.assertEqual((cuerpo["max_tokens"], cuerpo["temperature"], cuerpo["model"]), (50, 0.2, "claude-sonnet-5-5"))
        self.assertEqual(r.content, "Buenos días.")
        self.assertEqual(r.metrics, {"prompt_tokens": 12, "completion_tokens": 3, "finish_reason": "end_turn"})

    def test_max_tokens_es_obligatorio_y_tiene_valor_por_defecto(self):
        s = Sesion(Resp(200, {"content": [{"type": "text", "text": "x"}]}))
        self.provider(s).complete(self.pedido())
        self.assertEqual(s.llamadas[0]["json"]["max_tokens"], remoto.ANTHROPIC_MAX_TOKENS_POR_DEFECTO)

    def test_pedir_json_se_traduce_a_una_instruccion_porque_no_hay_modo_json(self):
        s = Sesion(Resp(200, {"content": [{"type": "text", "text": "{}"}]}))
        self.provider(s).complete(self.pedido(response_format="json"))
        cuerpo = s.llamadas[0]["json"]
        self.assertNotIn("response_format", cuerpo)
        self.assertIn("JSON", cuerpo["system"])

    def test_sin_mensajes_de_sistema_no_manda_el_campo(self):
        s = Sesion(Resp(200, {"content": [{"type": "text", "text": "x"}]}))
        self.provider(s).complete(self.pedido(messages=[{"role": "user", "content": "hola"}]))
        self.assertNotIn("system", s.llamadas[0]["json"])

    def test_el_stream_entrega_el_texto_de_los_deltas_y_cierra_con_metricas(self):
        lineas = [b"event: message_start",
                  linea(type="message_start", message={"usage": {"input_tokens": 9}}),
                  linea(type="content_block_start", index=0),
                  linea(type="content_block_delta", delta={"type": "text_delta", "text": "Buenos "}),
                  linea(type="content_block_delta", delta={"type": "text_delta", "text": "días."}),
                  linea(type="content_block_delta", delta={"type": "input_json_delta", "partial_json": "{"}),
                  linea(type="message_delta", delta={"stop_reason": "end_turn"}, usage={"output_tokens": 4}),
                  linea(type="message_stop")]
        s = Sesion(Resp(200, lineas=lineas))
        eventos = list(self.provider(s).stream(self.pedido()).iter_events())
        self.assertEqual("".join(e.content for e in eventos), "Buenos días.")
        self.assertTrue(eventos[-1].finished)
        self.assertEqual(eventos[-1].metrics, {"prompt_tokens": 9, "completion_tokens": 4, "finish_reason": "end_turn"})
        self.assertTrue(s.llamadas[0]["json"]["stream"])

    def test_un_error_a_mitad_del_stream_no_se_traga(self):
        s = Sesion(Resp(200, lineas=[linea(type="content_block_delta", delta={"type": "text_delta", "text": "a"}),
                                     linea(type="error", error={"type": "overloaded_error"})]))
        with self.assertRaises(RuntimeError):
            list(self.provider(s).stream(self.pedido()).iter_events())

    def test_respuesta_vacia_es_un_fallo_no_un_silencio(self):
        s = Sesion(Resp(200, {"content": []}))
        with self.assertRaises(remoto.ErrorRemoto):
            self.provider(s).complete(self.pedido())

    def test_un_401_se_clasifica_como_clave_rechazada(self):
        with self.assertRaises(remoto.ErrorRemoto) as ctx:
            self.provider(Sesion(Resp(401, texto="invalid x-api-key"))).complete(self.pedido())
        self.assertIn("401", ctx.exception.motivo)

    def test_un_recurso_del_catalogo_usa_el_formato_de_su_proveedor(self):
        c = crear_candidato({"id": "n", "origen": "nube", "cuenta": "anthropic", "modelo": "claude-sonnet-5-5",
                             "base_url": "https://api.anthropic.com/v1"}, sesion=Sesion(), local_base=None,
                            clave_de=lambda cuenta: SECRETO, log=lambda *_: None)
        self.assertEqual(c.proveedor._fijo["formato"], "anthropic")
        c2 = crear_candidato({"id": "n", "origen": "nube", "cuenta": "groq", "modelo": "m", "base_url": "https://x"},
                             sesion=Sesion(), local_base=None, clave_de=lambda cuenta: "k-valida", log=lambda *_: None)
        self.assertEqual(c2.proveedor._fijo["formato"], "openai")

    def test_el_formato_openai_sigue_igual(self):
        s = Sesion()
        p = remoto.RemotoChatProvider(session=s, log=lambda *_: None, fijo={
            "name": "g/m", "base_url": "https://api.groq.com/openai/v1", "api_key": "k", "model": "m"})
        p.complete(self.pedido())
        self.assertTrue(s.llamadas[0]["url"].endswith("/chat/completions"))
        self.assertEqual(s.llamadas[0]["headers"]["Authorization"], "Bearer k")


if __name__ == "__main__":
    unittest.main()
