"""P7: pasos fijos del primer arranque, presets de la ruta rápida y prueba final."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import (Biblioteca, DescriptorEquipo, DirectorCentro, EstadoPrimerArranque, ErrorBiblioteca,
                    Preferencias, ResultadoPrueba, SeccionClaves)
from centro import presets
from centro.ollama_local import ErrorOllama, ModeloCatalogo
from credenciales import AlmacenMemoria, ServicioClaves

GIB = 1024 ** 3
CATALOGO = [ModeloCatalogo("chat:4b", "chat", "standard", "sha256:" + "a" * 64, 4300, "Apache-2.0", "x"),
            ModeloCatalogo("orden:7b", "nucleus", "standard", "sha256:" + "b" * 64, 4700, "Apache-2.0", "x"),
            ModeloCatalogo("cod:7b", "coder", "standard", "sha256:" + "c" * 64, 4700, "Apache-2.0", "x")]


class Adaptador:
    """Adaptador de pega con los recursos ya guardados en preferencias."""

    def __init__(self, tipo, nombre, destino, funciones, probar_ok=True):
        self.tipo, self.nombre, self.destino, self.funciones = tipo, nombre, destino, funciones
        self.guia, self.probar_ok = f"Guía de {nombre}", probar_ok

    def origenes(self):
        return []

    def id_para(self, o, d):
        return d["id"]

    def revisar(self, o, d):
        raise ErrorBiblioteca("no")

    def instalar(self, *a):
        raise ErrorBiblioteca("no")

    def probar(self, recurso):
        return ResultadoPrueba(self.probar_ok, "Sonó bien" if self.probar_ok else "Falló")

    def eliminar(self, recurso):
        pass


def local(i, etiqueta, rol=None):
    r = {"id": i, "nombre": etiqueta, "origen": "ollama", "etiqueta": etiqueta}
    if rol:
        r["rol"] = rol
    return r


def nube(i, modelo="m"):
    return {"id": i, "nombre": i, "origen": "nube", "cuenta": "groq", "modelo": modelo, "base_url": "https://x"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.prefs = Preferencias(base / "p.json")
        self.estado = EstadoPrimerArranque(base / "f.json")
        self.cambios = 0
        self.claves = ServicioClaves(AlmacenMemoria())
        self.voz_ok = True

    def poner(self, pensamiento=(), voces=()):
        self.prefs.reemplazar_biblioteca("modelosPensamiento", list(pensamiento))
        self.prefs.reemplazar_biblioteca("voces", list(voces))

    def director(self, con_claves=True):
        bibs = {"modelosPensamiento": Biblioteca(Adaptador(
                    "modelosPensamiento", "Modelos de pensamiento", "pensamiento",
                    (("chat", "Conversación"), ("nucleo", "Órdenes"), ("codigo", "Código"))), self.prefs),
                "voces": Biblioteca(Adaptador("voces", "Voces", "vozSalida", (("principal", "Voz"),),
                                              probar_ok=self.voz_ok), self.prefs)}
        return DirectorCentro(
            self.prefs, self.estado, bibs, capacidades=lambda: None, aceptacion=lambda: None,
            ahora=lambda: "2026-11-24T00:00:00+00:00", catalogo=lambda: CATALOGO,
            claves=SeccionClaves(lambda: self.claves, lambda: Path(self.tmp.name) / "x.json") if con_claves else None,
            equipo=lambda: {"perfil": "standard"}, al_cambiar_asignaciones=self.contar)

    def contar(self):
        self.cambios += 1


class TestPresets(Base):
    def asignacion(self, destino, funcion):
        return self.prefs.obtener(f"asignaciones.{destino}.{funcion}")

    def test_hay_cuatro_presets_y_ninguno_de_solo_texto(self):
        self.assertEqual([p.id for p in presets.PRESETS], ["local", "nube", "hibrido_local", "hibrido_nube"])

    def test_sin_nada_configurado_ninguno_es_aplicable_y_dice_que_falta(self):
        for p in presets.evaluar(self.prefs, CATALOGO):
            self.assertFalse(p["aplicable"], p["id"])
            self.assertTrue(p["faltan"], p["id"])

    def test_local_reparte_los_modelos_por_rol(self):
        self.poner([local("l1", "chat:4b", "chat"), local("l2", "orden:7b", "nucleus"), local("l3", "cod:7b", "coder")],
                   [{"id": "v1", "origen": "sistema", "voz": "Helena"}])
        presets.aplicar(self.prefs, "local", CATALOGO, False, "t")
        self.assertEqual(self.asignacion("pensamiento", "chat"), {"politica": "solo_local", "cadena": ["l1"]})
        self.assertEqual(self.asignacion("pensamiento", "nucleo")["cadena"], ["l2"])
        self.assertEqual(self.asignacion("pensamiento", "codigo")["cadena"], ["l3"])
        self.assertEqual(self.asignacion("vozSalida", "principal"), {"politica": "solo_local", "cadena": ["v1"]})

    def test_el_rol_se_deduce_del_catalogo_si_el_recurso_no_lo_trae(self):
        self.poner([local("l1", "chat:4b"), local("l2", "orden:7b")])
        presets.aplicar(self.prefs, "local", CATALOGO, False, "t")
        self.assertEqual(self.asignacion("pensamiento", "chat")["cadena"], ["l1"])
        self.assertEqual(self.asignacion("pensamiento", "nucleo")["cadena"], ["l2"])

    def test_con_un_solo_modelo_local_se_usa_para_todas_las_funciones(self):
        self.poner([local("l1", "propio:1b")])
        presets.aplicar(self.prefs, "local", CATALOGO, False, "t")
        for f in ("chat", "nucleo", "codigo"):
            self.assertEqual(self.asignacion("pensamiento", f)["cadena"], ["l1"])

    def test_solo_nube_ignora_lo_local(self):
        self.poner([local("l1", "chat:4b", "chat"), nube("n1")])
        presets.aplicar(self.prefs, "nube", CATALOGO, True, "t")
        self.assertEqual(self.asignacion("pensamiento", "chat"), {"politica": "solo_nube", "cadena": ["n1"]})

    def test_hibrido_ordena_segun_la_politica(self):
        self.poner([local("l1", "chat:4b", "chat"), nube("n1")])
        presets.aplicar(self.prefs, "hibrido_local", CATALOGO, True, "t")
        self.assertEqual(self.asignacion("pensamiento", "chat"), {"politica": "local_primero", "cadena": ["l1", "n1"]})
        presets.aplicar(self.prefs, "hibrido_nube", CATALOGO, True, "t")
        self.assertEqual(self.asignacion("pensamiento", "chat"), {"politica": "nube_primero", "cadena": ["n1", "l1"]})

    def test_un_preset_no_toca_la_funcion_a_la_que_le_falta_algo(self):
        self.poner([local("l1", "chat:4b", "chat")])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_local", "cadena": ["l1"]})
        self.poner([local("l1", "chat:4b", "chat")], [])
        plan = presets.evaluar(self.prefs, CATALOGO)
        nube_ = next(p for p in plan if p["id"] == "nube")
        self.assertFalse(nube_["aplicable"])
        self.assertEqual(self.asignacion("pensamiento", "chat")["cadena"], ["l1"])  # evaluar no escribe

    def test_aplicar_algo_imposible_falla_sin_escribir(self):
        self.poner([local("l1", "chat:4b", "chat")])
        with self.assertRaises(presets.ErrorPreset):
            presets.aplicar(self.prefs, "nube", CATALOGO, True, "t")
        self.assertIsNone(self.asignacion("pensamiento", "chat"))

    def test_un_preset_con_nube_exige_consentimiento_si_no_se_dio_antes(self):
        self.poner([nube("n1")])
        with self.assertRaises(presets.ErrorPreset) as ctx:
            presets.aplicar(self.prefs, "nube", CATALOGO, False, "t")
        self.assertIn("consentimiento", ctx.exception.mensaje)
        self.assertIsNone(self.asignacion("pensamiento", "chat"))
        presets.aplicar(self.prefs, "nube", CATALOGO, True, "2026-11-24")
        self.assertEqual(self.prefs.obtener("ajustes.avisoNubeAceptado"), "2026-11-24")

    def test_si_el_aviso_ya_se_acepto_al_agregar_el_modelo_no_se_vuelve_a_pedir(self):
        self.poner([nube("n1")])
        self.prefs.establecer("ajustes.avisoNubeAceptado", "antes")
        presets.aplicar(self.prefs, "nube", CATALOGO, False, "t")
        self.assertEqual(self.prefs.obtener("ajustes.avisoNubeAceptado"), "antes")

    def test_un_preset_local_no_pide_consentimiento_de_nube(self):
        self.poner([local("l1", "chat:4b", "chat")])
        presets.aplicar(self.prefs, "local", CATALOGO, False, "t")
        self.assertIsNone(self.prefs.obtener("ajustes.avisoNubeAceptado"))

    def test_hibrido_con_un_solo_lado_avisa_que_no_hay_respaldo(self):
        self.poner([local("l1", "chat:4b", "chat")])
        p = next(x for x in presets.evaluar(self.prefs, CATALOGO) if x["id"] == "hibrido_local")
        self.assertTrue(p["aplicable"])
        self.assertTrue(any("respaldo" in a for a in p["avisos"]))

    def test_preset_inexistente(self):
        with self.assertRaises(presets.ErrorPreset):
            presets.aplicar(self.prefs, "magico", CATALOGO, True, "t")


class TestRecorrido(Base):
    def abrir(self, **kw):
        d = self.director(**kw)
        d.abrir_primer_arranque()
        return d

    def paso(self, d, accion):
        return d.operar("paso", {"accion": accion})

    def pantalla(self, d):
        return d.datos()["primerArranque"]

    def llegar_a_ruta(self, d):
        self.paso(d, "siguiente")
        self.paso(d, "siguiente")
        self.assertEqual(self.pantalla(d)["paso"], "ruta")

    def test_los_pasos_fijos_son_cinco(self):
        d = self.abrir()
        self.assertEqual([p["id"] for p in self.pantalla(d)["pasos"]], ["bienvenida", "equipo", "ruta", "prueba", "resumen"])
        self.assertEqual(self.pantalla(d)["total"], 5)

    def test_el_paso_equipo_trae_lo_que_describe_el_equipo(self):
        d = self.abrir()
        self.paso(d, "siguiente")
        self.assertEqual(self.pantalla(d)["paso"], "equipo")
        self.assertEqual(self.pantalla(d)["equipo"], {"perfil": "standard"})
        self.paso(d, "siguiente")
        self.assertIsNone(self.pantalla(d)["equipo"])

    def test_la_ruta_rapida_ofrece_presets_y_la_personalizada_no(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        self.assertIsNone(self.pantalla(d)["presets"])  # aún no eligió
        d.operar("ruta_elegir", {"ruta": "rapida"})
        self.assertEqual([p["id"] for p in self.pantalla(d)["presets"]], ["local", "nube", "hibrido_local", "hibrido_nube"])
        d.operar("ruta_elegir", {"ruta": "personalizada"})
        self.assertIsNone(self.pantalla(d)["presets"])

    def test_ruta_invalida(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        self.assertFalse(d.operar("ruta_elegir", {"ruta": "magica"})["ok"])

    def test_no_se_puede_seguir_sin_elegir_ruta_pero_si_omitir(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        r = self.paso(d, "siguiente")
        self.assertFalse(r["ok"])
        self.assertEqual(self.pantalla(d)["paso"], "ruta")
        self.assertTrue(self.paso(d, "omitir")["ok"])
        self.assertEqual(self.pantalla(d)["paso"], "prueba")
        self.assertEqual(self.estado.estado_de("ruta"), "omitido")

    def test_la_ruta_personalizada_visita_cada_menu_con_su_guia(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        d.operar("ruta_elegir", {"ruta": "personalizada"})
        self.assertEqual(self.pantalla(d)["total"], 5 + 3)
        vistas = []
        self.paso(d, "siguiente")
        while self.pantalla(d)["paso"] == "ruta":
            carga = d.datos()
            vistas.append(carga["seccion"])
            guia = next(s["guia"] for s in carga["secciones"] if s["id"] == carga["seccion"])
            self.assertTrue(guia, carga["seccion"])  # D.A.R.K. explica cada menú
            self.paso(d, "siguiente")
        self.assertEqual(vistas, ["claves", "bib:modelosPensamiento", "bib:voces"])
        self.assertEqual(self.pantalla(d)["paso"], "prueba")
        self.assertEqual(self.estado.estado_de("ruta"), "hecho")

    def test_cada_menu_guiado_trae_los_datos_de_su_seccion(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        d.operar("ruta_elegir", {"ruta": "personalizada"})
        self.paso(d, "siguiente")
        self.assertIsNotNone(d.datos()["claves"])
        self.paso(d, "siguiente")
        self.assertEqual(d.datos()["biblioteca"]["tipo"], "modelosPensamiento")
        self.paso(d, "siguiente")
        self.assertEqual(d.datos()["biblioteca"]["tipo"], "voces")

    def test_la_personalizada_se_adapta_a_lo_que_existe(self):
        d = self.abrir(con_claves=False)
        self.llegar_a_ruta(d)
        d.operar("ruta_elegir", {"ruta": "personalizada"})
        self.assertEqual(self.pantalla(d)["total"], 5 + 2)

    def test_anterior_desde_una_seccion_vuelve_y_omitir_la_ruta_salta_sus_menus(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        d.operar("ruta_elegir", {"ruta": "personalizada"})
        self.paso(d, "siguiente")
        self.paso(d, "anterior")
        self.assertIsNone(self.pantalla(d)["pantalla"].get("seccion"))
        self.paso(d, "omitir")
        self.assertEqual(self.pantalla(d)["paso"], "prueba")

    def test_aplicar_un_preset_avisa_y_notifica_al_nucleo(self):
        self.poner([local("l1", "chat:4b", "chat")])
        d = self.abrir()
        self.llegar_a_ruta(d)
        d.operar("ruta_elegir", {"ruta": "rapida"})
        r = d.operar("preset_aplicar", {"preset": "local"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.cambios, 1)  # el Núcleo debe ajustar su voz y repintar
        self.assertIn("aplicado", d.datos()["aviso"]["mensaje"])
        self.assertIn("Voz: falta", d.datos()["aviso"]["mensaje"])  # lo que faltó se dice
        self.assertEqual(self.prefs.obtener("asignaciones.pensamiento.chat")["cadena"], ["l1"])

    def test_preset_imposible_es_un_aviso_de_error_y_no_notifica(self):
        d = self.abrir()
        self.llegar_a_ruta(d)
        r = d.operar("preset_aplicar", {"preset": "nube", "aceptado": True})
        self.assertFalse(r["ok"])
        self.assertEqual(self.cambios, 0)

    def test_preset_con_nube_sin_consentimiento_es_un_error(self):
        self.poner([nube("n1")])
        d = self.abrir()
        self.llegar_a_ruta(d)
        self.assertFalse(d.operar("preset_aplicar", {"preset": "nube"})["ok"])
        self.assertTrue(d.operar("preset_aplicar", {"preset": "nube", "aceptado": True})["ok"])


class TestPrueba(Base):
    def ir_a_prueba(self, d):
        d.abrir_primer_arranque()
        d.operar("paso", {"accion": "siguiente"})
        d.operar("paso", {"accion": "siguiente"})
        d.operar("ruta_elegir", {"ruta": "rapida"})
        d.operar("paso", {"accion": "siguiente"})
        self.assertEqual(d.datos()["primerArranque"]["paso"], "prueba")

    def configurar_voz(self):
        self.poner([local("l1", "chat:4b", "chat")], [{"id": "v1", "nombre": "Helena", "origen": "sistema", "voz": "Helena"}])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_local", "cadena": ["l1"]})
        self.prefs.establecer_asignacion("vozSalida", "principal", {"politica": "local_primero", "cadena": ["v1"]})

    def test_sin_nada_asignado_no_hay_nada_que_probar_y_se_puede_seguir(self):
        d = self.director()
        self.ir_a_prueba(d)
        self.assertEqual(d.datos()["primerArranque"]["prueba"], {"items": [], "vozPendiente": False})
        self.assertTrue(d.operar("paso", {"accion": "siguiente"})["ok"])

    def test_lista_lo_asignado_con_su_estado(self):
        self.configurar_voz()
        d = self.director()
        self.ir_a_prueba(d)
        prueba = d.datos()["primerArranque"]["prueba"]
        self.assertEqual([(i["tipo"], i["estado"]) for i in prueba["items"]],
                         [("modelosPensamiento", "sin_probar"), ("voces", "sin_probar")])
        self.assertTrue(prueba["vozPendiente"])

    def test_no_se_termina_sin_probar_la_voz_elegida(self):
        self.configurar_voz()
        d = self.director()
        self.ir_a_prueba(d)
        r = d.operar("paso", {"accion": "siguiente"})
        self.assertFalse(r["ok"])
        self.assertIn("pruebe la voz", r["error"])
        self.assertEqual(d.datos()["primerArranque"]["paso"], "prueba")

    def test_probar_la_voz_destraba_el_paso(self):
        self.configurar_voz()
        d = self.director()
        self.ir_a_prueba(d)
        d.operar("bib_probar", {"tipo": "voces", "recurso": "v1"})
        prueba = d.datos()["primerArranque"]["prueba"]
        self.assertEqual([i["estado"] for i in prueba["items"]], ["sin_probar", "ok"])
        self.assertFalse(prueba["vozPendiente"])
        self.assertTrue(d.operar("paso", {"accion": "siguiente"})["ok"])
        self.assertEqual(self.estado.estado_de("prueba"), "hecho")

    def test_una_voz_que_falla_sigue_pendiente_y_muestra_el_motivo(self):
        self.configurar_voz()
        self.voz_ok = False
        d = self.director()
        self.ir_a_prueba(d)
        d.operar("bib_probar", {"tipo": "voces", "recurso": "v1"})
        prueba = d.datos()["primerArranque"]["prueba"]
        self.assertEqual(prueba["items"][1]["estado"], "fallo")
        self.assertEqual(prueba["items"][1]["mensaje"], "Falló")
        self.assertTrue(prueba["vozPendiente"])
        self.assertFalse(d.operar("paso", {"accion": "siguiente"})["ok"])

    def test_se_puede_omitir_el_paso_aunque_la_voz_no_se_probara(self):
        self.configurar_voz()
        d = self.director()
        self.ir_a_prueba(d)
        self.assertTrue(d.operar("paso", {"accion": "omitir"})["ok"])
        self.assertEqual(self.estado.estado_de("prueba"), "omitido")

    def test_probar_el_modelo_no_es_obligatorio(self):
        self.poner([local("l1", "chat:4b", "chat")])
        self.prefs.establecer_asignacion("pensamiento", "chat", {"politica": "solo_local", "cadena": ["l1"]})
        d = self.director()
        self.ir_a_prueba(d)
        self.assertTrue(d.operar("paso", {"accion": "siguiente"})["ok"])


class TestEquipo(unittest.TestCase):
    class Cliente:
        def __init__(self, modelos=None, falla=False):
            self.modelos, self.falla, self.llamadas = modelos or [], falla, 0

        def instalados(self):
            self.llamadas += 1
            if self.falla:
                raise ErrorOllama("no")
            return {m: {"digest": "x", "size": 1} for m in self.modelos}

    def descriptor(self, cliente, reloj, ram=16 * GIB):
        return DescriptorEquipo(cliente, reloj=lambda: reloj[0], ram=lambda: ram, libre=lambda: 50 * GIB)

    def test_describe_ram_espacio_perfil_y_ollama(self):
        d = self.descriptor(self.Cliente(["b:1", "a:1"]), [0.0]).describir()
        self.assertEqual((d["perfil"], d["ramTexto"], d["libreTexto"]), ("standard", "16.0 GB", "50.0 GB"))
        self.assertEqual(d["ollama"], {"responde": True, "modelos": ["a:1", "b:1"]})
        self.assertIn("recomendación", d["nota"])
        self.assertEqual(d["vram"], "no se mide")  # no se inventa lo que no se mide

    def test_sin_ollama(self):
        self.assertEqual(self.descriptor(self.Cliente(falla=True), [0.0]).describir()["ollama"],
                         {"responde": False, "modelos": []})

    def test_ram_desconocida_cae_al_perfil_minimo_y_lo_dice(self):
        d = self.descriptor(self.Cliente(), [0.0], ram=None).describir()
        self.assertEqual((d["perfil"], d["ramTexto"]), ("limited", "no se pudo medir"))

    def test_no_consulta_a_ollama_en_cada_repintado(self):
        c, reloj = self.Cliente(), [0.0]
        d = self.descriptor(c, reloj)
        d.describir()
        d.describir()
        self.assertEqual(c.llamadas, 1)
        reloj[0] = 10.0
        d.describir()
        self.assertEqual(c.llamadas, 2)


if __name__ == "__main__":
    unittest.main()
