"""P9: voz de entrada (palabra de activación como ajuste), voz local de Piper y el paquete de voz «no incluido»."""
import ast
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from centro import AdaptadorVoces, Biblioteca, ErrorBiblioteca, Preferencias, ResultadoPrueba, SeccionVozEntrada
from centro.secciones import ErrorSeccion
from centro.voz_entrada import UMBRAL_POR_DEFECTO, palabra_activa, umbral_guardado
from credenciales import AlmacenMemoria, ServicioClaves
from voz.tts_cadena import TtsPorCadena

DARK_PYTHON = Path(__file__).resolve().parents[1] / "dark_python"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefs = Preferencias(Path(self.tmp.name) / "p.json")


class TestAjustes(Base):
    def test_valores_por_defecto(self):
        self.assertTrue(palabra_activa(self.prefs))
        self.assertEqual(umbral_guardado(self.prefs), UMBRAL_POR_DEFECTO)

    def test_lo_guardado_se_lee_y_lo_invalido_cae_al_defecto(self):
        self.prefs.establecer("ajustes.palabraActivacion", {"activa": False, "sensibilidad": 0.65})
        self.assertFalse(palabra_activa(self.prefs))
        self.assertEqual(umbral_guardado(self.prefs), 0.65)
        for malo in (True, "0.9", None, 0.1, 5, -1):
            self.prefs.establecer("ajustes.palabraActivacion", {"activa": True, "sensibilidad": malo})
            self.assertEqual(umbral_guardado(self.prefs), UMBRAL_POR_DEFECTO, repr(malo))

    def test_unas_preferencias_rotas_no_rompen_el_arranque_del_microfono(self):
        class Rotas:
            def obtener(self, *_a, **_k):
                raise ValueError("roto")
        self.assertTrue(palabra_activa(Rotas()))
        self.assertEqual(umbral_guardado(Rotas()), UMBRAL_POR_DEFECTO)
        self.assertTrue(palabra_activa(None))
        self.assertEqual(umbral_guardado(None), UMBRAL_POR_DEFECTO)


class TestSeccionVozEntrada(Base):
    def seccion(self, modulos=(), modelo="small"):
        return SeccionVozEntrada(self.prefs, lambda n: n in modulos, lambda: modelo)

    def textos(self, b):
        return " ".join(x.get("texto", "") for x in b if x["tipo"] == "parrafo")

    def test_sin_paquete_lo_dice_con_franqueza_y_lista_lo_que_falta(self):
        b = self.seccion().bloques()
        self.assertIn("le falta algo", self.textos(b))
        faltan = next(x for x in b if x["tipo"] == "tabla" and x["titulo"].startswith("Qué falta"))
        self.assertEqual(len(faltan["filas"]), 2)
        self.assertTrue(all(f[1] == "no incluido" for f in faltan["filas"]))

    def test_con_lo_esencial_no_finge_que_falta(self):
        b = self.seccion(modulos={"openwakeword", "pyaudio"}).bloques()
        self.assertNotIn("le falta algo", self.textos(b))
        self.assertIn("Tengo lo necesario", self.textos(b))
        self.assertFalse(any(x["tipo"] == "tabla" and x["titulo"].startswith("Qué falta") for x in b))

    def test_un_componente_parcial_cuenta_como_no_incluido(self):
        b = self.seccion(modulos={"openwakeword"}).bloques()
        faltan = next(x for x in b if x["tipo"] == "tabla" and x["titulo"].startswith("Qué falta"))
        self.assertEqual([f[0] for f in faltan["filas"]], ["micrófono"])

    def test_arranca_con_windows_y_no_ofrece_whisper_si_no_esta_incluido(self):
        b = self.seccion().bloques()
        tabla = next(x for x in b if x["tipo"] == "tabla" and x["titulo"] == "Reconocimiento de voz")
        filas = dict(tabla["filas"])
        self.assertEqual(filas["Lo que entiendo con"], "Reconocedor de Windows")
        self.assertIn("no está incluido", filas["Whisper (opcional)"])
        lista = next(x for x in b if x["tipo"] == "lista")
        self.assertEqual([i["titulo"] for i in lista["items"]], ["✓ Reconocedor de Windows"])

    def test_no_ofrece_lo_que_no_puede_hacer(self):
        etiquetas = [a["etiqueta"] for x in self.seccion().bloques() for a in x.get("acciones", [])]
        self.assertTrue(all("ensibilidad" in e or "Estricta" in e or "Equilibrada" in e or "Sensible" in e
                            for e in etiquetas), etiquetas)  # nada de «Probar» ni «Elegir micrófono»

    def test_el_interruptor_guarda_la_preferencia(self):
        s = self.seccion()
        interruptor = next(x for x in s.bloques() if x["tipo"] == "interruptor")
        self.assertTrue(interruptor["valor"])
        mensaje = s.operar("vozentrada_activar", {"activa": False})
        self.assertFalse(palabra_activa(self.prefs))
        self.assertIn("reabrir", mensaje)
        self.assertEqual(self.prefs.obtener("ajustes.palabraActivacion")["sensibilidad"], UMBRAL_POR_DEFECTO)  # no pisa lo otro
        for malo in (None, "no", 0):
            with self.assertRaises(ErrorSeccion):
                s.operar("vozentrada_activar", {"activa": malo})

    def test_la_sensibilidad_marca_la_vigente_y_solo_acepta_los_tres_niveles(self):
        s = self.seccion()

        def marcada():
            botones = next(x for x in s.bloques() if x["tipo"] == "acciones")["acciones"]
            return [b["datos"]["valor"] for b in botones if b["etiqueta"].startswith("✓")]
        self.assertEqual(marcada(), [0.8])
        s.operar("vozentrada_activar", {"activa": False})  # un valor distinto del de por defecto
        s.operar("vozentrada_sensibilidad", {"valor": 0.65})
        self.assertEqual(marcada(), [0.65])
        self.assertFalse(palabra_activa(self.prefs))  # cambiar la sensibilidad no pisa el interruptor
        self.assertEqual(self.prefs.obtener("ajustes.palabraActivacion")["activa"], False)
        for malo in (0.7, 0.1, 1.5, "0.9", None, True):
            with self.assertRaises(ErrorSeccion, msg=repr(malo)):
                s.operar("vozentrada_sensibilidad", {"valor": malo})
        self.assertEqual(umbral_guardado(self.prefs), 0.65)

    def test_avisa_de_que_los_cambios_se_aplican_al_reabrir(self):
        self.assertIn("próxima vez", self.textos(self.seccion().bloques()))

    def test_operacion_desconocida(self):
        with self.assertRaises(ErrorSeccion):
            self.seccion().operar("vozentrada_probar", {})


class TestNucleoUsaLosAjustes(unittest.TestCase):
    """El Núcleo no se puede ejecutar aquí (necesita micrófono): se vigila por AST que use los ajustes."""

    @classmethod
    def setUpClass(cls):
        cls.arbol = ast.parse((DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8"))

    def test_todo_detector_de_activacion_recibe_el_umbral_elegido(self):
        llamadas = [n for n in ast.walk(self.arbol) if isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") == "WakeWordDetector"]
        self.assertGreaterEqual(len(llamadas), 2)
        for llamada in llamadas:
            self.assertEqual([k.arg for k in llamada.keywords], ["threshold"], f"línea {llamada.lineno}")

    def test_la_activacion_apagada_se_comprueba_antes_de_crear_el_detector(self):
        fuente = (DARK_PYTHON / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8")
        self.assertLess(fuente.index("if not palabra_activa(ajustes_prefs):"), fuente.index("detector = None\n"
                        "            if VOZ_DISPONIBLE and voz_api.config.MIC_PERSISTENTE:"))


# ------------------------------------------------------------------ voz local
class TestVozPiper(Base):
    VOZ = "es_ES-davefx-medium"

    def biblioteca(self, disponible=True, probar=None):
        piper = lambda: {"voz": self.VOZ, "disponible": disponible}
        adaptador = AdaptadorVoces(lambda: ServicioClaves(AlmacenMemoria()), piper=piper,
                                   probar_piper=probar or (lambda frase: ResultadoPrueba(True, f"Sonó «{frase}»")))
        adaptador._windows.listar = lambda: []
        return Biblioteca(adaptador, self.prefs)

    def origen(self, b):
        return next(o for o in b.descripcion()["origenes"] if o["id"] == "piper")

    def test_con_el_paquete_ofrece_la_voz_instalada(self):
        self.assertEqual(self.origen(self.biblioteca())["campos"][0]["opciones"], [self.VOZ])

    def test_sin_el_paquete_lo_dice_y_no_deja_agregar(self):
        b = self.biblioteca(disponible=False)
        campo = self.origen(b)["campos"][0]
        self.assertEqual(campo["opciones"], [])
        self.assertIn("no está incluido", campo["ayuda"])
        with self.assertRaises(ErrorBiblioteca) as ctx:
            b.revisar("piper", {"voz": self.VOZ})
        self.assertIn("no está incluido", str(ctx.exception))

    def test_solo_se_puede_agregar_la_voz_que_esta_instalada(self):
        with self.assertRaises(ErrorBiblioteca):
            self.biblioteca().revisar("piper", {"voz": "es_ES-sharvard-medium"})

    def test_la_revision_muestra_licencia_y_que_no_sale_nada(self):
        r = self.biblioteca().revisar("piper", {"voz": self.VOZ})
        self.assertIn("CC0", r.licencia)
        self.assertEqual(r.consentimientos, [])
        self.assertIn("no sale nada", r.lineas[0])

    def test_agregarla_no_dice_que_esta_lista_hasta_probarla(self):
        b = self.biblioteca()
        t = b.esperar(b.agregar("piper", {"voz": self.VOZ}, aceptado=False).id)
        self.assertEqual(t.estado, "ok")
        recurso = b.listar()[0]
        self.assertEqual((recurso["id"], recurso["origen"], recurso["lista"]), (f"voz:piper:{self.VOZ}", "piper", False))

    def test_probar_hace_sonar_la_voz_por_el_servidor(self):
        b = self.biblioteca()
        b.esperar(b.agregar("piper", {"voz": self.VOZ}, aceptado=False).id)
        self.assertTrue(b.probar(f"voz:piper:{self.VOZ}").ok)

    def test_probar_sin_el_servidor_no_miente(self):
        b = self.biblioteca()
        b.esperar(b.agregar("piper", {"voz": self.VOZ}, aceptado=False).id)
        b._adaptador = b.adaptador
        b.adaptador._piper = lambda: {"voz": self.VOZ, "disponible": False}
        r = b.probar(f"voz:piper:{self.VOZ}")
        self.assertFalse(r.ok)
        self.assertIn("no está activa", r.mensaje)


class TestCadenaConPiper(Base):
    class Base_:
        def __init__(self):
            self.dichos = []

        def hablar(self, texto, parar=None, al_pcm=None, solo_pcm=False):
            self.dichos.append(texto)
            return {"ok": True, "motor": "piper-base"}

        def cortar(self):
            pass
        disponible, hablando, sonando, estado, nivel_salida = True, False, False, "x", 0.0

    def tts(self, base):
        return TtsPorCadena(base, lambda: self.prefs, lambda c: "", lambda: None, log=lambda *_: None)

    def configurar(self, politica="local_primero"):
        self.prefs.reemplazar_biblioteca("voces", [{"id": "v", "origen": "piper", "voz": "es_ES-davefx-medium"}])
        self.prefs.establecer_asignacion("vozSalida", "principal", {"politica": politica, "cadena": ["v"]})

    def test_la_voz_de_piper_habla_por_el_tts_de_base(self):
        self.configurar()
        base = self.Base_()
        r = self.tts(base).hablar("Hola")
        self.assertTrue(r["ok"])
        self.assertEqual(base.dichos, ["Hola"])

    def test_sin_servidor_de_voz_la_voz_de_piper_no_cuenta_como_candidato(self):
        self.configurar()
        self.assertFalse(self.tts(None).hay_cadena())

    def test_solo_nube_no_usa_piper(self):
        self.configurar("solo_nube")
        base = self.Base_()
        self.tts(base).hablar("Hola")
        self.assertEqual(base.dichos, [])  # y «solo nube» tampoco cae a la base

    def test_la_capacidad_refleja_la_voz_local_elegida(self):
        from capacidades.sondas import SondasReales
        from proveedores.llm import cadena
        self.configurar()
        cadena.fijar_preferencias(self.prefs)
        self.addCleanup(cadena.fijar_preferencias, None)
        self.assertEqual(SondasReales().voz_elegida(), ("local", "es_ES-davefx-medium"))


if __name__ == "__main__":
    unittest.main()
