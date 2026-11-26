"""Un solo sitio físico para la sesión compartida.

Nueve almacenes estaban duplicados a la vez en el núcleo, en el dueño de capacidades
y —los de imágenes— empujados por asignación al especialista de comunicación:
`_resultados_visuales`, `_imagenes_vistas`, `_ultima_query_imagenes`,
`_intencion_imagenes`, `_espera_wallpaper_pregunta`, `_espera_wallpaper_abierta_en`,
`_busqueda_web_sintesis_fallida`, `_ultimos_resultados` y
`_timer_ocultar_resultados`.

Las reglas que vigilan estas pruebas:

  * **un hogar**: lo que escribe una capacidad lo lee la presentación sin copiar. Con
    dos almacenes el fallo era silencioso: la tarjeta seguía en pantalla y la voz
    decía «no hay resultados», o `investigar` dejaba la bandera de síntesis en su
    lado y `_narrar_resultado` nunca la veía;
  * **vistas, no copias**: cada consumidor conserva los nombres con los que siempre
    accedió, respaldados por el mismo objeto;
  * **cero empujones**: el especialista recibe el objeto; si vuelve a haber cuatro
    asignaciones `especialista._x = ...`, hay dos hogares otra vez;
  * **degrada, no lanza**: un dueño construido sin sesión (pruebas, fábricas sueltas)
    se crea la suya y sigue funcionando.

El puerto está en `contratos/sesion_resultados.py`, la fábrica y la implementación en
`nucleo/sesion_resultados.py`, y la composición sale de `DarkNucleo.sesion`.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.sesion_resultados import PuertoSesionResultados  # noqa: E402
from nucleo import sesion_resultados  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402

CAMPOS = ("resultados_visuales", "imagenes_vistas", "ultima_query_imagenes",
          "intencion_imagenes", "espera_wallpaper_pregunta",
          "espera_wallpaper_abierta_en", "sintesis_fallida",
          # 8º y 9º: la lista de la búsqueda web y el temporizador que esconde el
          # panel. Los escribe el dueño de capacidades y los lee/cancela el núcleo.
          "ultimos_resultados", "timer_ocultar_resultados")


def _intencion(action, params=None):
    intencion = Mock()
    intencion.action = action
    intencion.params_planos.return_value = params or {}
    intencion._resultado_narrado = False
    return intencion


class PruebasPuertoYFabrica(unittest.TestCase):
    def test_la_implementacion_cumple_el_puerto(self):
        sesion = sesion_resultados.crear_sesion_resultados()
        self.assertIsInstance(sesion, PuertoSesionResultados)
        for campo in CAMPOS:
            self.assertTrue(hasattr(sesion, campo), campo)

    def test_arranca_sin_nada_escrito(self):
        # El estado inicial es el que el núcleo ponía a mano en su `__init__`.
        # `resultados_visuales` arranca en None, no en `[]`: la presentación
        # distingue «sin búsqueda» de «búsqueda sin tarjetas».
        sesion = sesion_resultados.crear_sesion_resultados()

        self.assertIsNone(sesion.resultados_visuales)
        self.assertEqual(sesion.imagenes_vistas, set())
        self.assertIsNone(sesion.ultima_query_imagenes)
        self.assertIsNone(sesion.intencion_imagenes)
        self.assertIsNone(sesion.espera_wallpaper_pregunta)
        self.assertIsNone(sesion.espera_wallpaper_abierta_en)
        self.assertFalse(sesion.sintesis_fallida)
        self.assertIsNone(sesion.ultimos_resultados)
        self.assertIsNone(sesion.timer_ocultar_resultados)

    def test_limpiar_imagenes_deja_cuatro_campos_y_no_toca_la_espera(self):
        """El `limpiar` es el de las tarjetas: la espera del tema vive aparte.

        Mezclarlas sería borrar la ventana de 35 s al ocultar resultados, que es
        justo lo que `_esconder_overlay_principal` no quiere hacer.
        """
        sesion = sesion_resultados.crear_sesion_resultados()
        sesion.resultados_visuales = [{"url": "x"}]
        sesion.imagenes_vistas = {"url"}
        sesion.ultima_query_imagenes = "gatos"
        sesion.intencion_imagenes = "wallpaper"
        sesion.espera_wallpaper_pregunta = "¿de qué tema?"

        sesion.limpiar_imagenes()

        self.assertIsNone(sesion.resultados_visuales)
        self.assertEqual(sesion.imagenes_vistas, set())
        self.assertIsNone(sesion.ultima_query_imagenes)
        self.assertIsNone(sesion.intencion_imagenes)
        self.assertEqual(sesion.espera_wallpaper_pregunta, "¿de qué tema?")


class PruebasHogarUnico(unittest.TestCase):
    def setUp(self):
        self.sesion = sesion_resultados.crear_sesion_resultados()

    def nucleo(self):
        # `object.__new__` es la forma que usan las pruebas de pipeline: si `sesion`
        # dependiera del constructor, estos núcleos se quedarían sin sesión.
        nuevo = DarkNucleo.__new__(DarkNucleo)
        nuevo._sesion_cache = self.sesion
        return nuevo

    def ejecutor(self):
        from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios
        return EjecutorHerramientas(
            servicios=Servicios(sesion=self.sesion,
                                hablar=lambda texto: None))

    def test_los_tres_consumidores_miran_el_mismo_objeto(self):
        from especialistas.especialista_comunicacion import EspecialistaComunicacion
        nucleo = self.nucleo()
        especialista = EspecialistaComunicacion(sesion=self.sesion)

        self.assertIs(nucleo.sesion, self.sesion)
        self.assertIs(self.ejecutor().sesion, self.sesion)
        self.assertIs(especialista.sesion, self.sesion)

    def test_escribir_por_la_capacidad_se_ve_desde_la_vista_del_nucleo(self):
        """La escritura cae en el almacén, no en la vista de quien escribió."""
        nucleo = self.nucleo()
        tarjetas = [{"titulo": "gato", "url": "https://x"}]

        self.ejecutor().resultados_visuales = tarjetas

        self.assertEqual(nucleo._resultados_visuales, tarjetas)
        self.assertEqual(self.sesion.resultados_visuales, tarjetas)

    def test_la_vista_del_nucleo_escribe_en_el_almacen_compartido(self):
        nucleo = self.nucleo()

        nucleo._ultima_query_imagenes = "pajarito de mi barrio"

        self.assertEqual(self.ejecutor().ultima_query_imagenes,
                         "pajarito de mi barrio")

    def test_la_espera_del_wallpaper_la_abre_un_dueno_y_la_cierra_el_nucleo(self):
        """`_preguntar_tema_wallpaper` vive en capacidades; la ventana, en el núcleo."""
        nucleo = self.nucleo()
        nucleo._habla_activa = Mock()
        nucleo._habla_activa.is_set.return_value = False
        nucleo._habla_pendiente = Mock()
        nucleo._habla_pendiente.is_set.return_value = False
        nucleo.speak = Mock()

        with patch("random.choice",
                   return_value="¿De qué tema lo quiere, señor?"):
            self.ejecutor()._preguntar_tema_wallpaper()

        self.assertEqual(nucleo._espera_wallpaper_pregunta,
                         "¿De qué tema lo quiere, señor?")
        with patch("nucleo.dark_nucleo.time.time", return_value=1_000.0):
            self.assertTrue(nucleo._espera_wallpaper_viva())

        nucleo._cerrar_espera_wallpaper()

        self.assertIsNone(self.sesion.espera_wallpaper_pregunta)
        self.assertIsNone(self.sesion.espera_wallpaper_abierta_en)

    def test_la_sintesis_fallida_del_ejecutor_la_narra_la_voz(self):
        """Hoy este dato se pierde: lo escribe `investigar` y lo lee `_narrar_resultado`."""
        nucleo = self.nucleo()
        nucleo.cerebro = Mock()
        self.sesion.sintesis_fallida = True

        frase = DarkNucleo._narrar_resultado(
            nucleo, "Einstein: el resumen va pegado con las fuentes.",
            _intencion("investigar"))

        self.assertIn("No pude resumir", frase)
        nucleo.cerebro.dar_forma_resultado.assert_not_called()

    def _investigar_sin_red_ni_modelo(self, ejecutor, resultados):
        """`investigar` de verdad, con la búsqueda y el modelo fuera del camino.

        Se parcha el proveedor de resultados, no la herramienta: lo que se quiere
        medir es que la lista la guarda EL DUEÑO y la lee LA VOZ.
        """
        with patch.object(ejecutor, "_buscar_resultados_web",
                          return_value=resultados), \
             patch.object(ejecutor, "_investigar_interno", return_value=""), \
             patch.object(ejecutor, "_preparar_modelo_de_trabajo",
                          return_value=False):
            return ejecutor.investigar("einstein")

    def test_lo_que_guarda_investigar_lo_selecciona_la_voz(self):
        """Hoy la lista queda en el almacén del ejecutor: `_detectar_seleccion_resultado`
        mira el suyo, siempre None, y «abre la segunda» no existe."""
        nucleo = self.nucleo()
        resultados = [{"title": f"fuente {i}", "href": f"https://x.test/{i}"}
                      for i in range(3)]

        self._investigar_sin_red_ni_modelo(self.ejecutor(), resultados)

        self.assertEqual(1, nucleo._detectar_seleccion_resultado("abre la segunda"))

    def test_al_bajar_un_resultado_se_vacian_ambas_lecturas(self):
        """`_seleccionar_resultado` limpia la lista: si limpia su copia, el dueño
        sigue ofreciendo las fuentes de la búsqueda anterior."""
        nucleo = self.nucleo()
        nucleo.speak = Mock()
        capacidades = Mock()
        capacidades.descargar_archivo.return_value = "Descargado."
        nucleo._capacidades_herramientas = Mock(return_value=capacidades)
        self._investigar_sin_red_ni_modelo(
            self.ejecutor(),
            [{"title": "fuente", "href": "https://x.test/1"}])

        DarkNucleo._seleccionar_resultado(nucleo, 0)

        self.assertIsNone(self.sesion.ultimos_resultados)
        self.assertIsNone(self.ejecutor()._ultimos_resultados)

    def test_el_temporizador_de_la_capacidad_lo_cancela_el_mismo_dueño(self):
        """Un panel, un temporizador — y desde el corte 3 ya no hay dos manijas.

        La escondida era la del núcleo: cancelaba `None` y el Timer del ejecutor
        seguía armándose. Con el cuerpo mudado, lo que queda por probar es que
        las dos llegadas al almacén —el ejecutor montado a mano y el que el
        núcleo inyecta— cancelan EL MISMO temporizador de la sesión.
        """
        nucleo = self.nucleo()
        nucleo.overlay = Mock()
        nucleo.overlay.estado.return_value = "idle"
        nucleo._set_overlay = Mock()
        self.sesion.resultados_visuales = [{"image": "https://x.test/1.jpg"}]
        timer = Mock()
        capacidades = nucleo._capacidades_herramientas()

        with patch("threading.Timer", return_value=timer) as fabrica:
            self.ejecutor()._ocultar_resultados_visuales(borrar_memoria=False)

            self.assertIs(self.sesion.timer_ocultar_resultados, timer)
            timer.cancel.assert_not_called()

            capacidades._ocultar_resultados_visuales(borrar_memoria=False)

        timer.cancel.assert_called_once()
        self.assertEqual(2, fabrica.call_count)
        self.assertIs(self.sesion.timer_ocultar_resultados, timer)

    def test_sin_sesion_inyectada_el_ejecutor_se_basta(self):
        from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios
        dueño = EjecutorHerramientas(servicios=Servicios())

        self.assertIsInstance(dueño.sesion, PuertoSesionResultados)
        dueño.sesion.resultados_visuales = [{"url": "y"}]
        self.assertEqual(dueño.sesion.resultados_visuales, [{"url": "y"}])


class PruebasCeroCopias(unittest.TestCase):
    def test_el_especialista_recibe_el_objeto_y_sus_nombres_son_vistas(self):
        from especialistas.especialista_comunicacion import EspecialistaComunicacion
        sesion = sesion_resultados.crear_sesion_resultados()

        especialista = EspecialistaComunicacion(sesion=sesion)

        sesion.resultados_visuales = [{"url": "z"}]
        self.assertEqual(especialista._resultados_visuales, [{"url": "z"}])
        especialista._intencion_imagenes = "wallpaper"
        self.assertEqual(sesion.intencion_imagenes, "wallpaper")

    def test_el_nucleo_ya_no_empuja_los_cuatro_valores(self):
        """El empujón era el pegamento: cuatro asignaciones y dos hogares."""
        ruta = DARK_PYTHON / "nucleo" / "dark_nucleo.py"
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        privados = {"_%s" % c for c in CAMPOS} | {"_busqueda_web_sintesis_fallida"}
        empujones = []
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
                objetivo = nodo.targets[0]
                if (isinstance(objetivo, ast.Attribute)
                        and objetivo.attr in privados
                        and not (isinstance(objetivo.value, ast.Name)
                                 and objetivo.value.id == "self")):
                    empujones.append("%d:%s.%s" % (
                        nodo.lineno, ast.unparse(objetivo.value), objetivo.attr))
        self.assertEqual(empujones, [],
                         "el núcleo volvió a copiarle estado a otro consumidor: %s"
                         % empujones)

    def test_ningun_consumidor_declara_el_almacen_en_su_constructor(self):
        """Si `self._resultados_visuales = None` vuelve a un `__init__`, el objeto
        deja de ser el único sitio: la asignación pisa el almacén compartido.
        """
        rutas = [DARK_PYTHON / "nucleo" / "dark_nucleo.py",
                 DARK_PYTHON / "herramientas" / "internas" / "ejecutor.py",
                 DARK_PYTHON / "especialistas" / "especialista_comunicacion.py"]
        privados = {"_%s" % c for c in CAMPOS} | {"_busqueda_web_sintesis_fallida"}
        for ruta in rutas:
            arbol = ast.parse(ruta.read_text(encoding="utf-8"))
            declaraciones = []
            for clase in [n for n in arbol.body if isinstance(n, ast.ClassDef)]:
                for funcion in [f for f in clase.body
                                if isinstance(f, ast.FunctionDef)
                                and f.name == "__init__"]:
                    for nodo in ast.walk(funcion):
                        if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
                            objetivo = nodo.targets[0]
                            if (isinstance(objetivo, ast.Attribute)
                                    and objetivo.attr in privados):
                                declaraciones.append(
                                    "%s:%d %s" % (ruta.name, nodo.lineno, objetivo.attr))
            self.assertEqual(declaraciones, [],
                             "un consumidor volvió a declarar el almacén: %s"
                             % declaraciones)


if __name__ == "__main__":
    unittest.main()
