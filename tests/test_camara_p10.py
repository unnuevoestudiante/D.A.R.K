"""P10: personas registradas (acceso por rostro), reglas y sección «Cámara y biometría»."""
import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "dark_python"))

import numpy as np

from acceso import biometria
from centro import Preferencias, SeccionCamara
from centro.camara import AUSENCIAS, FRASE_ELIMINAR_TODO, UMBRALES, ajustes_acceso
from centro.secciones import ErrorSeccion


def vector(semilla=1):
    v = np.random.default_rng(semilla).normal(size=biometria.DIMENSION_VECTOR).astype("float32")
    return v / np.linalg.norm(v)


class ConDatosTemporales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"DARK_USER_DATA_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)


# ---------------------------------------------------------------- biometría real
class TestBiometriaPersonas(ConDatosTemporales):
    def registrar(self, nombre, semilla, muestras=12):
        base = {}
        try:
            base = biometria.cargar_base()
        except (FileNotFoundError, biometria.ErrorBiometria):
            pass
        base[nombre] = vector(semilla)
        biometria.guardar_base(base)
        biometria._registrar_persona(nombre, muestras)

    def test_los_metadatos_van_cifrados_y_sin_el_nombre_en_claro(self):
        self.registrar("Ana Gómez", 1)
        contenido = biometria.ruta_personas().read_bytes()
        self.assertTrue(contenido.startswith(b"DPA1"))
        self.assertNotIn("Ana".encode(), contenido)
        self.assertEqual([p["nombre"] for p in biometria.leer_personas()], ["Ana Gómez"])

    def test_una_persona_nueva_empieza_con_el_acceso_activo_y_conserva_su_estado_al_volver_a_capturar(self):
        self.registrar("Ana", 1, muestras=10)
        biometria.poner_activa("Ana", False)
        self.registrar("Ana", 2, muestras=12)  # volver a capturar
        ana = biometria.leer_personas()[0]
        self.assertEqual((ana["muestras"], ana["activa"]), (12, False))  # no reactiva el acceso por sorpresa

    def test_desactivar_a_todos_apaga_la_puerta_facial_sin_borrar_nada(self):
        biometria.registrar_consentimiento()
        self.registrar("Ana", 1)
        self.assertTrue(biometria.facial_habilitado())
        biometria.poner_activa("Ana", False)
        self.assertFalse(biometria.facial_habilitado())
        self.assertTrue(biometria.ruta_base().is_file())  # los datos siguen ahí
        biometria.poner_activa("Ana", True)
        self.assertTrue(biometria.facial_habilitado())

    def test_con_una_activa_basta(self):
        biometria.registrar_consentimiento()
        self.registrar("Ana", 1)
        self.registrar("Beto", 2)
        biometria.poner_activa("Ana", False)
        self.assertTrue(biometria.facial_habilitado())

    def test_la_puerta_solo_carga_a_las_personas_activas(self):
        self.registrar("Ana", 1)
        self.registrar("Beto", 2)
        biometria.poner_activa("Ana", False)
        self.assertEqual(sorted(biometria.cargar_base()), ["Ana", "Beto"])  # la base completa sigue completa
        self.assertEqual(list(biometria.cargar_base(solo_activas=True)), ["Beto"])

    def test_sin_ninguna_activa_la_puerta_no_se_levanta_con_un_error_claro(self):
        self.registrar("Ana", 1)
        biometria.poner_activa("Ana", False)
        with self.assertRaises(biometria.ErrorBiometria):
            biometria.cargar_base(solo_activas=True)

    def test_un_registro_anterior_sin_metadatos_sigue_funcionando_y_se_sincroniza(self):
        biometria.registrar_consentimiento()
        biometria.guardar_base({"Vieja": vector(3)})  # sin personas.bin
        self.assertTrue(biometria.facial_habilitado())
        self.assertEqual(biometria.leer_personas(), [])
        personas = biometria.sincronizar_personas()
        self.assertEqual([(p["nombre"], p["activa"]) for p in personas], [("Vieja", True)])
        self.assertEqual(len(biometria.leer_personas()), 1)

    def test_borrar_una_persona_deja_a_las_demas(self):
        self.registrar("Ana", 1)
        self.registrar("Beto", 2)
        self.assertTrue(biometria.borrar_persona("Ana"))
        self.assertEqual(list(biometria.cargar_base()), ["Beto"])
        self.assertEqual([p["nombre"] for p in biometria.leer_personas()], ["Beto"])
        self.assertFalse(biometria.borrar_persona("Ana"))

    def test_borrar_a_la_ultima_borra_todo_el_registro(self):
        biometria.registrar_consentimiento()
        self.registrar("Ana", 1)
        self.assertTrue(biometria.borrar_persona("Ana"))
        self.assertFalse(biometria.ruta_base().exists())
        self.assertFalse(biometria.ruta_personas().exists())
        self.assertFalse(biometria.tiene_consentimiento())

    def test_borrar_el_registro_borra_tambien_los_metadatos(self):
        self.registrar("Ana", 1)
        biometria.borrar_registro()
        self.assertFalse(biometria.ruta_personas().exists())

    def test_metadatos_corruptos_cuentan_como_ausentes_y_no_apagan_el_acceso(self):
        biometria.registrar_consentimiento()
        biometria.guardar_base({"Ana": vector(1)})
        biometria.ruta_personas().write_bytes(b"DPA1basura")
        self.assertEqual(biometria.leer_personas(), [])
        self.assertTrue(biometria.facial_habilitado())

    def test_poner_activa_a_alguien_inexistente(self):
        self.assertFalse(biometria.poner_activa("Nadie", False))


# ---------------------------------------------------------------- la sección
class BioFalsa:
    def __init__(self, personas=(), consentimiento=True, falla_registro=None):
        self.personas = [dict(p) for p in personas]
        self.consentimiento, self.falla = consentimiento, falla_registro
        self.llamadas = []

    def tiene_consentimiento(self):
        return self.consentimiento

    def leer_personas(self):
        return [dict(p) for p in self.personas]

    sincronizar_personas = leer_personas

    def poner_activa(self, nombre, activa):
        for p in self.personas:
            if p["nombre"] == nombre:
                p["activa"] = activa
                return True
        return False

    def borrar_persona(self, nombre):
        antes = len(self.personas)
        self.personas = [p for p in self.personas if p["nombre"] != nombre]
        return len(self.personas) < antes

    def registrar_consentimiento(self):
        self.llamadas.append("consentimiento")
        self.consentimiento = True

    def registrar_rostro(self, nombre, servicio=None):
        self.llamadas.append(("registrar", nombre, servicio))
        if self.falla:
            raise self.falla
        self.personas.append({"nombre": nombre, "creadoEn": "2026-11-24T00:00:00+00:00", "muestras": 12, "activa": True})
        return 12

    class ErrorBiometria(Exception):
        pass


ANA = {"nombre": "Ana", "creadoEn": "2026-11-20T10:00:00+00:00", "muestras": 12, "activa": True}


class TestSeccionCamara(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.prefs = Preferencias(pathlib.Path(self.tmp.name) / "p.json")
        self.cambios = self.borrados_todo = 0

    def seccion(self, bio=None, modulos=("cv2", "mediapipe", "numpy")):
        self.bio = bio or BioFalsa([ANA])
        self.tareas = []

        def al_borrar():
            self.borrados_todo += 1
            self.bio.personas = []
        return SeccionCamara(self.prefs, self.bio, lambda n: n in modulos, camara=lambda: "CAMARA",
                             al_cambiar=lambda: setattr(self, "cambios", self.cambios + 1),
                             al_borrar_todo=al_borrar, hilo=self.tareas.append)

    def textos(self, s):
        return " ".join(b.get("texto", "") for b in s.bloques() if b["tipo"] == "parrafo")

    def etiquetas(self, s):
        out = []
        for b in s.bloques():
            out += [a["etiqueta"] for a in b.get("acciones", [])]
            for i in b.get("items", []):
                out += [a["etiqueta"] for a in i["acciones"]]
        return out

    def test_sin_el_paquete_de_vision_lo_dice_y_no_ofrece_registrar(self):
        s = self.seccion(modulos=())
        self.assertIn("no está incluido", self.textos(s))
        self.assertNotIn("Agregar persona", self.etiquetas(s))
        self.assertIn("Gestos de manos", self.textos(s))
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_agregar", {"nombre": "Ana", "confirmado": True})
        self.assertEqual(self.tareas, [])

    def test_lista_a_las_personas_con_su_estado(self):
        s = self.seccion()
        lista = next(b for b in s.bloques() if b["tipo"] == "lista")
        self.assertEqual(lista["items"][0]["titulo"], "Ana")
        self.assertIn("12 muestras", lista["items"][0]["detalle"])
        self.assertIn("acceso activo", lista["items"][0]["detalle"])
        self.assertIn("Personas registradas: 1", self.textos(s))

    def test_el_texto_de_consentimiento_dice_que_la_persona_debe_estar_presente_y_aceptar(self):
        s = self.seccion()
        agregar = next(a for b in s.bloques() for a in b.get("acciones", []) if a["etiqueta"] == "Agregar persona")
        self.assertIn("debe estar presente y aceptar", agregar["confirmar"])
        self.assertIn("no se guardan fotos", agregar["confirmar"])
        self.assertIn("Google", agregar["confirmar"])  # la descarga del modelo, declarada
        self.assertEqual(agregar["pideTexto"]["campo"], "nombre")

    def test_agregar_sin_consentimiento_no_captura_nada(self):
        s = self.seccion()
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_agregar", {"nombre": "Beto"})
        self.assertEqual((self.tareas, self.bio.llamadas), ([], []))

    def test_agregar_exige_nombre_y_lo_normaliza_y_acota(self):
        s = self.seccion()
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_agregar", {"nombre": "   ", "confirmado": True})
        s.operar("camara_agregar", {"nombre": "  Beto \n  Pérez  " + "x" * 80, "confirmado": True})
        self.tareas.pop()()
        nombre = self.bio.llamadas[-1][1]
        self.assertTrue(nombre.startswith("Beto Pérez x") and len(nombre) == 40)
        self.assertNotIn("\n", nombre)

    def test_la_captura_registra_consentimiento_primero_y_usa_la_camara_compartida(self):
        s = self.seccion()
        s.operar("camara_agregar", {"nombre": "Beto", "confirmado": True})
        self.assertIn("Mire a la cámara", self.textos(s))  # mientras captura
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_agregar", {"nombre": "Otra", "confirmado": True})  # una a la vez
        self.tareas.pop()()
        self.assertEqual(self.bio.llamadas, ["consentimiento", ("registrar", "Beto", "CAMARA")])
        self.assertIn("quedó registrada", self.textos(s))
        self.assertEqual(self.cambios, 1)  # el Núcleo repinta al terminar

    def test_un_fallo_de_captura_se_explica_y_no_filtra_trazas(self):
        s = self.seccion(bio=BioFalsa([ANA], falla_registro=RuntimeError("Traceback (most recent call last) c:\\secreto")))
        s.operar("camara_agregar", {"nombre": "Beto", "confirmado": True})
        self.tareas.pop()()
        texto = self.textos(s)
        self.assertIn("No se pudo registrar", texto)
        self.assertNotIn("secreto", texto)
        self.assertEqual([p["nombre"] for p in self.bio.personas], ["Ana"])

    def test_un_error_de_biometria_si_se_muestra_porque_es_legible(self):
        bio = BioFalsa([ANA])
        err = type("ErrorBiometria", (Exception,), {})("Solo se obtuvieron 3 capturas válidas.")
        bio.falla = err
        s = self.seccion(bio=bio)
        s.operar("camara_agregar", {"nombre": "Beto", "confirmado": True})
        self.tareas.pop()()
        self.assertIn("Solo se obtuvieron 3 capturas", self.textos(s))

    def test_activar_y_desactivar_sin_borrar(self):
        s = self.seccion()
        s.operar("camara_activa", {"nombre": "Ana", "activa": False})
        self.assertFalse(self.bio.personas[0]["activa"])
        self.assertIn("Activar acceso", self.etiquetas(s))
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_activa", {"nombre": "Nadie", "activa": False})
        for malo in ({"nombre": "Ana"}, {"nombre": 5, "activa": True}, {"nombre": "Ana", "activa": "si"}):
            with self.assertRaises(ErrorSeccion):
                s.operar("camara_activa", malo)

    def test_eliminar_una_persona_exige_confirmacion_en_el_nucleo(self):
        s = self.seccion()
        with self.assertRaises(ErrorSeccion):
            s.operar("camara_eliminar", {"nombre": "Ana"})
        self.assertEqual(len(self.bio.personas), 1)
        s.operar("camara_eliminar", {"nombre": "Ana", "confirmado": True})
        self.assertEqual(self.bio.personas, [])

    def test_sin_numpy_no_ofrece_eliminar_una_sola_persona(self):
        s = self.seccion(modulos=("cv2", "mediapipe"))
        self.assertNotIn("Eliminar", self.etiquetas(s))
        self.assertIn("Eliminar todo", self.etiquetas(s))  # eliminar todo no necesita numpy

    def test_eliminar_todo_exige_la_frase_exacta(self):
        s = self.seccion()
        for datos in ({}, {"confirmado": True}, {"confirmado": True, "frase": "eliminar"}, {"frase": FRASE_ELIMINAR_TODO}):
            with self.assertRaises(ErrorSeccion):
                s.operar("camara_eliminar_todo", datos)
        self.assertEqual(self.borrados_todo, 0)
        s.operar("camara_eliminar_todo", {"confirmado": True, "frase": FRASE_ELIMINAR_TODO})
        self.assertEqual(self.borrados_todo, 1)

    def test_reglas_por_defecto_marcadas_y_solo_valores_conocidos(self):
        s = self.seccion()
        marcadas = [a["datos"]["valor"] for b in s.bloques() for a in b.get("acciones", []) if a["etiqueta"].startswith("✓")]
        self.assertEqual(marcadas, [0.4, 7.0])
        s.operar("camara_umbral", {"valor": 0.5})
        s.operar("camara_ausencia", {"valor": 12.0})
        self.assertEqual(ajustes_acceso(self.prefs), {"umbral": 0.5, "ausenciaSeg": 12.0})
        for op in ("camara_umbral", "camara_ausencia"):
            for malo in (0.45, 99, "0.4", None, True):
                with self.assertRaises(ErrorSeccion, msg=f"{op} {malo!r}"):
                    s.operar(op, {"valor": malo})
        self.assertEqual(ajustes_acceso(self.prefs), {"umbral": 0.5, "ausenciaSeg": 12.0})  # nada cambió

    def test_cambiar_una_regla_no_pisa_la_otra(self):
        s = self.seccion()
        s.operar("camara_umbral", {"valor": 0.3})
        s.operar("camara_ausencia", {"valor": 4.0})
        self.assertEqual(ajustes_acceso(self.prefs), {"umbral": 0.3, "ausenciaSeg": 4.0})
        s.operar("camara_umbral", {"valor": 0.5})
        self.assertEqual(ajustes_acceso(self.prefs)["ausenciaSeg"], 4.0)

    def test_ajustes_invalidos_o_rotos_caen_a_los_de_siempre(self):
        self.assertEqual(ajustes_acceso(self.prefs), {"umbral": 0.4, "ausenciaSeg": 7.0})
        self.prefs.establecer("ajustes.accesoFacial", {"umbral": 0.01, "ausenciaSeg": "mucho"})
        self.assertEqual(ajustes_acceso(self.prefs), {"umbral": 0.4, "ausenciaSeg": 7.0})
        self.assertEqual(ajustes_acceso(None), {"umbral": 0.4, "ausenciaSeg": 7.0})

    def test_dice_la_verdad_sobre_la_contrasena_tras_un_rebloqueo(self):
        texto = self.textos(self.seccion())
        self.assertIn("solo vuelve a abrir su rostro", texto)
        self.assertNotIn("la contraseña sigue abriendo", texto)  # no se promete lo que la política no da

    def test_las_reglas_avisan_de_que_se_aplican_al_reabrir(self):
        self.assertIn("próxima vez que abras", self.textos(self.seccion()))

    def test_ningun_dato_biometrico_sale_en_los_bloques(self):
        import json
        s = self.seccion()
        s.operar("camara_umbral", {"valor": 0.5})
        texto = json.dumps(s.bloques(), ensure_ascii=False)
        self.assertNotIn("vector", texto.lower())
        self.assertNotIn("embedding", texto.lower())

    def test_operacion_desconocida(self):
        with self.assertRaises(ErrorSeccion):
            self.seccion().operar("camara_probar", {})


class TestNucleoUsaLasReglas(unittest.TestCase):
    def test_la_puerta_se_crea_con_el_umbral_y_la_ausencia_elegidos(self):
        import ast
        arbol = ast.parse((RAIZ / "dark_python" / "nucleo" / "dark_nucleo.py").read_text(encoding="utf-8"))
        llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "crear_gate"]
        self.assertEqual(len(llamadas), 1)
        self.assertTrue({"threshold", "ausencia_seg"} <= {k.arg for k in llamadas[0].keywords})

    def test_la_fabrica_acepta_esos_argumentos(self):
        from acceso import fabrica
        self.assertIn("threshold", fabrica._CLAVES_GATE)
        self.assertIn("ausencia_seg", fabrica._CLAVES_GATE)

    def test_la_puerta_carga_solo_a_las_personas_activas(self):
        fuente = (RAIZ / "dark_python" / "herramientas" / "dark_acceso.py").read_text(encoding="utf-8")
        self.assertIn("cargar_base(solo_activas=True)", fuente)


if __name__ == "__main__":
    unittest.main()


class TestRegistrosDeUnModeloAnterior(unittest.TestCase):
    def setUp(self):
        import os
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._previo = os.environ.get("DARK_USER_DATA_DIR")
        os.environ["DARK_USER_DATA_DIR"] = self.tmp.name

        def restaurar():
            if self._previo is None:
                os.environ.pop("DARK_USER_DATA_DIR", None)
            else:
                os.environ["DARK_USER_DATA_DIR"] = self._previo
        self.addCleanup(restaurar)

    def test_un_vector_de_512_valores_ya_no_sirve_y_se_pide_registrar_de_nuevo(self):
        viejo = np.random.default_rng(1).normal(size=512).astype("float32")
        biometria.guardar_base({"Ana": viejo / np.linalg.norm(viejo)})
        with self.assertRaises(biometria.ErrorBiometria) as ctx:
            biometria.cargar_base()
        self.assertIn("vuelva a registrarlos", str(ctx.exception))

    def test_los_vigentes_se_conservan_y_los_viejos_se_descartan(self):
        viejo = np.random.default_rng(1).normal(size=512).astype("float32")
        biometria.guardar_base({"Vieja": viejo, "Nueva": vector(2)})
        self.assertEqual(list(biometria.cargar_base()), ["Nueva"])
