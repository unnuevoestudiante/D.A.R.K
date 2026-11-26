"""Casos de cobertura del matcher V3, ahora único."""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    Capacidad,
    GestorIntenciones,
)
from nucleo.intenciones.matcher_palabras_clave import VocabularioCapacidad, candidatas, puntuar  # noqa: E402


FRASES_V3 = [
    ("reprodice música relajante", "reproducir_musica"),
    ("pásame jazz", "reproducir_musica"),
    ("arranca Opera", "abrir_aplicacion"),
    ("expande la tercera imagen", "accion_imagenes"),
    ("agranda la segunda foto", "accion_imagenes"),
    ("amplía la primera imagen", "accion_imagenes"),
    ("sube la música", "ajustar_volumen_musica"),
    ("llévame a YouTube", "abrir_en_navegador"),
    ("enséñame la página de descargas de Visual Studio Code",
     "abrir_en_navegador"),
    ("pon el volumen en 30", "ajustar_volumen_musica"),
    ("poner de fondo", "poner_wallpaper"),
    ("poner la canción Bohemian Rhapsody", "reproducir_musica"),
    ("inicia Opera", "abrir_aplicacion"),
    ("lanza Chrome", "abrir_aplicacion"),
    ("cierra Spotify", "cerrar_aplicacion"),
    ("abre config.py", "abrir_archivo"),
    ("busca config.py", "buscar_archivo"),
    ("busca fotos de perros", "buscar_imagenes"),
    ("busca 5 wallpapers de montañas", "buscar_imagenes"),
    ("muestra tareas", "menu"),
    ("muestra recursos", "menu"),
    ("dile al teléfono que encienda la linterna", "orden_modulo"),
    ("detén la música", "detener_musica"),
    ("escribe una página web sobre gatos", "escribir_codigo"),
    ("escribe un ensayo sobre historia", "escribir_documento"),
    ("traduce notas.txt al inglés", "traducir_archivo"),
    ("opción dos resultado", "seleccionar_resultado_web"),
    ("cámbiale el nombre", "cambiar_nombre_archivo"),
    ("sube el volumen", "ajustar_volumen_musica"),
    ("reproduce Queen", "reproducir_musica"),
    ("descarga la primera imagen", "accion_imagenes"),
    ("pon la segunda como fondo", "poner_wallpaper"),
    ("qué hora es", "hora"),
]


class PruebasMatcherV3(unittest.TestCase):
    def test_treinta_frases(self):
        self.assertEqual(len(FRASES_V3), 33)
        for frase, accion in FRASES_V3:
            with self.subTest(frase=frase):
                resultado = GestorIntenciones(
                    CAPACIDADES_NUCLEO).interpretar(frase)
                self.assertEqual(resultado.action, accion)

    def test_tres_sinonimos_resueltos_por_matcher_unico(self):
        nuevas = (
            ("reprodice música relajante", "reproducir_musica",
             {"query": "música relajante"}),
            ("pásame jazz", "reproducir_musica", {"query": "jazz"}),
            ("arranca Opera", "abrir_aplicacion", {"nombre": "Opera"}),
        )
        for frase, accion, parametros in nuevas:
            with self.subTest(frase=frase):
                resultado = GestorIntenciones(
                    CAPACIDADES_NUCLEO).interpretar(frase)
                self.assertEqual(resultado.action, accion)
                self.assertEqual(resultado.params_planos(), parametros)

    def test_frases_migradas_al_matcher_v3(self):
        casos = (
            ("muéstrame wallpapers de paisajes", "buscar_imagenes",
             {"query": "paisajes"}),
            ("encuentra fondos de pantalla de Japón", "buscar_imagenes",
             {"query": "Japón"}),
            ("muestra fotos de coches clásicos", "buscar_imagenes",
             {"query": "coches clásicos"}),
            ("busca una imagen de galaxias", "buscar_imagenes",
             {"query": "galaxias"}),
            ("googlea clima Madrid", "investigar", {"query": "clima Madrid"}),
            ("reanuda la tele", "orden_modulo", {
                "orden": {
                    "numero": None,
                    "action": "media_control",
                    "params": {"action": "play"},
                    "timeout": 12,
                    "module_type": "tv",
                },
            }),
            ("hazme una página web en HTML", "escribir_codigo", {
                "extension": "html",
            }),
        )
        for frase, accion, parametros in casos:
            with self.subTest(frase=frase):
                resultado = GestorIntenciones(
                    CAPACIDADES_NUCLEO).interpretar(frase)
                self.assertEqual(resultado.action, accion)
                actual = resultado.params_planos()
                for nombre, valor in parametros.items():
                    self.assertEqual(actual.get(nombre), valor)

    def test_pedido_pdf_de_tarea_larga_es_intencion_de_documento(self):
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "crea un documento PDF sobre Ada Lovelace")
        self.assertEqual(resultado.action, "escribir_documento")
        self.assertEqual(
            resultado.params_planos(),
            {
                "tema": "Ada Lovelace",
                "tipo_documento": "documento",
                "extension": "pdf",
            },
        )

    def test_modulo_puro_solo_importa_normalizador_y_stdlib(self):
        ruta = DARK_PYTHON / "nucleo" / "intenciones" / "matcher_palabras_clave.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        externos = {
            nodo.module.split(".")[0]
            for nodo in ast.walk(arbol)
            if isinstance(nodo, ast.ImportFrom) and nodo.module
            and nodo.module.split(".")[0] not in {
                "__future__", "collections", "dataclasses", "typing",
                "unicodedata", "difflib", "re", "nucleo",
            }
        }
        self.assertEqual(externos, set())

    def test_score_y_exclusiones(self):
        vocabulario = VocabularioCapacidad(
            verbos={"reproducir"}, objetos={"música"}, excluir={"televisión"})
        self.assertEqual(puntuar("reproducir música", vocabulario), 2.0)
        self.assertLessEqual(puntuar("reproducir música televisión", vocabulario), 0)

    def test_vocabulario_inferido_para_las_veintiseis_capacidades(self):
        self.assertEqual(len(CAPACIDADES_NUCLEO), 26)  # + conexiones: conectar, desconectar y estado
        self.assertTrue(all(c.vocabulario is not None for c in CAPACIDADES_NUCLEO))
        self.assertTrue(all(candidatas("pon música jazz", [c]) or c.nombre != "reproducir_musica"
                            for c in CAPACIDADES_NUCLEO))

    def test_capacidad_no_expone_handler_muerto(self):
        self.assertNotIn("handler", Capacidad.__dataclass_fields__)


if __name__ == "__main__":
    unittest.main()
