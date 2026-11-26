"""P3: claves en el Administrador de credenciales, sección «Claves» y migración."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

import credenciales
from centro import DirectorCentro, EstadoPrimerArranque, Preferencias, SeccionClaves
from credenciales import AlmacenMemoria, ErrorClaves, ServicioClaves, migracion

SECRETO = "gsk_SECRETO-que-no-debe-salir-123"


def servicio():
    return ServicioClaves(AlmacenMemoria())


class TestServicio(unittest.TestCase):
    def test_guardar_y_leer(self):
        s = servicio()
        s.guardar("groq", SECRETO)
        self.assertEqual(s.leer("groq"), SECRETO)
        self.assertTrue(s.existe("groq"))

    def test_el_listado_no_lleva_el_valor(self):
        s = servicio()
        s.guardar("groq", SECRETO, "mi cuenta")
        self.assertNotIn(SECRETO, json.dumps(s.listar()))
        self.assertEqual(s.listar()[0]["proveedor"], "groq")

    def test_el_destino_lleva_el_prefijo(self):
        a = AlmacenMemoria()
        ServicioClaves(a).guardar("Groq", SECRETO)
        self.assertEqual([e.target for e in a.listar("")], ["D.A.R.K/api/groq"])

    def test_rechaza_ids_raros(self):
        s = servicio()
        for malo in ("", "con espacio", "../x", "a" * 41, "Ñandú", "x/y"):
            with self.assertRaises(ErrorClaves, msg=malo):
                s.guardar(malo, SECRETO)

    def test_rechaza_valores_raros_sin_filtrarlos(self):
        s = servicio()
        for malo in ("", "   ", "dos palabras", "salto\nde linea", "x" * 1001):
            with self.assertRaises(ErrorClaves) as ctx:
                s.guardar("groq", malo)
            self.assertNotIn(malo.strip() or "§", str(ctx.exception) if malo.strip() else "")

    def test_valor_con_espacios_en_los_bordes_se_recorta(self):
        s = servicio()
        s.guardar("groq", f"  {SECRETO}\n")
        self.assertEqual(s.leer("groq"), SECRETO)

    def test_borrar(self):
        s = servicio()
        s.guardar("groq", SECRETO)
        self.assertTrue(s.borrar("groq"))
        self.assertFalse(s.borrar("groq"))
        self.assertEqual(s.leer("groq"), "")

    def test_escritura_que_no_se_lee_de_vuelta_no_cuenta(self):
        class Roto(AlmacenMemoria):
            def leer(self, target):
                return None
        with self.assertRaises(ErrorClaves):
            ServicioClaves(Roto()).guardar("groq", SECRETO)

    def test_clave_de_nunca_lanza(self):
        class Muerto(AlmacenMemoria):
            def leer(self, target):
                raise RuntimeError("sin almacén")
        credenciales.fijar_servicio(ServicioClaves(Muerto()))
        try:
            self.assertEqual(credenciales.clave_de("groq"), "")
        finally:
            credenciales.fijar_servicio(None)

    def test_id_desde_nombre(self):
        self.assertEqual(credenciales.id_desde_nombre("Groq 2"), "groq-2")
        self.assertEqual(credenciales.id_desde_nombre("!!!"), "")


class ConArchivo(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ruta = Path(self.dir.name) / "online_coder.json"
        self.s = servicio()

    def escribir(self, **extra):
        datos = {"enabled": True, "providers": [
            {"name": "groq-1", "provider": "groq", "api_key": SECRETO, "chat_model": "m1"},
            {"name": "groq-2", "provider": "groq", "api_key": SECRETO + "2", "chat_model": "m2"},
            {"name": "sin-clave", "provider": "openrouter", "chat_model": "m3"},
        ], **extra}
        self.ruta.write_text(json.dumps(datos), encoding="utf-8")


class TestMigracion(ConArchivo):
    def test_analizar_no_incluye_valores(self):
        self.escribir()
        analisis = migracion.analizar(self.ruta, self.s)
        self.assertEqual([e["id"] for e in analisis["entradas"]], ["groq-1", "groq-2"])
        self.assertNotIn(SECRETO, json.dumps(analisis))
        self.assertFalse(self.s.existe("groq-1"))  # analizar no escribe nada

    def test_analizar_sin_archivo(self):
        analisis = migracion.analizar(self.ruta, self.s)
        self.assertFalse(analisis["existe"])
        self.assertEqual(analisis["entradas"], [])

    def test_importar_conserva_el_archivo_si_no_se_pide_borrarlo(self):
        self.escribir()
        antes = self.ruta.read_text(encoding="utf-8")
        r = migracion.importar(self.ruta, self.s)
        self.assertEqual(r["importadas"], ["groq-1", "groq-2"])
        self.assertFalse(r["origenBorrado"])
        self.assertEqual(self.s.leer("groq-2"), SECRETO + "2")
        self.assertEqual(self.ruta.read_text(encoding="utf-8"), antes)

    def test_importar_y_borrar_origen_deja_la_referencia(self):
        self.escribir(timeout=30)
        r = migracion.importar(self.ruta, self.s, borrar_origen=True)
        self.assertTrue(r["origenBorrado"])
        texto = self.ruta.read_text(encoding="utf-8")
        self.assertNotIn(SECRETO, texto)
        datos = json.loads(texto)
        self.assertEqual(datos["timeout"], 30)  # lo demás no se toca
        self.assertEqual([p.get("credencial") for p in datos["providers"]], ["groq-1", "groq-2", None])
        self.assertTrue(all("api_key" not in p for p in datos["providers"]))

    def test_no_pisa_una_clave_existente_salvo_que_se_pida(self):
        self.escribir()
        self.s.guardar("groq-1", "la-que-ya-tenia")
        r = migracion.importar(self.ruta, self.s)
        self.assertEqual(r["omitidas"], ["groq-1"])
        self.assertEqual(self.s.leer("groq-1"), "la-que-ya-tenia")
        migracion.importar(self.ruta, self.s, reemplazar=True)
        self.assertEqual(self.s.leer("groq-1"), SECRETO)

    def test_si_algo_falla_el_origen_no_se_toca(self):
        self.escribir()
        antes = self.ruta.read_text(encoding="utf-8")

        class Falla(AlmacenMemoria):
            def escribir(self, target, secreto, comentario=""):
                if target.endswith("groq-2"):
                    raise credenciales.ErrorAlmacen("disco lleno")
                super().escribir(target, secreto, comentario)
        with self.assertRaises(ErrorClaves):
            migracion.importar(self.ruta, ServicioClaves(Falla()), borrar_origen=True)
        self.assertEqual(self.ruta.read_text(encoding="utf-8"), antes)

    def test_ids_repetidos_se_distinguen(self):
        self.ruta.write_text(json.dumps({"providers": [
            {"name": "groq", "api_key": "a"}, {"name": "Groq", "api_key": "b"}]}), encoding="utf-8")
        ids = [e["id"] for e in migracion.analizar(self.ruta, self.s)["entradas"]]
        self.assertEqual(ids, ["groq", "groq-2"])

    def test_archivo_roto_da_error_claro(self):
        self.ruta.write_text("{no es json", encoding="utf-8")
        with self.assertRaises(ErrorClaves):
            migracion.analizar(self.ruta, self.s)

    def test_el_entorno_se_informa_pero_no_se_toca(self):
        os.environ["DARK_CHAT_API_KEY"] = SECRETO
        try:
            self.assertTrue(migracion.analizar(self.ruta, self.s)["entorno"])
        finally:
            del os.environ["DARK_CHAT_API_KEY"]
        self.assertFalse(migracion.analizar(self.ruta, self.s)["entorno"])


class TestSeccionYDirector(ConArchivo):
    def setUp(self):
        super().setUp()
        base = Path(self.dir.name)
        self.director = DirectorCentro(
            Preferencias(base / "preferences.json"), EstadoPrimerArranque(base / "firstrun.json"),
            claves=SeccionClaves(lambda: self.s, lambda: self.ruta))

    def carga(self):
        return self.director.datos("claves")

    def test_la_seccion_existe_y_lista_los_proveedores_conocidos(self):
        c = self.carga()
        self.assertIn("claves", [s["id"] for s in c["secciones"]])
        self.assertEqual(c["seccion"], "claves")
        ids = [p["id"] for p in c["claves"]["proveedores"]]
        for esperado in ("groq", "openrouter", "gemini", "elevenlabs", "fishaudio"):
            self.assertIn(esperado, ids)

    def test_sin_seccion_de_claves_no_hay_seccion(self):
        base = Path(self.dir.name)
        sin = DirectorCentro(Preferencias(base / "p.json"), EstadoPrimerArranque(base / "f.json"))
        self.assertNotIn("claves", [s["id"] for s in sin.secciones()])

    def test_guardar_nunca_devuelve_el_valor(self):
        r = self.director.operar("clave_guardar", {"proveedor": "groq", "valor": SECRETO})
        self.assertTrue(r["ok"])
        c = self.carga()
        self.assertNotIn(SECRETO, json.dumps(c))
        fila = next(p for p in c["claves"]["proveedores"] if p["id"] == "groq")
        self.assertTrue(fila["guardada"])
        self.assertEqual(self.s.leer("groq"), SECRETO)

    def test_guardar_voz_avisa_del_consumo(self):
        self.director.operar("clave_guardar", {"proveedor": "elevenlabs", "valor": SECRETO})
        self.assertIn("consumo", self.carga()["aviso"]["mensaje"])
        fila = next(p for p in self.carga()["claves"]["proveedores"] if p["id"] == "elevenlabs")
        self.assertIn("consumo", fila["aviso"])

    def test_un_error_no_filtra_el_valor(self):
        r = self.director.operar("clave_guardar", {"proveedor": "NO VALIDO", "valor": SECRETO})
        self.assertFalse(r["ok"])
        self.assertNotIn(SECRETO, json.dumps(self.carga()))
        self.assertNotIn(SECRETO, r["error"])

    def test_borrar_pide_confirmacion(self):
        self.s.guardar("groq", SECRETO)
        self.assertFalse(self.director.operar("clave_borrar", {"proveedor": "groq"})["ok"])
        self.assertTrue(self.s.existe("groq"))
        self.assertTrue(self.director.operar("clave_borrar", {"proveedor": "groq", "confirmado": True})["ok"])
        self.assertFalse(self.s.existe("groq"))

    def test_las_claves_ajenas_a_la_lista_tambien_se_ven(self):
        self.s.guardar("mi-proveedor", SECRETO)
        ids = [p["id"] for p in self.carga()["claves"]["proveedores"]]
        self.assertIn("mi-proveedor", ids)

    def test_migracion_pide_consentimiento_y_revision_previa(self):
        self.escribir()
        self.director.operar("clave_revisar", {})
        m = self.carga()["claves"]["migracion"]
        self.assertEqual([e["id"] for e in m["entradas"]], ["groq-1", "groq-2"])
        self.assertNotIn(SECRETO, json.dumps(self.carga()))
        self.assertFalse(self.director.operar("clave_migrar", {})["ok"])  # sin `aceptado`
        self.assertFalse(self.s.existe("groq-1"))
        r = self.director.operar("clave_migrar", {"aceptado": True, "borrarOrigen": True})
        self.assertTrue(r["ok"])
        self.assertTrue(self.s.existe("groq-1") and self.s.existe("groq-2"))
        self.assertNotIn(SECRETO, self.ruta.read_text(encoding="utf-8"))
        self.assertIsNone(self.carga()["claves"]["migracion"])

    def test_cambiar_de_seccion_descarta_la_revision(self):
        self.escribir()
        self.director.operar("clave_revisar", {})
        self.director.operar("ir", {"seccion": "resumen"})
        self.assertIsNone(self.director.datos("claves")["claves"]["migracion"])


class TestConsumidores(unittest.TestCase):
    """El rotador y el chat remoto leen la clave del almacén, no del archivo."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.s = servicio()
        credenciales.fijar_servicio(self.s)
        self.addCleanup(credenciales.fijar_servicio, None)
        base = Path(self.dir.name) / "data"
        base.mkdir()
        os.environ["DARK_USER_DATA_DIR"] = str(base)
        self.addCleanup(os.environ.pop, "DARK_USER_DATA_DIR", None)
        self.config = Path(self.dir.name) / "config"
        self.config.mkdir()
        (self.config / "online_coder.json").write_text(json.dumps({
            "enabled": True,
            "providers": [{"name": "groq", "provider": "groq", "chat_model": "m", "model": "m",
                           "credencial": "groq"}]}), encoding="utf-8")

    def test_remoto_toma_la_clave_del_almacen_y_el_archivo_del_usuario(self):
        from proveedores.llm import remoto
        remoto._cache_config = None
        self.assertEqual(remoto._leer_config()["providers"], [])  # sin clave no hay proveedor
        self.s.guardar("groq", SECRETO)
        remoto._cache_config = None
        try:
            provs = remoto._leer_config()["providers"]
            self.assertEqual([p["api_key"] for p in provs], [SECRETO])
            self.assertTrue(remoto._leer_config()["ruta"].startswith(str(self.config)))
        finally:
            remoto._cache_config = None

    def test_los_roles_de_trabajo_toman_la_clave_del_almacen(self):
        from proveedores.llm import remoto
        (self.config / "online_coder.json").write_text(json.dumps({
            "enabled": True, "providers": [{"name": "Groq", "provider": "groq",
                                            "model": "codigo", "text_model": "texto"}]}),
            encoding="utf-8")
        self.s.guardar("groq", SECRETO)
        remoto._cache_config = None
        try:
            por_rol = remoto._leer_config()["por_rol"]
            self.assertEqual([p["api_key"] for p in por_rol["codigo"] + por_rol["texto"]],
                             [SECRETO, SECRETO])
        finally:
            remoto._cache_config = None

    def test_la_referencia_por_nombre_funciona_sin_campo_credencial(self):
        from proveedores.llm import remoto
        (self.config / "online_coder.json").write_text(json.dumps({
            "enabled": True, "providers": [{"name": "Groq", "provider": "groq", "chat_model": "m"}]}),
            encoding="utf-8")
        self.s.guardar("groq", SECRETO)
        remoto._cache_config = None
        try:
            self.assertEqual(len(remoto._leer_config()["providers"]), 1)
        finally:
            remoto._cache_config = None


if __name__ == "__main__":
    unittest.main()
