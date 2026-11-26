"""P4: biblioteca de modelos de pensamiento y cadena de modelos por función."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import AdaptadorPensamiento, Biblioteca, ErrorBiblioteca, Preferencias
from credenciales import AlmacenMemoria, ServicioClaves
from proveedores.llm import cadena
from proveedores.llm.cadena import CadenaProveedores, Candidato, ConModelo, ProveedorPorFuncion, ordenar
from proveedores.llm.contrato import ChatEvent, ChatRequest, ChatResult

SECRETO = "gsk_SECRETO-del-proveedor"


def pedido(modelo="base"):
    return ChatRequest(model=modelo, messages=[{"role": "user", "content": "hola"}])


class Respuesta:
    def __init__(self, codigo=200, cuerpo=None, texto=""):
        self.status_code, self._c, self.text = codigo, cuerpo, texto

    def json(self):
        return self._c

    def close(self):
        pass


class Sesion:
    """`requests.Session` de pega: guarda lo que se envió."""

    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta or Respuesta(200, {"model": "m", "choices": [{"message": {"content": "listo"}}]})
        self.error, self.llamadas = error, []

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.llamadas.append({"url": url, "headers": headers, "json": json})
        if self.error:
            raise self.error
        return self.respuesta


class Motor:
    """Proveedor de chat de pega con nombre, resultado o fallo."""

    def __init__(self, nombre, texto="ok", falla=None, vacio=False, disponible=True):
        self.nombre_, self.texto, self.falla, self.vacio, self.disp = nombre, texto, falla, vacio, disponible
        self.modelos, self.timeouts = [], []

    def disponible(self):
        return self.disp

    def complete(self, solicitud, timeout=None):
        self.modelos.append(solicitud.model)
        self.timeouts.append(timeout)
        if self.falla:
            raise self.falla
        return ChatResult(content=self.texto, model=self.nombre_)

    def stream(self, solicitud, timeout=None):
        self.modelos.append(solicitud.model)
        self.timeouts.append(timeout)
        if self.falla:
            raise self.falla
        eventos = [] if self.vacio else [ChatEvent(content=self.texto), ChatEvent(finished=True)]
        motor = self

        class Flujo:
            status_code = 200

            def iter_events(self):
                return iter(eventos)

            def close(self):
                motor.cerrado = True
        return Flujo()

    def health(self, timeout=None):
        return True

    def loaded_models(self, timeout=None):
        return []


def texto_de(flujo):
    return "".join(e.content for e in flujo.iter_events())


class TestOrden(unittest.TestCase):
    R = [{"id": "l1", "origen": "ollama"}, {"id": "n1", "origen": "nube"},
         {"id": "l2", "origen": "ollama"}, {"id": "n2", "origen": "nube"}]

    def ids(self, politica):
        return [r["id"] for r in ordenar(politica, self.R)]

    def test_las_cuatro_politicas(self):
        self.assertEqual(self.ids("solo_local"), ["l1", "l2"])
        self.assertEqual(self.ids("solo_nube"), ["n1", "n2"])
        self.assertEqual(self.ids("local_primero"), ["l1", "l2", "n1", "n2"])
        self.assertEqual(self.ids("nube_primero"), ["n1", "n2", "l1", "l2"])

    def test_una_politica_desconocida_es_la_mas_privada(self):
        self.assertEqual(self.ids("inventada"), self.ids("local_primero"))


class TestCadena(unittest.TestCase):
    def cadena(self, *motores, base=None, solo_nube=False):
        candidatos = [Candidato(m.nombre_, m.nombre_, m, es_nube=m.nombre_.startswith("n")) for m in motores]
        return CadenaProveedores(candidatos, base or Motor("base"), tope_nube=8.0, tope_local=5.0,
                                 solo_nube=solo_nube, log=lambda *_: None)

    def test_el_primero_que_responde_se_queda_el_turno(self):
        n1, l1 = Motor("n1", "de la nube"), Motor("l1", "local")
        self.assertEqual(self.cadena(n1, l1).complete(pedido()).content, "de la nube")
        self.assertEqual(l1.modelos, [])

    def test_si_el_primero_falla_sigue_con_el_siguiente(self):
        n1, l1 = Motor("n1", falla=RuntimeError("429")), Motor("l1", "local")
        self.assertEqual(self.cadena(n1, l1).complete(pedido()).content, "local")

    def test_stream_que_no_emite_cae_al_siguiente(self):
        n1, l1 = Motor("n1", vacio=True), Motor("l1", "local")
        self.assertEqual(texto_de(self.cadena(n1, l1).stream(pedido())), "local")
        self.assertTrue(getattr(n1, "cerrado", False))  # el flujo fallido se cierra

    def test_los_no_ultimos_tienen_tope_y_el_ultimo_no(self):
        n1, l1 = Motor("n1", falla=RuntimeError("x")), Motor("l1")
        self.cadena(n1, l1).complete(pedido(), timeout=(5, 45))
        self.assertEqual(n1.timeouts, [(5, 8.0)])
        self.assertEqual(l1.timeouts, [(5, 45)])

    def test_un_candidato_no_disponible_se_salta(self):
        n1, l1 = Motor("n1", disponible=False), Motor("l1", "local")
        self.cadena(n1, l1).complete(pedido())
        self.assertEqual(n1.modelos, [])

    def test_si_todo_falla_cae_al_proveedor_por_defecto(self):
        base = Motor("base", "por defecto")
        c = self.cadena(Motor("n1", falla=RuntimeError("x")), Motor("l1", falla=RuntimeError("y")), base=base)
        self.assertEqual(c.complete(pedido()).content, "por defecto")

    def test_solo_nube_nunca_cae_al_local(self):
        base = Motor("base", "no debe usarse")
        c = self.cadena(Motor("n1", falla=RuntimeError("x")), base=base, solo_nube=True)
        with self.assertRaises(RuntimeError):
            c.complete(pedido())
        self.assertEqual(base.modelos, [])
        with self.assertRaises(RuntimeError):
            self.cadena(base=base, solo_nube=True).complete(pedido())

    def test_con_modelo_fija_el_modelo_local(self):
        local = Motor("l")
        ConModelo(local, "qwen3:4b").complete(pedido("otro"))
        self.assertEqual(local.modelos, ["qwen3:4b"])


class ConPreferencias(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.prefs = Preferencias(Path(self.dir.name) / "preferences.json")
        self.claves = ServicioClaves(AlmacenMemoria())
        cadena.fijar_preferencias(self.prefs)
        self.addCleanup(cadena.fijar_preferencias, None)
        self.sesion = Sesion()
        self.ollama = (True, ["qwen3:4b"])

    def adaptador(self):
        return AdaptadorPensamiento(self.prefs, lambda: self.claves, lambda: self.ollama,
                                    sesion=lambda: self.sesion, local_base=lambda: Motor("local", "hola local"),
                                    ahora=lambda: "2026-11-24T00:00:00+00:00")

    def biblioteca(self):
        return Biblioteca(self.adaptador(), self.prefs)

    def agregar_nube(self, b, modelo="llama-3.3"):
        self.claves.guardar("groq", SECRETO)
        t = b.agregar("nube", {"cuenta": "groq", "modelo": modelo, "funciones": ["chat"]}, aceptado=True)
        return b.esperar(t.id)


class TestAdaptador(ConPreferencias):
    def test_nube_exige_clave_guardada(self):
        b = self.biblioteca()
        with self.assertRaises(ErrorBiblioteca) as ctx:
            b.revisar("nube", {"cuenta": "groq", "modelo": "m", "funciones": ["chat"]})
        self.assertIn("Clave de API", str(ctx.exception))

    def test_la_revision_dice_que_datos_salen_y_pide_consentimiento(self):
        self.claves.guardar("groq", SECRETO)
        r = self.biblioteca().revisar("nube", {"cuenta": "groq", "modelo": "m", "funciones": ["chat"]})
        self.assertTrue(r.consentimientos)
        self.assertIn("Groq", r.datos_que_salen[0])
        self.assertNotIn(SECRETO, json.dumps(r.como_dict()))

    def test_sin_consentimiento_no_se_agrega(self):
        self.claves.guardar("groq", SECRETO)
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().agregar("nube", {"cuenta": "groq", "modelo": "m", "funciones": ["chat"]}, aceptado=False)
        self.assertEqual(self.sesion.llamadas, [])  # ni siquiera se llamó al proveedor

    def test_agregar_nube_prueba_guarda_y_registra_el_aviso_una_vez(self):
        b = self.biblioteca()
        trabajo = self.agregar_nube(b)
        self.assertEqual(trabajo.estado, "ok")
        recurso = b.listar()[0]
        self.assertEqual((recurso["id"], recurso["origen"]), ("nube:groq:llama-3.3", "nube"))
        self.assertEqual(recurso["base_url"], "https://api.groq.com/openai/v1")
        self.assertEqual(self.prefs.obtener("ajustes.avisoNubeAceptado"), "2026-11-24T00:00:00+00:00")
        # la llamada de prueba fue al proveedor con la clave, y la clave no quedó en preferencias
        self.assertEqual(self.sesion.llamadas[0]["headers"]["Authorization"], f"Bearer {SECRETO}")
        self.assertNotIn(SECRETO, json.dumps(self.prefs.todo()))

    def test_si_el_proveedor_rechaza_la_clave_no_se_guarda_nada(self):
        self.sesion = Sesion(Respuesta(401, texto="bad key"))
        t = self.agregar_nube(self.biblioteca())
        self.assertEqual(t.estado, "error")
        self.assertIn("rechazó la clave", t.error)
        self.assertEqual(self.prefs.obtener("bibliotecas.modelosPensamiento"), [])
        self.assertIsNone(self.prefs.obtener("ajustes.avisoNubeAceptado"))

    def test_corregir_la_clave_tras_un_rechazo_funciona_de_inmediato(self):
        self.sesion = Sesion(Respuesta(401, texto="bad key"))
        b = self.biblioteca()
        self.assertEqual(self.agregar_nube(b).estado, "error")  # 401: el proveedor queda enfriado
        self.claves.guardar("groq", "gsk_clave-corregida")
        self.sesion = Sesion()  # ahora el proveedor acepta
        t = b.esperar(b.agregar("nube", {"cuenta": "groq", "modelo": "llama-3.3", "funciones": ["chat"]}, aceptado=True).id)
        self.assertEqual(t.estado, "ok")

    def test_probar_tras_un_rechazo_vuelve_a_intentarlo(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        self.sesion = Sesion(Respuesta(401, texto="x"))
        self.assertFalse(b.probar("nube:groq:llama-3.3").ok)
        self.sesion = Sesion()
        self.assertTrue(b.probar("nube:groq:llama-3.3").ok)

    def test_modelo_inexistente_se_explica(self):
        self.sesion = Sesion(Respuesta(404, texto="no model"))
        self.assertIn("no conoce ese modelo", self.agregar_nube(self.biblioteca()).error)

    def test_sin_conexion_se_explica(self):
        import requests
        self.sesion = Sesion(error=requests.exceptions.ConnectionError("x"))
        self.assertIn("sin conexión", self.agregar_nube(self.biblioteca()).error)

    def test_cuenta_ajena_a_los_conocidos_pide_direccion_https(self):
        self.claves.guardar("mi-proveedor", SECRETO)
        b = self.biblioteca()
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("nube", {"cuenta": "mi-proveedor", "modelo": "m", "funciones": ["chat"]})
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("nube", {"cuenta": "mi-proveedor", "modelo": "m", "funciones": ["chat"], "base_url": "http://x.com/v1"})
        b.revisar("nube", {"cuenta": "mi-proveedor", "modelo": "m", "funciones": ["chat"], "base_url": "https://x.com/v1"})

    def test_los_proveedores_ofrecidos_son_los_del_catalogo_de_pensamiento_con_marca_de_clave(self):
        a = self.adaptador()
        campo = [o for o in a.origenes() if o.id == 'nube'][0].campos[0]
        self.assertEqual(campo.opciones, ("anthropic", "openai", "deepseek", "gemini", "groq", "openrouter", "mistral", "otro"))
        self.assertNotIn("elevenlabs", campo.opciones)  # una voz no es un proveedor de pensamiento
        self.assertNotIn("clave guardada", dict(campo.etiquetas_opciones)["groq"])
        self.claves.guardar("groq", SECRETO)
        self.claves.guardar("mi-proveedor", SECRETO)
        campo = [o for o in a.origenes() if o.id == 'nube'][0].campos[0]
        self.assertIn("clave guardada", dict(campo.etiquetas_opciones)["groq"])
        self.assertIn("mi-proveedor", campo.opciones)

    def test_ollama_exige_el_modelo_instalado(self):
        b = self.biblioteca()
        with self.assertRaises(ErrorBiblioteca) as ctx:
            b.revisar("ollama", {"etiqueta": "otro:7b"})
        self.assertIn("no está instalado", str(ctx.exception))
        self.ollama = (False, [])
        with self.assertRaises(ErrorBiblioteca):
            b.revisar("ollama", {"etiqueta": "qwen3:4b"})

    def test_agregar_ollama(self):
        b = self.biblioteca()
        t = b.esperar(b.agregar("ollama", {"etiqueta": "qwen3:4b"}, aceptado=False).id)
        self.assertEqual(t.estado, "ok")
        self.assertEqual(b.listar()[0]["etiqueta"], "qwen3:4b")

    def test_probar_ollama_usa_la_etiqueta(self):
        b = self.biblioteca()
        b.esperar(b.agregar("ollama", {"etiqueta": "qwen3:4b"}, aceptado=False).id)
        r = b.probar("ollama:qwen3:4b")
        self.assertTrue(r.ok)
        self.assertIn("hola local", r.mensaje)

    def test_eliminar_no_toca_la_clave(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        with self.assertRaises(ErrorBiblioteca):
            b.eliminar("nube:groq:llama-3.3")  # está en uso (lo asignó el propio «Agregar»)
        b.eliminar("nube:groq:llama-3.3", forzar=True)
        self.assertTrue(self.claves.existe("groq"))
        self.assertEqual(b.listar(), [])

    def test_duplicado_no_se_sobrescribe(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        with self.assertRaises(ErrorBiblioteca):
            b.agregar("nube", {"cuenta": "groq", "modelo": "llama-3.3", "funciones": ["chat"]}, aceptado=True)


class TestEnrutador(ConPreferencias):
    def router(self, base=None, sesion=None):
        return ProveedorPorFuncion("chat", base or Motor("base", "por defecto"), sesion=sesion or self.sesion,
                                   clave_de=lambda c: self.claves.leer(c), log=lambda *_: None)

    def asignar(self, b, cadena_ids, politica):
        b.asignar("chat", cadena_ids, politica)

    def test_nube_de_trabajo_sigue_la_cadena_y_respeta_solo_local(self):
        r = self.router()
        self.assertIsNone(r.nube_de_trabajo(), "sin cadena no opina")
        b = self.biblioteca()
        self.agregar_nube(b)
        self.asignar(b, ["nube:groq:llama-3.3"], "local_primero")
        elegido = r.nube_de_trabajo()
        self.assertEqual(elegido._fijo["model"], "llama-3.3")
        self.asignar(b, ["nube:groq:llama-3.3"], "solo_local")
        self.assertIs(r.nube_de_trabajo(), False)

    def test_sin_preferencias_vivas_o_sin_asignacion_todo_sigue_igual(self):
        r = self.router()
        self.assertEqual(r.complete(pedido()).content, "por defecto")
        cadena.fijar_preferencias(None)
        self.assertEqual(r.complete(pedido()).content, "por defecto")

    def test_con_asignacion_responde_la_nube_y_se_ve_en_la_llamada(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        self.asignar(b, ["nube:groq:llama-3.3"], "nube_primero")
        self.sesion.llamadas.clear()
        r = self.router().complete(pedido())
        self.assertEqual(r.content, "listo")
        self.assertEqual(self.sesion.llamadas[0]["json"]["model"], "llama-3.3")

    def test_un_cambio_en_el_centro_vale_en_la_siguiente_llamada(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        r = self.router()
        self.assertEqual(r.complete(pedido()).content, "listo")  # «Agregar» ya lo asignó a Conversar
        b.asignar("chat", [], "solo_nube")
        self.assertEqual(r.complete(pedido()).content, "por defecto")
        self.asignar(b, ["nube:groq:llama-3.3"], "solo_nube")
        self.assertEqual(r.complete(pedido()).content, "listo")
        b.asignar("chat", [], "solo_nube")  # sin cadena: vuelve al valor de siempre
        self.assertEqual(r.complete(pedido()).content, "por defecto")

    def test_sin_clave_la_nube_se_omite_y_en_solo_nube_falla_claro(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        self.asignar(b, ["nube:groq:llama-3.3"], "nube_primero")
        self.claves.borrar("groq")
        self.assertEqual(self.router().complete(pedido()).content, "por defecto")
        self.asignar(b, ["nube:groq:llama-3.3"], "solo_nube")
        with self.assertRaises(RuntimeError):
            self.router().complete(pedido())

    def test_borrar_la_clave_se_nota_sin_reiniciar(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        self.asignar(b, ["nube:groq:llama-3.3"], "nube_primero")
        r = self.router()
        self.assertEqual(r.complete(pedido()).content, "listo")
        self.claves.borrar("groq")
        self.assertEqual(r.complete(pedido()).content, "por defecto")

    def test_local_primero_usa_el_modelo_elegido_y_nube_de_respaldo(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        b.esperar(b.agregar("ollama", {"etiqueta": "qwen3:4b"}, aceptado=False).id)
        self.asignar(b, ["nube:groq:llama-3.3", "ollama:qwen3:4b"], "local_primero")
        local = Motor("l", "del local")
        r = self.router(base=local).complete(pedido("modelo-por-defecto"))
        self.assertEqual(r.content, "del local")
        self.assertEqual(local.modelos, ["qwen3:4b"])

    def test_el_respaldo_expuesto_es_el_motor_local(self):
        local = Motor("l")
        conmutado = type("C", (), {"respaldo": local})()
        self.assertIs(self.router(base=conmutado).respaldo, local)
        self.assertIs(self.router(base=local).respaldo, local)

    def test_una_configuracion_rota_no_deja_sin_motor(self):
        class Rotas:
            def obtener(self, *_a, **_k):
                raise ValueError("roto")
        cadena.fijar_preferencias(Rotas())
        self.assertEqual(self.router().complete(pedido()).content, "por defecto")

    def test_las_funciones_son_independientes(self):
        b = self.biblioteca()
        self.agregar_nube(b)
        self.asignar(b, ["nube:groq:llama-3.3"], "solo_nube")
        otra = ProveedorPorFuncion("codigo", Motor("base", "codigo por defecto"), sesion=self.sesion,
                                   clave_de=lambda c: self.claves.leer(c), log=lambda *_: None)
        self.assertEqual(otra.complete(pedido()).content, "codigo por defecto")


class TestRemotoFijo(unittest.TestCase):
    def test_el_proveedor_fijo_no_lee_el_archivo_y_usa_su_modelo(self):
        from proveedores.llm.remoto import RemotoChatProvider
        s = Sesion()
        p = RemotoChatProvider(session=s, log=lambda *_: None, fijo={
            "name": "groq/m", "base_url": "https://api.groq.com/openai/v1", "api_key": "k", "model": "m-fijo"})
        self.assertTrue(p.disponible())
        p.complete(pedido("ignorado"))
        self.assertEqual(s.llamadas[0]["json"]["model"], "m-fijo")
        self.assertTrue(s.llamadas[0]["url"].endswith("/chat/completions"))

    def test_sin_clave_no_esta_disponible(self):
        from proveedores.llm.remoto import RemotoChatProvider
        p = RemotoChatProvider(fijo={"name": "x", "base_url": "https://x", "api_key": "", "model": "m"})
        self.assertFalse(p.disponible())


if __name__ == "__main__":
    unittest.main()
