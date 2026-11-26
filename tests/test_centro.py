"""Centro de configuración (P2): preferencias, primer arranque, bibliotecas y director."""
import json
import pathlib
import sys
import tempfile
import threading
import time
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from centro import (Biblioteca, Campo, DirectorCentro, EstadoPrimerArranque, ErrorBiblioteca,
                    Origen, Preferencias, ResultadoPrueba, Revision)
from centro import preferencias as prefs_mod
from centro import primer_arranque as pa_mod


class AdaptadorFalso:
    """Un tipo de recurso mínimo para probar las reglas comunes del motor."""

    tipo = "voces"
    nombre = "Voces"
    destino = "vozSalida"
    funciones = (("principal", "Voz principal"),)

    def __init__(self, tiempo=0.0, falla=False, consentimiento=True):
        self.tiempo, self.falla, self.consentimiento = tiempo, falla, consentimiento
        self.eliminados = []

    def origenes(self):
        return [Origen("catalogo", "Catálogo", campos=(Campo("voz", "Voz"),))]

    def id_para(self, origen_id, datos):
        return f"piper:{datos['voz']}"

    def revisar(self, origen_id, datos):
        return Revision(titulo=f"Voz {datos['voz']}", tamano_bytes=1000, licencia="CC0",
                        consentimientos=["Descargar la voz"] if self.consentimiento else [])

    def instalar(self, origen_id, datos, progreso, cancelado):
        pasos = 5
        for i in range(pasos):
            if cancelado():
                return {"id": self.id_para(origen_id, datos)}
            progreso((i + 1) / pasos, f"paso {i + 1}")
            time.sleep(self.tiempo / pasos)
        if self.falla:
            raise RuntimeError("boom con detalles internos")
        return {"id": self.id_para(origen_id, datos), "nombre": datos["voz"], "origen": origen_id}

    def probar(self, recurso):
        return ResultadoPrueba(True, f"{recurso['nombre']} suena bien")

    def eliminar(self, recurso):
        self.eliminados.append(recurso["id"])


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)
        self.prefs = Preferencias(self.dir / "preferences.json")
        self.estado = EstadoPrimerArranque(self.dir / "firstrun.json")


class TestPreferencias(Base):
    def test_por_defecto_es_valido_y_sin_secretos(self):
        self.assertEqual(prefs_mod.validar(prefs_mod.por_defecto()), [])
        self.assertEqual(self.prefs.errores_de_carga, [])
        self.assertTrue(self.prefs.obtener("ajustes.memoriaActiva"))  # decisión D2

    def test_ida_y_vuelta_en_disco(self):
        self.prefs.establecer("ajustes.busquedaWeb", False)
        otra = Preferencias(self.dir / "preferences.json")
        self.assertFalse(otra.obtener("ajustes.busquedaWeb"))

    def test_escritura_atomica_no_deja_temporales(self):
        self.prefs.establecer("ajustes.tiempoMaximoLocalSeg", 5)
        self.assertEqual([p.name for p in self.dir.iterdir() if p.name.endswith(".tmp")], [])

    def test_ruta_desconocida_se_rechaza(self):
        with self.assertRaises(KeyError):
            self.prefs.establecer("ajustes.noExiste", 1)
        with self.assertRaises(KeyError):
            self.prefs.establecer("inventada.algo", 1)

    def test_archivo_ilegible_se_aparta_y_se_avisa(self):
        (self.dir / "preferences.json").write_text("{ esto no es json", encoding="utf-8")
        p = Preferencias(self.dir / "preferences.json")
        self.assertTrue(p.errores_de_carga)
        self.assertTrue(any(f.name.startswith("preferences.json.invalido-") for f in self.dir.iterdir()))
        self.assertEqual(p.obtener("schemaVersion"), 1)  # arranca con los valores por defecto

    def test_version_desconocida_no_se_sustituye_en_silencio(self):
        (self.dir / "preferences.json").write_text(json.dumps({"schemaVersion": 99}), encoding="utf-8")
        p = Preferencias(self.dir / "preferences.json")
        self.assertIn("versión de esquema no soportada: 99", " ".join(p.errores_de_carga))

    def test_un_secreto_en_preferencias_se_rechaza(self):
        with self.assertRaises(ValueError):
            self.prefs.reemplazar_biblioteca("voces", [{"id": "x", "api_key": "gsk_123"}])
        self.assertEqual(self.prefs.obtener("bibliotecas.voces"), [])

    def test_secreto_anidado_tambien(self):
        datos = prefs_mod.por_defecto()
        datos["cuentasNube"] = [{"id": "groq", "credentialRef": "ok", "cabeceras": {"Authorization": "Bearer x"}}]
        self.assertTrue(any("secreto" in e for e in prefs_mod.validar(datos)))

    def test_la_referencia_opaca_a_credenciales_si_vale(self):
        datos = prefs_mod.por_defecto()
        datos["cuentasNube"] = [{"id": "groq", "credentialRef": "D.A.R.K/api/groq"}]
        self.assertEqual(prefs_mod.validar(datos), [])

    def test_biblioteca_desconocida(self):
        with self.assertRaises(KeyError):
            self.prefs.reemplazar_biblioteca("inventada", [])

    def test_lo_que_se_lee_es_una_copia(self):
        copia = self.prefs.todo()
        copia["ajustes"]["busquedaWeb"] = "manipulado"
        self.assertTrue(self.prefs.obtener("ajustes.busquedaWeb"))

    def test_carga_completa_los_defectos_que_faltan(self):
        (self.dir / "preferences.json").write_text(json.dumps({
            "schemaVersion": 1, "bibliotecas": {"voces": []}, "cuentasNube": [],
            "asignaciones": {}, "ajustes": {"busquedaWeb": False}}), encoding="utf-8")
        p = Preferencias(self.dir / "preferences.json")
        self.assertFalse(p.obtener("ajustes.busquedaWeb"))
        self.assertTrue(p.obtener("ajustes.memoriaActiva"))  # el defecto que faltaba


class TestPrimerArranque(Base):
    def test_al_principio_hay_recorrido_pendiente(self):
        self.assertTrue(self.estado.pendiente())
        self.assertEqual(self.estado.pasos_pendientes(), list(pa_mod.PASOS))

    def test_completar_deja_los_pasos_sin_tocar_como_omitidos(self):
        self.estado.marcar("bienvenida", "hecho")
        self.estado.completar("2026-11-23T00:00:00+00:00")
        self.assertFalse(self.estado.pendiente())
        self.assertEqual(self.estado.estado_de("resumen"), "omitido")

    def test_persiste_entre_sesiones(self):
        self.estado.marcar("bienvenida", "hecho")
        self.estado.completar("2026-11-23T00:00:00+00:00")
        otra = EstadoPrimerArranque(self.dir / "firstrun.json")
        self.assertFalse(otra.pendiente())
        self.assertEqual(otra.estado_de("bienvenida"), "hecho")

    def test_un_paso_nuevo_vuelve_a_pedirse_sin_repetir_los_hechos(self):
        self.estado.completar("2026-11-23T00:00:00+00:00")
        (self.dir / "firstrun.json").write_text(json.dumps({
            "schemaVersion": 1, "wizardVersion": "0", "completadoEn": "x",
            "pasos": {"bienvenida": "hecho"}}), encoding="utf-8")
        otra = EstadoPrimerArranque(self.dir / "firstrun.json")
        self.assertTrue(otra.pendiente())
        self.assertEqual(otra.pasos_pendientes(), ["equipo", "ruta", "prueba", "resumen"])

    def test_paso_o_estado_desconocido(self):
        with self.assertRaises(KeyError):
            self.estado.marcar("inventado", "hecho")
        with self.assertRaises(ValueError):
            self.estado.marcar("bienvenida", "quizas")

    def test_archivo_roto_vuelve_a_empezar_y_lo_dice(self):
        (self.dir / "firstrun.json").write_text("basura", encoding="utf-8")
        e = EstadoPrimerArranque(self.dir / "firstrun.json")
        self.assertTrue(e.pendiente())
        self.assertIn("firstrun.json", e.error_de_carga)

    def test_aceptacion_del_instalador(self):
        ruta = self.dir / "terms-acceptance.json"
        ruta.write_text("﻿" + json.dumps({
            "schemaVersion": 1, "termsVersion": "tester-v1", "termsSha256": "abc",
            "acceptedAtUtc": "2026-11-23T20:00:00Z",
            "selectedComponents": [{"Id": "dark-app"}]}), encoding="utf-8")
        a = pa_mod.leer_aceptacion_instalador(ruta)
        self.assertEqual(a, {"version": "tester-v1", "sha256": "abc", "aceptadasEn": "2026-11-23T20:00:00Z"})
        self.assertNotIn("selectedComponents", a)  # no se expone la lista de componentes

    def test_aceptacion_ausente_o_rota_es_none(self):
        self.assertIsNone(pa_mod.leer_aceptacion_instalador(self.dir / "no-existe.json"))
        (self.dir / "mala.json").write_text("{", encoding="utf-8")
        self.assertIsNone(pa_mod.leer_aceptacion_instalador(self.dir / "mala.json"))


class TestBiblioteca(Base):
    def setUp(self):
        super().setUp()
        self.adaptador = AdaptadorFalso()
        self.cambios = []
        self.bib = Biblioteca(self.adaptador, self.prefs, al_cambiar=lambda: self.cambios.append(1))

    def _agregar(self, voz="davefx", aceptado=True, **extra):
        trabajo = self.bib.agregar("catalogo", {"voz": voz}, aceptado=aceptado, **extra)
        return self.bib.esperar(trabajo.id)

    def test_agregar_guarda_el_recurso_y_notifica(self):
        t = self._agregar()
        self.assertEqual((t.estado, t.progreso), ("ok", 1.0))
        self.assertEqual([r["id"] for r in self.bib.listar()], ["piper:davefx"])
        self.assertEqual(self.prefs.obtener("bibliotecas.voces")[0]["id"], "piper:davefx")
        self.assertTrue(self.cambios)

    def test_sin_consentimiento_no_se_instala_nada(self):
        with self.assertRaises(ErrorBiblioteca) as e:
            self.bib.agregar("catalogo", {"voz": "x"}, aceptado=False)
        self.assertIn("consentimiento", e.exception.mensajes[0])
        self.assertEqual(self.bib.listar(), [])

    def test_aceptado_debe_ser_exactamente_true(self):
        for valor in ("true", 1, None):
            with self.assertRaises(ErrorBiblioteca):
                self.bib.agregar("catalogo", {"voz": "x"}, aceptado=valor)

    def test_si_la_revision_no_pide_consentimiento_no_hace_falta(self):
        bib = Biblioteca(AdaptadorFalso(consentimiento=False), self.prefs)
        t = bib.esperar(bib.agregar("catalogo", {"voz": "x"}, aceptado=False).id)
        self.assertEqual(t.estado, "ok")

    def test_campos_requeridos(self):
        with self.assertRaises(ErrorBiblioteca) as e:
            self.bib.agregar("catalogo", {"voz": "  "}, aceptado=True)
        self.assertIn("Falta «Voz»", e.exception.mensajes[0])

    def test_origen_desconocido(self):
        with self.assertRaises(ErrorBiblioteca):
            self.bib.revisar("inventado", {})

    def test_no_sobrescribe_sin_confirmar(self):
        self._agregar()
        with self.assertRaises(ErrorBiblioteca) as e:
            self.bib.agregar("catalogo", {"voz": "davefx"}, aceptado=True)
        self.assertIn("No se sobrescribe", e.exception.mensajes[0])
        self.assertEqual(self._agregar(reemplazar=True).estado, "ok")
        self.assertEqual(len(self.bib.listar()), 1)

    def test_un_fallo_del_adaptador_no_filtra_detalles_internos(self):
        bib = Biblioteca(AdaptadorFalso(falla=True), self.prefs)
        t = bib.esperar(bib.agregar("catalogo", {"voz": "x"}, aceptado=True).id)
        self.assertEqual(t.estado, "error")
        self.assertNotIn("boom", t.error)
        self.assertEqual(bib.listar(), [])

    def test_cancelar_no_guarda_nada(self):
        bib = Biblioteca(AdaptadorFalso(tiempo=1.0), self.prefs)
        t = bib.agregar("catalogo", {"voz": "x"}, aceptado=True)
        time.sleep(0.1)
        bib.cancelar(t.id)
        final = bib.esperar(t.id, 3)
        self.assertEqual(final.estado, "cancelado")
        self.assertEqual(bib.listar(), [])

    def test_probar(self):
        self._agregar()
        self.assertEqual(self.bib.probar("piper:davefx").como_dict(), {"ok": True, "mensaje": "davefx suena bien"})

    def test_probar_recurso_inexistente(self):
        with self.assertRaises(ErrorBiblioteca):
            self.bib.probar("nada")

    def test_asignar_valida_funcion_politica_y_recursos(self):
        self._agregar()
        with self.assertRaises(ErrorBiblioteca):
            self.bib.asignar("inventada", ["piper:davefx"], "solo_local")
        with self.assertRaises(ErrorBiblioteca):
            self.bib.asignar("principal", ["piper:davefx"], "a_veces")
        with self.assertRaises(ErrorBiblioteca):
            self.bib.asignar("principal", ["piper:fantasma"], "solo_local")
        with self.assertRaises(ErrorBiblioteca):
            self.bib.asignar("principal", ["piper:davefx", "piper:davefx"], "solo_local")
        self.bib.asignar("principal", ["piper:davefx"], "solo_local")
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal"),
                         {"politica": "solo_local", "cadena": ["piper:davefx"]})

    def test_eliminar_en_uso_pide_confirmacion_y_limpia_la_asignacion(self):
        self._agregar()
        self.bib.asignar("principal", ["piper:davefx"], "solo_local")
        self.assertEqual(self.bib.listar()[0]["enUso"][0]["funcion"], "principal")
        with self.assertRaises(ErrorBiblioteca) as e:
            self.bib.eliminar("piper:davefx")
        self.assertIn("principal", e.exception.mensajes[0])
        self.assertEqual(len(self.bib.listar()), 1)  # no se tocó
        usos = self.bib.eliminar("piper:davefx", forzar=True)
        self.assertEqual(usos[0]["funcion"], "principal")
        self.assertEqual(self.bib.listar(), [])
        self.assertEqual(self.adaptador.eliminados, ["piper:davefx"])
        self.assertIsNone(self.prefs.obtener("asignaciones.vozSalida.principal"))

    def test_eliminar_de_una_cadena_conserva_el_resto(self):
        self._agregar("a")
        self._agregar("b")
        self.bib.asignar("principal", ["piper:a", "piper:b"], "local_primero")
        self.bib.eliminar("piper:a", forzar=True)
        self.assertEqual(self.prefs.obtener("asignaciones.vozSalida.principal")["cadena"], ["piper:b"])

    def test_el_recurso_devuelto_sin_id_es_un_error(self):
        class Malo(AdaptadorFalso):
            def instalar(self, *a, **k): return {"nombre": "sin id"}
        bib = Biblioteca(Malo(), self.prefs)
        t = bib.esperar(bib.agregar("catalogo", {"voz": "x"}, aceptado=True).id)
        self.assertEqual(t.estado, "error")


class TestDirector(Base):
    def setUp(self):
        super().setUp()
        self.capacidades = {"resumen": {"total": 8, "pendientes": 2, "idsPendientes": ["ia_chat", "voz_salida"]}, "items": []}
        self.aceptacion = {"version": "tester-v1", "sha256": "abc", "aceptadasEn": "2026-11-23T20:00:00Z"}
        self.bib = Biblioteca(AdaptadorFalso(), self.prefs)
        self.d = DirectorCentro(self.prefs, self.estado, {"voces": self.bib},
                                capacidades=lambda: self.capacidades, aceptacion=lambda: self.aceptacion,
                                ahora=lambda: "2026-11-23T21:00:00+00:00")

    def test_secciones_incluyen_resumen_y_cada_biblioteca(self):
        ids = [s["id"] for s in self.d.secciones()]
        self.assertEqual(ids, ["resumen", "bib:voces"])
        self.assertTrue(self.d.secciones()[0]["aviso"])  # hay pendientes

    def test_sin_bibliotecas_solo_hay_resumen(self):
        d = DirectorCentro(self.prefs, self.estado, capacidades=lambda: None)
        self.assertEqual([s["id"] for s in d.secciones()], ["resumen"])

    def test_el_recorrido_se_ofrece_una_sola_vez_por_sesion(self):
        self.assertTrue(self.d.debe_ofrecer_primer_arranque())
        self.d.abrir_primer_arranque()
        self.assertFalse(self.d.debe_ofrecer_primer_arranque())

    def test_no_se_ofrece_si_ya_se_completo(self):
        self.estado.completar("x")
        self.assertFalse(self.d.debe_ofrecer_primer_arranque())

    def test_recorrido_completo_paso_a_paso(self):
        carga = self.d.abrir_primer_arranque()
        self.assertEqual(carga["primerArranque"]["paso"], "bienvenida")
        self.assertEqual(carga["bienvenida"]["aceptacion"]["version"], "tester-v1")
        self.assertTrue(self.d.operar("paso", {"accion": "siguiente"})["ok"])
        carga = self.d.datos()
        self.assertEqual(carga["primerArranque"]["paso"], "equipo")
        self.assertIsNone(carga["bienvenida"])
        self.d.operar("paso", {"accion": "anterior"})
        self.assertEqual(self.d.datos()["primerArranque"]["paso"], "bienvenida")
        self.d.operar("paso", {"accion": "siguiente"})
        self.d.operar("paso", {"accion": "siguiente"})  # equipo
        self.assertEqual(self.d.datos()["primerArranque"]["paso"], "ruta")
        self.assertFalse(self.d.operar("paso", {"accion": "siguiente"})["ok"])  # hay que elegir ruta
        self.d.operar("ruta_elegir", {"ruta": "rapida"})
        self.d.operar("paso", {"accion": "siguiente"})  # ruta
        self.assertEqual(self.d.datos()["primerArranque"]["paso"], "prueba")
        self.d.operar("paso", {"accion": "siguiente"})  # prueba
        self.assertEqual(self.d.datos()["primerArranque"]["paso"], "resumen")
        self.d.operar("paso", {"accion": "siguiente"})  # último paso: termina
        self.assertIsNone(self.d.datos()["primerArranque"])
        self.assertFalse(self.estado.pendiente())
        self.assertEqual(self.estado.estado_de("bienvenida"), "hecho")

    def test_omitir_marca_omitido(self):
        self.d.abrir_primer_arranque()
        self.d.operar("paso", {"accion": "omitir"})
        self.assertEqual(self.estado.estado_de("bienvenida"), "omitido")

    def test_salir_termina_el_recorrido_sin_perder_nada(self):
        self.d.abrir_primer_arranque()
        self.d.operar("paso", {"accion": "salir"})
        self.assertFalse(self.estado.pendiente())
        self.assertIsNone(self.d.datos()["primerArranque"])

    def test_reabrir_retoma_en_el_primer_paso_pendiente(self):
        self.d.abrir_primer_arranque()
        self.d.operar("paso", {"accion": "siguiente"})
        d2 = DirectorCentro(self.prefs, self.estado, capacidades=lambda: None, aceptacion=lambda: None)
        self.assertEqual(d2.abrir_primer_arranque()["primerArranque"]["paso"], "equipo")

    def test_paso_sin_recorrido_activo_es_un_error(self):
        r = self.d.operar("paso", {"accion": "siguiente"})
        self.assertFalse(r["ok"])
        self.assertTrue(self.d.datos()["aviso"]["error"])

    def test_navegar_a_mano_sale_del_recorrido(self):
        self.d.abrir_primer_arranque()
        self.assertTrue(self.d.operar("ir", {"seccion": "bib:voces"})["ok"])
        carga = self.d.datos()
        self.assertIsNone(carga["primerArranque"])
        self.assertEqual(carga["seccion"], "bib:voces")
        self.assertEqual(carga["biblioteca"]["tipo"], "voces")

    def test_seccion_inexistente(self):
        self.assertFalse(self.d.operar("ir", {"seccion": "inventada"})["ok"])

    def test_operacion_desconocida(self):
        self.assertFalse(self.d.operar("hackear", {})["ok"])

    def test_ciclo_completo_de_una_biblioteca(self):
        self.d.operar("ir", {"seccion": "bib:voces"})
        r = self.d.operar("bib_revisar", {"tipo": "voces", "origen": "catalogo", "datos": {"voz": "davefx"}})
        self.assertTrue(r["ok"])
        rev = self.d.datos()["biblioteca"]["revision"]
        self.assertEqual(rev["titulo"], "Voz davefx")
        self.assertEqual(rev["consentimientos"], ["Descargar la voz"])
        self.assertFalse(self.d.operar("bib_agregar", {"tipo": "voces", "origen": "catalogo", "datos": {"voz": "davefx"}})["ok"])
        self.assertTrue(self.d.operar("bib_agregar", {"tipo": "voces", "origen": "catalogo",
                                                      "datos": {"voz": "davefx"}, "aceptado": True})["ok"])
        trabajo = self.d.datos()["biblioteca"]["trabajo"]
        self.bib.esperar(trabajo["id"])
        carga = self.d.datos()["biblioteca"]
        self.assertEqual(carga["trabajo"]["estado"], "ok")
        self.assertEqual([x["id"] for x in carga["recursos"]], ["piper:davefx"])
        self.d.operar("bib_probar", {"tipo": "voces", "recurso": "piper:davefx"})
        self.assertTrue(self.d.datos()["biblioteca"]["pruebas"]["piper:davefx"]["ok"])
        self.assertTrue(self.d.operar("bib_asignar", {"tipo": "voces", "funcion": "principal",
                                                      "cadena": ["piper:davefx"], "politica": "solo_local"})["ok"])
        self.assertFalse(self.d.operar("bib_eliminar", {"tipo": "voces", "recurso": "piper:davefx"})["ok"])
        self.assertTrue(self.d.operar("bib_eliminar", {"tipo": "voces", "recurso": "piper:davefx", "forzar": True})["ok"])
        self.assertEqual(self.d.datos()["biblioteca"]["recursos"], [])

    def test_biblioteca_inexistente(self):
        self.assertFalse(self.d.operar("bib_revisar", {"tipo": "nada", "origen": "x"})["ok"])

    def test_cadena_mal_formada(self):
        self.assertFalse(self.d.operar("bib_asignar", {"tipo": "voces", "funcion": "principal",
                                                       "cadena": "no-es-lista", "politica": "solo_local"})["ok"])

    def test_los_errores_de_carga_se_muestran(self):
        (self.dir / "preferences.json").write_text("basura", encoding="utf-8")
        p = Preferencias(self.dir / "preferences.json")
        d = DirectorCentro(p, self.estado, capacidades=lambda: None)
        self.assertTrue(d.datos()["errores"])

    def test_la_carga_es_serializable_y_sin_secretos(self):
        self.d.abrir_primer_arranque()
        texto = json.dumps(self.d.datos())
        for prohibido in ("api_key", "password", "Authorization"):
            self.assertNotIn(prohibido, texto)

    def test_concurrencia_de_lecturas_mientras_se_instala(self):
        bib = Biblioteca(AdaptadorFalso(tiempo=0.3), self.prefs)
        d = DirectorCentro(self.prefs, self.estado, {"voces": bib}, capacidades=lambda: None)
        d.operar("ir", {"seccion": "bib:voces"})
        d.operar("bib_agregar", {"tipo": "voces", "origen": "catalogo", "datos": {"voz": "x"}, "aceptado": True})
        errores = []
        def leer():
            try:
                for _ in range(40):
                    d.datos()
                    time.sleep(0.005)
            except Exception as error:
                errores.append(error)
        hilos = [threading.Thread(target=leer) for _ in range(4)]
        [h.start() for h in hilos]; [h.join() for h in hilos]
        self.assertEqual(errores, [])


if __name__ == "__main__":
    unittest.main()
