"""P5: Ollama local (estado, catálogo por perfil, descarga) y orígenes catálogo/etiqueta."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import AdaptadorPensamiento, Biblioteca, ErrorBiblioteca, Preferencias
from centro import ollama_local as ol
from centro.ollama_local import ClienteOllama, ErrorOllama, ModeloCatalogo
from credenciales import AlmacenMemoria, ServicioClaves

GIB = ol.GIB
HUELLA_A = "a" * 64
HUELLA_B = "b" * 64


def modelo(etiqueta="qwen3:4b", perfil="standard", rol="chat", huella="sha256:" + HUELLA_A, mb=4300):
    return ModeloCatalogo(etiqueta, rol, perfil, huella, mb, "Apache-2.0", "https://ollama.com/library/" + etiqueta)


class RespuestaPull:
    def __init__(self, lineas, codigo=200):
        self.status_code, self._l, self.cerrada = codigo, lineas, False

    def iter_lines(self):
        yield from self._l

    def close(self):
        self.cerrada = True


class SesionOllama:
    def __init__(self, tags=None, pull=None, falla=False):
        self.tags, self.pull, self.falla, self.posts = tags or [], pull, falla, []

    def get(self, url, timeout=None):
        if self.falla:
            raise ConnectionError("no")

        class R:
            status_code = 200

            def json(_s):
                return {"models": self.tags}
        return R()

    def post(self, url, json=None, stream=False, timeout=None):
        self.posts.append((url, json))
        if self.falla:
            raise ConnectionError("no")
        return self.pull


def linea(**kw):
    return json.dumps(kw).encode()


class TestUtilidades(unittest.TestCase):
    def test_solo_un_ollama_local(self):
        for ok in ("http://localhost:11434", "http://127.0.0.1:11434/", "http://[::1]:11434"):
            ol.validar_url_local(ok)
        for mal in ("http://10.0.0.5:11434", "http://ejemplo.com", "ftp://localhost", "http://u:p@localhost:1",
                    "http://localhost.evil.com"):
            with self.assertRaises(ErrorOllama, msg=mal):
                ol.validar_url_local(mal)

    def test_etiquetas(self):
        self.assertEqual(ol.etiqueta_valida(" qwen3:4b "), "qwen3:4b")
        for mala in ("", "con espacio", "../x", "/x", "x/", "a" * 201, "salto\nlinea"):
            with self.assertRaises(ErrorOllama, msg=mala):
                ol.etiqueta_valida(mala)

    def test_perfil_por_ram(self):
        self.assertEqual(ol.perfil_recomendado(None), "limited")
        self.assertEqual(ol.perfil_recomendado(8 * GIB), "limited")
        self.assertEqual(ol.perfil_recomendado(16 * GIB), "standard")
        self.assertEqual(ol.perfil_recomendado(32 * GIB), "high")

    def test_ofrecidos_primero_el_recomendado_y_nunca_uno_mayor(self):
        cat = [modelo("g", "high"), modelo("s", "standard"), modelo("l", "limited"), modelo("x", "station")]
        self.assertEqual([m.etiqueta for m in ol.ofrecidos(cat, "standard")], ["s", "l"])
        self.assertEqual([m.etiqueta for m in ol.ofrecidos(cat, "limited")], ["l"])

    def test_el_catalogo_real_se_lee(self):
        cat = ol.leer_catalogo()
        self.assertGreaterEqual(len(cat), 12)
        self.assertTrue(all(m.huella.startswith("sha256:") and m.descarga_mb > 0 for m in cat))
        self.assertEqual({m.perfil for m in cat}, {"limited", "standard", "high", "station"})

    def test_catalogo_roto_o_ausente_es_vacio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            self.assertEqual(ol.leer_catalogo(p), [])
            p.write_text("{no", encoding="utf-8")
            self.assertEqual(ol.leer_catalogo(p), [])


class TestCliente(unittest.TestCase):
    def cliente(self, sesion):
        return ClienteOllama(url=lambda: "http://localhost:11434", sesion=lambda: sesion)

    def test_instalados(self):
        c = self.cliente(SesionOllama(tags=[{"name": "qwen3:4b", "digest": "sha256:" + HUELLA_A, "size": 5}]))
        self.assertEqual(c.instalados(), {"qwen3:4b": {"digest": HUELLA_A, "size": 5}})

    def test_ollama_caido(self):
        with self.assertRaises(ErrorOllama):
            self.cliente(SesionOllama(falla=True)).instalados()

    def test_descarga_con_progreso_y_exito(self):
        pull = RespuestaPull([linea(status="pulling"), linea(status="pulling x", total=100, completed=40),
                              linea(status="success")])
        avances = []
        self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda f, m: avances.append((f, m)), lambda: False)
        self.assertEqual(avances[1][0], 0.4)
        self.assertIn("40 %", avances[1][1])
        self.assertTrue(pull.cerrada)

    def test_el_error_de_ollama_se_muestra_acotado(self):
        pull = RespuestaPull([linea(error="x" * 500)])
        with self.assertRaises(ErrorOllama) as ctx:
            self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda *a: None, lambda: False)
        self.assertLess(len(str(ctx.exception)), 260)

    def test_sin_success_es_error(self):
        pull = RespuestaPull([linea(status="pulling", total=10, completed=5)])
        with self.assertRaises(ErrorOllama):
            self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda *a: None, lambda: False)

    def test_cancelar_corta_y_cierra_sin_error(self):
        pull = RespuestaPull([linea(status="pulling", total=10, completed=1)] * 5)
        self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda *a: None, lambda: True)
        self.assertTrue(pull.cerrada)

    def test_tamano_que_excede_lo_mostrado_se_detiene(self):
        pull = RespuestaPull([linea(status="pulling", total=10_000, completed=1)])
        with self.assertRaises(ErrorOllama):
            self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda *a: None, lambda: False, limite_bytes=100)

    def test_linea_gigante_se_rechaza(self):
        pull = RespuestaPull([b"x" * (70 * 1024)])
        with self.assertRaises(ErrorOllama):
            self.cliente(SesionOllama(pull=pull)).descargar("m:1", lambda *a: None, lambda: False)

    def test_la_descarga_solo_va_al_ollama_local(self):
        c = ClienteOllama(url=lambda: "http://10.0.0.5:11434", sesion=lambda: SesionOllama())
        with self.assertRaises(ErrorOllama):
            c.descargar("m:1", lambda *a: None, lambda: False)

    def test_etiqueta_invalida_no_llega_a_ollama(self):
        s = SesionOllama(pull=RespuestaPull([]))
        with self.assertRaises(ErrorOllama):
            self.cliente(s).descargar("../x", lambda *a: None, lambda: False)
        self.assertEqual(s.posts, [])


class ClienteFalso:
    """Ollama de pega con estado: lo que se «descarga» aparece en `instalados`."""

    def __init__(self, instalados=None, responde=True, descarga=None, falla=None):
        self.estado = dict(instalados or {})
        self.responde, self.descarga, self.falla = responde, descarga, falla
        self.descargas = []

    def instalados(self):
        if not self.responde:
            raise ErrorOllama("Ollama no responde en este equipo.")
        return dict(self.estado)

    def descargar(self, etiqueta, progreso, cancelado, limite_bytes=None):
        self.descargas.append(etiqueta)
        progreso(0.5, "Descargando… 50 %")
        if self.falla:
            raise self.falla
        if self.descarga:
            self.estado[etiqueta] = self.descarga


class TestAdaptadorOllama(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.prefs = Preferencias(Path(self.dir.name) / "p.json")
        self.cliente = ClienteFalso(descarga={"digest": HUELLA_A, "size": 4_000_000})
        self.libre = 100 * GIB
        self.catalogo = [modelo("qwen3:4b"), modelo("pequeno:0.5b", "limited", huella="sha256:" + HUELLA_B, mb=400)]

    def biblioteca(self):
        a = AdaptadorPensamiento(
            self.prefs, lambda: ServicioClaves(AlmacenMemoria()), lambda: (True, []), cliente=self.cliente,
            catalogo=lambda: self.catalogo, ram=lambda: 16 * GIB, libre=lambda: self.libre)
        return Biblioteca(a, self.prefs)

    def agregar(self, b, origen, datos, aceptado=True):
        return b.esperar(b.agregar(origen, datos, aceptado=aceptado).id)

    def test_el_catalogo_ofrece_lo_del_perfil_y_lo_mas_pequeno(self):
        origen = self.biblioteca().descripcion()["origenes"][0]
        self.assertEqual(origen["id"], "catalogo")
        self.assertEqual(origen["campos"][0]["opciones"], ["qwen3:4b", "pequeno:0.5b"])
        self.assertIn("standard", origen["campos"][0]["ayuda"])

    def test_la_revision_muestra_tamano_licencia_huella_y_pide_consentimiento(self):
        r = self.biblioteca().revisar("catalogo", {"modelo": "qwen3:4b"})
        self.assertEqual(r.licencia, "Apache-2.0")
        self.assertEqual(r.tamano_bytes, 4300 * ol.MIB)
        self.assertTrue(any(HUELLA_A[:16] in l for l in r.lineas))
        self.assertIn("4.2 GB", r.consentimientos[0].replace(",", "."))
        self.assertEqual(self.cliente.descargas, [])  # revisar no descarga

    def test_el_perfil_limited_avisa_que_las_respuestas_seran_basicas(self):
        r = self.biblioteca().revisar("catalogo", {"modelo": "pequeno:0.5b"})
        self.assertTrue(any("básicas" in a for a in r.advertencias))

    def test_sin_consentimiento_no_se_descarga(self):
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().agregar("catalogo", {"modelo": "qwen3:4b"}, aceptado=False)
        self.assertEqual(self.cliente.descargas, [])

    def test_descarga_completa_verifica_la_huella_y_registra(self):
        b = self.biblioteca()
        t = self.agregar(b, "catalogo", {"modelo": "qwen3:4b"})
        self.assertEqual(t.estado, "ok")
        self.assertEqual(self.cliente.descargas, ["qwen3:4b"])
        r = b.listar()[0]
        self.assertEqual((r["id"], r["origen"], r["huella"]), ("ollama:qwen3:4b", "ollama", HUELLA_A))

    def test_huella_distinta_tras_descargar_no_se_registra(self):
        self.cliente.descarga = {"digest": HUELLA_B, "size": 1}
        b = self.biblioteca()
        t = self.agregar(b, "catalogo", {"modelo": "qwen3:4b"})
        self.assertEqual(t.estado, "error")
        self.assertIn("huella no coincide", t.error)
        self.assertEqual(b.listar(), [])

    def test_etiqueta_existente_con_otra_huella_no_se_sobrescribe(self):
        self.cliente.estado["qwen3:4b"] = {"digest": HUELLA_B, "size": 1}
        with self.assertRaises(ErrorBiblioteca) as ctx:
            self.biblioteca().revisar("catalogo", {"modelo": "qwen3:4b"})
        self.assertIn("no se sobrescribe", str(ctx.exception))

    def test_ya_instalado_y_coincidente_solo_se_registra_sin_descargar(self):
        self.cliente.estado["qwen3:4b"] = {"digest": HUELLA_A, "size": 9}
        b = self.biblioteca()
        self.assertEqual(b.revisar("catalogo", {"modelo": "qwen3:4b"}).consentimientos, [])
        self.assertEqual(self.agregar(b, "catalogo", {"modelo": "qwen3:4b"}, aceptado=False).estado, "ok")
        self.assertEqual(self.cliente.descargas, [])

    def test_sin_espacio_se_detiene_antes_de_descargar(self):
        self.libre = 1 * GIB
        with self.assertRaises(ErrorBiblioteca) as ctx:
            self.biblioteca().revisar("catalogo", {"modelo": "qwen3:4b"})
        self.assertIn("espacio", str(ctx.exception))
        self.assertEqual(self.cliente.descargas, [])

    def test_ollama_caido_explica_que_hacer(self):
        self.cliente.responde = False
        with self.assertRaises(ErrorBiblioteca) as ctx:
            self.biblioteca().revisar("catalogo", {"modelo": "qwen3:4b"})
        self.assertIn("ollama.com", str(ctx.exception))

    def test_un_modelo_fuera_del_catalogo_no_se_acepta_por_esa_via(self):
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().revisar("catalogo", {"modelo": "otra:cosa"})

    def test_una_descarga_interrumpida_no_queda_registrada(self):
        self.cliente.falla = ErrorOllama("Se interrumpió la descarga. Si la agregas de nuevo, Ollama reanuda.")
        b = self.biblioteca()
        t = self.agregar(b, "catalogo", {"modelo": "qwen3:4b"})
        self.assertEqual(t.estado, "error")
        self.assertIn("reanuda", t.error)
        self.assertEqual(b.listar(), [])

    def test_etiqueta_propia_pide_confirmacion_aparte_y_verifica_despues(self):
        b = self.biblioteca()
        r = b.revisar("etiqueta", {"etiqueta": "modelo:7b"})
        self.assertIn("ollama.com/library", r.consentimientos[0])
        with self.assertRaises(ErrorBiblioteca):
            b.agregar("etiqueta", {"etiqueta": "modelo:7b"}, aceptado=False)
        t = self.agregar(b, "etiqueta", {"etiqueta": "modelo:7b"})
        self.assertEqual(t.estado, "ok")
        self.assertEqual(b.listar()[0]["etiqueta"], "modelo:7b")

    def test_etiqueta_propia_que_ollama_no_deja_instalada_falla(self):
        self.cliente.descarga = None  # «termina» pero no aparece
        t = self.agregar(self.biblioteca(), "etiqueta", {"etiqueta": "modelo:7b"})
        self.assertEqual(t.estado, "error")
        self.assertIn("no muestra", t.error)

    def test_etiqueta_propia_invalida(self):
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().revisar("etiqueta", {"etiqueta": "../x"})

    def test_catalogo_y_ollama_comparten_recurso(self):
        b = self.biblioteca()
        self.agregar(b, "catalogo", {"modelo": "qwen3:4b"})
        with self.assertRaises(ErrorBiblioteca):  # mismo modelo de Ollama: no se duplica
            b.agregar("etiqueta", {"etiqueta": "qwen3:4b"}, aceptado=True)


if __name__ == "__main__":
    unittest.main()
