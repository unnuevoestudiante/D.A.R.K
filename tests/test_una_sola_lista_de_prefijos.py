"""Una sola lista de prefijos de fallo para los dos clasificadores.

`_normalizar_resultado` (núcleo) y `_ya_hablado` / `_clasificar_error` (dueño de
capacidades) deciden «esto es un fallo» recorriendo las mismas dos tuplas. Estaban
copiadas en los dos archivos y las copias divergieron: el núcleo se quedó con 20
prefijos y el dueño con 44, así que los 24 mensajes que llegaron con el traslado de
las capacidades —«No encontré imágenes», «No hay imagen en esa posición», «No puedo
abrir archivos en esa ubicación», «No tengo resultados web a la vista»— se leían como
éxito en la boca del orquestador: el usuario oía el fallo y el worker daba el paso por
bueno. Mismo origen que `ToolResult` definido dos veces: un contrato duplicado.

Las reglas que vigilan estas pruebas:

  * **una tupla, dos consumidores**: `contratos` la declara y los dos la importan
    (mismo objeto, no copia igual);
  * **nadie la reescribe en su casa**: una asignación módulo arriba revive la deriva;
  * **el censo**: 44 definitivos y 7 transitorios. Cambiar la cuenta es un acto
    deliberado, no el efecto secundario de añadir un mensaje a un solo archivo.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

import contratos  # noqa: E402
import nucleo.dark_nucleo as nucleo_mod  # noqa: E402
from herramientas.internas import ejecutor as ejecutor_mod  # noqa: E402

DarkNucleo = nucleo_mod.DarkNucleo
EjecutorHerramientas = ejecutor_mod.EjecutorHerramientas

NOMBRES = ("PREFIJOS_NO_REINTENTABLES", "PREFIJOS_FALLO_TRANSITORIO")
# 44 definitivos (20 compartidos + 24 que llegaron con las capacidades) y 8
# transitorios: los 7 que ya estaban en las dos casas más «Error instalando
# wallpaper», que no empezaba como ninguno de los 7 y se normalizaba como éxito.
CENSO = {"PREFIJOS_NO_REINTENTABLES": 44, "PREFIJOS_FALLO_TRANSITORIO": 8}

# Los 24 que solo estaban en el dueño de capacidades, copiados de su lista tal como
# llegó el traslado (medidos sobre HEAD: los 20 compartidos van en las dos casas).
LOS_24_DE_LAS_CAPACIDADES = (
    "No puedo abrir archivos en esa ubicación",
    "No puedo renombrar archivos en esa ubicación",
    "Necesito la ruta del archivo",
    "Necesito saber qué archivo",
    "Necesito el nombre nuevo",
    "Ese nombre tiene caracteres que no puedo usar",
    "Ese nombre no es válido",
    "Ya existe un archivo llamado",
    "No encontré imágenes",
    "No encontré resultados.",
    "No pude obtener la URL del resultado seleccionado",
    "No tengo resultados web a la vista",
    "No tengo imágenes a la vista",
    "No tengo esa imagen disponible",
    "No hay imagen en esa posición",
    "No hay imágenes para descargar",
    "No hay una búsqueda de imágenes previa",
    "No hay una imagen en la posición",
    "No tengo suficiente contexto para buscar similares",
    "No pude descargar la imagen #",
    "No pude poner la imagen #",
    "La imagen #",
    "La imagen supera los 30MB",
    "No encontré el fondo anterior en",
)


class PruebasUnHogar(unittest.TestCase):
    def test_los_dos_consumidores_miran_la_misma_tupla(self):
        for nombre in NOMBRES:
            self.assertIs(
                getattr(contratos, nombre),
                getattr(nucleo_mod, nombre),
                "%s: el núcleo tiene su propia copia" % nombre)
            self.assertIs(
                getattr(contratos, nombre),
                getattr(ejecutor_mod, nombre),
                "%s: el dueño de capacidades tiene su propia copia" % nombre)

    def test_ningun_consumidor_la_declara_en_su_archivo(self):
        """Si la tupla vuelve a escribirse módulo arriba, la deriva vuelve sola."""
        rutas = {
            "dark_nucleo.py": DARK_PYTHON / "nucleo" / "dark_nucleo.py",
            "ejecutor.py": (DARK_PYTHON / "herramientas" / "internas"
                            / "ejecutor.py"),
        }
        for etiqueta, ruta in rutas.items():
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            declaraciones = [
                "%s:%d" % (etiqueta, nodo.lineno)
                for nodo in arbol.body if isinstance(nodo, ast.Assign)
                for objetivo in nodo.targets
                if isinstance(objetivo, ast.Name) and objetivo.id in NOMBRES
            ]
            self.assertEqual(declaraciones, [],
                             "%s volvió a declarar los prefijos: %s"
                             % (etiqueta, declaraciones))

    def test_el_censo_de_las_dos_listas(self):
        for nombre, esperado in CENSO.items():
            actual = getattr(contratos, nombre)
            self.assertEqual(
                esperado, len(actual),
                "%s tiene %d prefijos y se esperaban %d: cambiar la cuenta exige "
                "actualizar esta prueba a propósito"
                % (nombre, len(actual), esperado))
            self.assertEqual(
                len(set(actual)), len(actual),
                "%s tiene prefijos repetidos" % nombre)


class PruebasClasificacion(unittest.TestCase):
    def nucleo(self):
        nuevo = Mock()
        nuevo.TOOLS_QUE_USAN_MODELO = {}
        return nuevo

    def test_los_24_que_llegaron_con_las_capacidades_no_son_exito(self):
        """Los que tenía el dueño y no el núcleo, escritos aquí a propósito.

        Esta prueba no depende de dónde viva la lista: nombra los veinticuatro
        mensajes y exige que la boca del orquestador los marque fallo. Sobre el
        código anterior a `contratos` fallan los 24, y ese era el daño —el
        usuario los oía y el worker daba el paso por bueno—.
        """
        sin_clasificar = [texto for texto in LOS_24_DE_LAS_CAPACIDADES
                          if DarkNucleo._normalizar_resultado(
                              self.nucleo(), texto).ok]
        self.assertEqual(
            [], sin_clasificar,
            "el núcleo lee éxito y se lo dice al usuario: %s" % sin_clasificar)

    def test_lo_que_el_dueno_llama_fallo_no_es_exito_en_el_nucleo(self):
        """Los 44 definitivos, recorridos por la boca del orquestador."""
        sin_clasificar = []
        for prefijo in contratos.PREFIJOS_NO_REINTENTABLES:
            if DarkNucleo._normalizar_resultado(self.nucleo(), prefijo).ok:
                sin_clasificar.append(prefijo)
        self.assertEqual(
            [], sin_clasificar,
            "el núcleo lee éxito y se lo dice al usuario: %s" % sin_clasificar)

    def test_los_transitorios_tambien_son_fallo_en_ambas_bocas(self):
        for prefijo in contratos.PREFIJOS_FALLO_TRANSITORIO:
            texto = prefijo if prefijo.endswith(" ") else prefijo + "algo"
            self.assertFalse(
                DarkNucleo._normalizar_resultado(
                    self.nucleo(), texto).ok,
                prefijo)
            self.assertFalse(
                ejecutor_mod.EjecutorHerramientas._ya_hablado(texto).ok,
                prefijo)

    def test_un_mensaje_de_exito_sigue_siendo_exito(self):
        """El corte no puede consistir en declarar todo fallo."""
        for texto in ("Fondo de pantalla actualizado.",
                      "Ahí van 4 imágenes en carrusel.",
                      "Guardado example en https://example.com."):
            self.assertTrue(
                DarkNucleo._normalizar_resultado(self.nucleo(), texto).ok, texto)

    def test_la_clasificacion_del_nucleo_no_reintenta_lo_definitivo(self):
        """`_clasificar_error` recibe el `detalle_error` del paso caído."""
        tipo, reintentable = DarkNucleo._clasificar_error(
            "No encontré imágenes con URLs válidas.")
        self.assertFalse(
            reintentable,
            "un paso imposible se va a reintentar en bucle (%s)" % tipo)


class PruebasWallpaperSinClasificar(unittest.TestCase):
    """El detalle menor que quedó del traslado.

    `instalar_wallpaper` y `_instalar_wallpaper_indice` cierran su `except` con
    `f"Error instalando wallpaper: {e}"`. Ese texto no empieza como ninguno de los
    prefijos —«Error al » no lo cubre—, así que las dos bocas lo devolvían como
    éxito: DarkNucleo `_normalizar_resultado` montaba `ToolResult(True, ...)` y
    `_clasificar_error` caía al default `("interno", False)`. El fallo se hablaba
    como si fuera la respuesta y el worker daba el paso por bueno sin reintentar.
    """

    FRASE = "Error instalando wallpaper: el archivo no llegó"

    def nucleo(self):
        return Mock()

    def test_en_la_boca_del_nucleo_es_fallo(self):
        self.assertFalse(
            DarkNucleo._normalizar_resultado(self.nucleo(), self.FRASE).ok,
            "el orquestador narró el fallo como respuesta")

    def test_en_ya_hablado_del_dueno_es_fallo(self):
        self.assertFalse(
            EjecutorHerramientas._ya_hablado(self.FRASE).ok,
            "la capacidad que ya habló dejó el paso marcado como bueno")

    def test_y_el_worker_la_reintenta(self):
        """Fallo transitorio: la ventana de descarga se puede repetir."""
        tipo, reintentable = DarkNucleo._clasificar_error(self.FRASE)
        self.assertTrue(reintentable, tipo)
        self.assertEqual("interno", tipo)


if __name__ == "__main__":
    unittest.main()
