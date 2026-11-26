"""Pruebas del dueño de capacidades: sus hojas, no su capa de despacho.

El ejecutor se instancia SIN DarkNucleo: si estas pruebas necesitan el
núcleo, el desacoplamiento no es real.

Lo que ya no se prueba aquí es el `ejecutar(mensaje)` del dueño —el dispatcher
que formaba un `PasoResultado` a partir de un diccionario—, porque ese camino
no lo recorre nadie: el núcleo pregunta al banco (`_banco_herramientas()`) y el
banco monta contra `getattr`. Cada contrato que vivía en aquel dispatcher tiene
ahora un hogar declarado:

  * forma del paso, `paso_id` y alias .... `tests/test_orquestador_herramientas.py:278`
  * puerta de la terminal de desarrollo .. `tests/test_orquestador_herramientas.py:202`
  * nombre inventado, `tool_not_found` ... `tests/test_orquestador_herramientas.py:243`
  * defaults, descartes, requeridos ...... `tests/test_banco_herramientas.py:405/430/436`
  * clasificación de un fallo ........... `tests/test_una_sola_lista_de_prefijos.py:126`

Lo que sí es del dueño y se prueba aquí es lo que sus hojas devuelven: el
texto, el efecto y —donde el caso lo pide— el veredicto del par que el dueño
conserva (`_normalizar_resultado` + `_clasificar_error`).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas import ejecutor as ej  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas, Servicios,
)


class FakeDDGS:
    """Devuelve resultados deterministas, sin red. El ejecutor llama a
    DDGS(), así que se pasa la clase, no una instancia."""
    imagenes = [
        {"title": f"paisaje {i}", "image": f"https://x.test/{i}.jpg",
         "thumbnail": f"https://x.test/{i}_t.jpg", "url": "https://x.test"}
        for i in range(12)
    ]

    def images(self, query, max_results=15):
        return self.imagenes[:max_results]

    def text(self, query, max_results=5):
        return [{"title": f"resultado {i}", "body": "cuerpo",
                 "href": f"https://x.test/r{i}"} for i in range(max_results)]


def veredicto(e, raw):
    """(ok, tipo_error, reintentable) de lo que dice una hoja.

    Es el par de funciones que el dueño conserva: el núcleo lo aplica sobre el
    resultado crudo del banco, así que afirmar aquí el veredicto de un texto
    real de hoja es probar lo que el plan va a ver, sin volver a fabricar el
    `PasoResultado` del dispatcher muerto.
    """
    tr = e._normalizar_resultado(raw)
    tipo, reint = e._clasificar_error(tr.detalle_error or tr.mensaje)
    return tr.ok, tipo, reint


class PruebasServicios(unittest.TestCase):
    def test_hablar_y_overlay_se_delegan(self):
        hablado, pintado = [], []
        e = EjecutorHerramientas(servicios=Servicios(
            hablar=hablado.append,
            overlay=lambda estado, **kw: pintado.append((estado, kw)),
            estado_overlay=lambda: "listening",
        ))
        e.speak("hola")
        e._set_overlay("showing_results", results_data={"items": [1]})
        self.assertEqual(hablado, ["hola"])
        self.assertEqual(pintado[0][0], "showing_results")
        self.assertEqual(pintado[0][1]["results_data"], {"items": [1]})
        self.assertEqual(e._estado_overlay(), "listening")

    def test_estado_overlay_sale_del_objeto_si_no_hay_callback(self):
        """Sin callback se lee el método del contrato, no un atributo privado.

        `FachadaOverlay` solo expone `estado()`; el doble de antes ponía
        `_state`, que la fachada real no tiene, y tapaba una lectura que en
        producción devolvía "idle" siempre.
        """
        class FachadaDePrueba:
            def estado(self):
                return "showing_results"

        e = EjecutorHerramientas(servicios=Servicios(
            overlay_obj=FachadaDePrueba()))
        self.assertEqual(e._estado_overlay(), "showing_results")
        self.assertTrue(e._hay_imagenes_visibles())

    def test_sintesis_web_sin_llm_devuelve_titulares(self):
        """Sin modelo la búsqueda no se queda muda: da titulares y URLs.

        El parche del navegador pasó a reclamar que NO llamen: desde K.3.1
        «busca X» no abre páginas, y abrir es otra herramienta.
        """
        e = EjecutorHerramientas(servicios=Servicios(http=Mock()))
        with patch.object(ej, "DDGS", FakeDDGS), \
             patch.object(ej.webbrowser, "open") as abrir:
            msg = e.investigar("algo")
        self.assertIn("Encontré 5 resultados", msg)
        self.assertEqual(len(e.ultimos_resultados), 5)
        abrir.assert_not_called()


class PruebasRutas(unittest.TestCase):
    def setUp(self):
        self.e = EjecutorHerramientas()

    def test_ruta_absoluta_no_se_reescribe(self):
        absoluta = os.path.join("C:\\", "Users", "samue", "Desktop", "x.txt")
        self.assertEqual(self.e._normalizar_arg_ruta(absoluta),
                         os.path.normpath(absoluta))

    def test_destino_en_lenguaje_natural_se_resuelve(self):
        # El patrón que corta el nombre es ([^/\\]+\.\w+)$, que traga los
        # espacios: "en el escritorio prueba.txt" acaba pegado al destino.
        # Es el comportamiento heredado del núcleo; el test lo fija para que
        # un cambio aquí sea visible, no invisible.
        resuelto = self.e._normalizar_arg_ruta("en el escritorio prueba.txt")
        self.assertTrue(resuelto.startswith(ej.ESCRITORIO))
        self.assertEqual(resuelto, os.path.join(ej.ESCRITORIO,
                                                "en el escritorio prueba.txt"))
        self.assertEqual(self.e._normalizar_arg_ruta("mis documentos"),
                         ej.DOCUMENTOS)

    def test_valor_no_string_pasa_intacto(self):
        self.assertEqual(self.e._normalizar_arg_ruta(7), 7)

    def test_rutas_protegidas_bloqueadas(self):
        self.assertFalse(self.e._ruta_permitida("C:\\Windows\\System32\\cmd.exe"))
        self.assertFalse(self.e._ruta_permitida("C:\\Program Files\\x"))
        self.assertTrue(self.e._ruta_permitida(ej.DESCARGAS))

    def test_alias_de_carpeta(self):
        self.assertEqual(self.e._resolver_ruta("descargas"), ej.DESCARGAS)
        self.assertEqual(self.e._resolver_ruta("escritorio\\notas.txt"),
                         os.path.join(ej.ESCRITORIO, "notas.txt"))

    def test_abrir_archivo_en_zona_bloqueada(self):
        raw = self.e._abrir_archivo_intencion("C:\\Windows\\System32\\x.exe")
        self.assertIn("No puedo abrir archivos", raw)
        self.assertEqual((False, "archivo", False), veredicto(self.e, raw))

    def test_abrir_archivo_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = self.e._abrir_archivo_intencion(
                os.path.join(tmp, "no_existe.txt"))
        ok, tipo, reint = veredicto(self.e, raw)
        self.assertFalse(ok, raw)
        self.assertEqual("archivo", tipo)

    def test_abrir_archivo_real(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "real.txt")
            Path(ruta).write_text("hola", encoding="utf-8")
            with patch.object(ej.os, "startfile") as abrir:
                raw = self.e._abrir_archivo_intencion(ruta)
            abrir.assert_called_once_with(ruta)
        self.assertIn("Abriendo real.txt", raw)
        self.assertTrue(veredicto(self.e, raw)[0], raw)

    def test_renombrar_conserva_la_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "viejo.txt")
            Path(ruta).write_text("hola", encoding="utf-8")
            raw = self.e.cambiar_nombre_archivo(ruta, "nuevo")
            self.assertTrue(veredicto(self.e, raw)[0], raw)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "nuevo.txt")))
            self.assertFalse(os.path.exists(ruta))

    def test_renombrar_rechaza_caracteres_reservados(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "viejo.txt")
            Path(ruta).write_text("hola", encoding="utf-8")
            raw = self.e.cambiar_nombre_archivo(ruta, "malo:nombre")
            self.assertIn("caracteres que no puedo usar", raw)
            self.assertFalse(veredicto(self.e, raw)[0], raw)
            self.assertTrue(os.path.isfile(ruta))

    def test_renombrar_no_pisa_un_archivo_existente(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = os.path.join(tmp, "viejo.txt")
            Path(ruta).write_text("hola", encoding="utf-8")
            Path(os.path.join(tmp, "ocupado.txt")).write_text("ya", encoding="utf-8")
            raw = self.e.cambiar_nombre_archivo(ruta, "ocupado.txt")
        self.assertIn("Ya existe un archivo", raw)
        self.assertFalse(veredicto(self.e, raw)[0], raw)

    def test_sanear_nombre(self):
        self.assertEqual(self.e._sanear_nombre("Mi Archivo (final).PDF"),
                         "mi_archivo__final__pdf")
        self.assertEqual(self.e._sanear_nombre("", default="x"), "x")


class PruebasDescargas(unittest.TestCase):
    def test_esquema_no_http_se_rechaza(self):
        e = EjecutorHerramientas()
        raw = e.descargar_archivo("file:///C:/x.txt")
        self.assertIn("Solo puedo descargar desde", raw)
        self.assertEqual((False, "tool", False), veredicto(e, raw))

    def test_extension_ejecutable_bloqueada(self):
        resp = Mock()
        resp.__enter__ = Mock(return_value=resp)
        resp.__exit__ = Mock(return_value=False)
        resp.headers = {"Content-Disposition": 'attachment; filename="instalador.bat"'}
        resp.raise_for_status = Mock()
        http = Mock()
        http.get = Mock(return_value=resp)
        e = EjecutorHerramientas(servicios=Servicios(http=http))
        raw = e.descargar_archivo("https://x.test/instalador.bat")
        self.assertIn("No descargo archivos .bat", raw)
        self.assertFalse(veredicto(e, raw)[0], raw)

    def test_exe_no_esta_en_la_lista_de_bloqueadas(self):
        """Documenta un hueco real: .exe no está en DOWNLOADS_BLOCKED_EXT,
        así que un ejecutable sí se descarga. Test en verde = hueco intacto."""
        self.assertNotIn("exe", ej.DOWNLOADS_BLOCKED_EXT)

    def test_extension_desde_url_y_content_disposition(self):
        e = EjecutorHerramientas()
        self.assertEqual(e._extension_desde_url("https://x.test/a.pdf?token=1"), "pdf")
        self.assertEqual(
            e._extension_desde_url("https://x.test/descarga",
                                   'attachment; filename="informe.docx"'), "docx")
        self.assertEqual(e._extension_desde_url("https://x.test/sin"), "")


class PruebasImagenes(unittest.TestCase):
    def setUp(self):
        self.hablado = []
        self.pintado = []
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.http = Mock()
        # El overlay dice lo último que se pintó: `accion_imagenes` se niega sin
        # tarjetas a la vista, así que el estado tiene que seguir la conversación.
        self.estado = "idle"

        def pintar(estado, **kw):
            self.estado = estado
            self.pintado.append((estado, kw))

        self.e = EjecutorHerramientas(servicios=Servicios(
            hablar=self.hablado.append,
            overlay=pintar,
            estado_overlay=lambda: self.estado,
            http=self.http,
        ))
        self._ddgs = patch.object(ej, "DDGS", FakeDDGS)
        self._ddgs.start()
        self.addCleanup(self._ddgs.stop)
        self._descargas = patch.object(ej, "DESCARGAS", self.tmp.name)
        self._descargas.start()
        self.addCleanup(self._descargas.stop)

    def _buscar(self, query="paisajes", count=3):
        return self.e.buscar_imagenes_texto(query, count=count)

    def test_buscar_deja_sesion_y_pinta_resultados(self):
        msg = self._buscar()
        self.assertTrue(veredicto(self.e, msg)[0], msg)
        self.assertEqual(len(self.e.resultados_visuales), 3)
        self.assertEqual(self.e.intencion_imagenes, "descargar")
        self.assertEqual(self.e.ultima_query_imagenes, "paisajes")
        self.assertEqual(self.pintado[-1][0], "showing_results")
        self.assertFalse(self.pintado[-1][1]["results_data"]["carousel"])

    def test_query_de_wallpaper_fija_la_intencion(self):
        self._buscar("wallpaper de montañas", count=2)
        self.assertEqual(self.e.intencion_imagenes, "wallpaper")

    def test_mas_de_tres_es_carrusel(self):
        msg = self._buscar(count=6)
        self.assertIn("carrusel", msg)
        self.assertTrue(self.e.payload_resultados()["carousel"])

    def test_count_se_acota(self):
        self._buscar(count=999)
        self.assertLessEqual(len(self.e.resultados_visuales), 30)

    def test_payload_y_ocultar_limpian_la_sesion(self):
        self._buscar()
        self.assertIsNotNone(self.e.payload_resultados())
        self.e.ocultar_resultados()
        self.assertIsNone(self.e.resultados_visuales)
        self.assertIsNone(self.e.payload_resultados())
        self.assertIsNone(self.e.ultima_query_imagenes)
        self.assertEqual(self.pintado[-1][1]["results_data"]["items"], [])

    def test_ocultar_sin_borrar_memoria_conserva_los_items(self):
        self._buscar()
        self.e.ocultar_resultados(borrar_memoria=False)
        self.assertEqual(len(self.e.resultados_visuales), 3)
        if self.e._timer_ocultar_resultados:
            self.e._timer_ocultar_resultados.cancel()

    def test_descargar_imagen_por_indice(self):
        self._buscar()
        resp = Mock()
        resp.__enter__ = Mock(return_value=resp)
        resp.__exit__ = Mock(return_value=False)
        resp.raise_for_status = Mock()
        resp.iter_content = Mock(return_value=[b"datos-de-imagen"])
        self.http.get = Mock(return_value=resp)
        raw = self.e._descargar_imagen(0)
        self.assertIn("Descargada en", raw)
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)

    def test_indice_fuera_de_rango_es_fallo_no_reintentable(self):
        self._buscar()
        raw = self.e._descargar_imagen(99)
        self.assertEqual("No hay imagen en esa posición.", raw)
        self.assertEqual((False, "tool", False), veredicto(self.e, raw))

    def test_accion_limpiar(self):
        self._buscar()
        self.e._despachar_accion_imagenes(accion="limpiar")
        self.assertIsNone(self.e.resultados_visuales)
        self.assertIn("Listo, las quité.", self.hablado)

    def test_accion_sin_tarjetas_a_la_vista_es_fallo_definitivo(self):
        """El candado no puede registrar éxito: el paso no se cumplió.

        La lista sigue viva después de un `esconder`, pero no hay tarjeta sobre
        la que actuar. Como el rechazo es mudo, si sale como éxito el plan
        avanza sin saberlo; sale como fallo de herramienta no reintentable.
        """
        self.e._resultados_visuales = [
            {"url": "https://x.test/1.jpg", "title": "paisaje 1"}]
        tr = self.e._despachar_accion_imagenes(accion="descargar", indices=[0])
        self.assertFalse(tr.ok)
        self.assertEqual("", tr.mensaje)
        self.assertIn("precondition:", tr.detalle_error)
        self.assertEqual((False, "tool", False), veredicto(self.e, tr))
        self.assertEqual([], self.hablado)

    def test_wallpaper_por_indice(self):
        self._buscar()
        with patch.object(self.e, "instalar_wallpaper",
                          return_value="Fondo de pantalla actualizado.") as instalar:
            tr = self.e._despachar_accion_imagenes(accion="wallpaper", indices=[1])
        instalar.assert_called_once_with("https://x.test/1.jpg")
        self.assertEqual("", tr.mensaje)
        self.assertIn("Fondo de pantalla actualizado.", self.hablado)

    def test_poner_wallpaper_sin_url_usa_la_sesion(self):
        self._buscar()
        with patch.object(self.e, "instalar_wallpaper",
                          return_value="Fondo de pantalla actualizado.") as instalar:
            tr = self.e._poner_wallpaper_intencion(indice=2)
        instalar.assert_called_once_with("https://x.test/2.jpg")
        self.assertTrue(tr.ok)

    def test_poner_wallpaper_sin_nada_que_poner_pregunta_el_tema(self):
        tr = self.e._poner_wallpaper_intencion()
        self.assertTrue(tr.ok)
        self.assertEqual("", tr.mensaje)
        self.assertEqual(1, len(self.hablado))
        self.assertEqual(self.hablado[-1], self.e.espera_wallpaper_pregunta)

    def test_ampliar_anade_sin_repetir(self):
        self._buscar(count=3)
        raw = self.e._ampliar_imagenes(count=3)
        self.assertTrue(veredicto(self.e, raw)[0], raw)
        self.assertEqual(len(self.e.resultados_visuales), 6)
        urls = [i["url"] for i in self.e.resultados_visuales]
        self.assertEqual(len(urls), len(set(urls)))

    def test_ampliar_sin_busqueda_previa(self):
        raw = self.e._ampliar_imagenes(count=3)
        self.assertIn("No hay una búsqueda de imágenes previa", raw)

    def test_buscar_similares_usa_el_titulo(self):
        self._buscar()
        with patch.object(self.e, "buscar_imagenes_texto",
                          return_value="ok") as buscar:
            self.e._buscar_similares_a_indice(0, count=6)
        buscar.assert_called_once_with("paisaje 0", count=6)


class PruebasSeleccionWeb(unittest.TestCase):
    def setUp(self):
        self.e = EjecutorHerramientas()
        self.e._ultimos_resultados = [
            {"title": "primero", "href": "https://x.test/1.pdf"},
            {"title": "segundo", "href": "https://x.test/2.pdf"},
        ]

    def test_detectar_por_ordinal(self):
        self.assertEqual(self.e.detectar_seleccion_resultado("el segundo"), 1)
        self.assertEqual(self.e.detectar_seleccion_resultado("la opción 1"), 0)

    def test_detectar_sin_resultados(self):
        self.e._ultimos_resultados = None
        self.assertIsNone(self.e.detectar_seleccion_resultado("el primero"))

    def test_seleccionar_descarga_y_limpia(self):
        with patch.object(self.e, "descargar_archivo",
                          return_value="Descargado en x.") as descargar:
            raw = self.e._seleccionar_resultado(1)
        descargar.assert_called_once_with("https://x.test/2.pdf", "segundo")
        self.assertTrue(veredicto(self.e, raw)[0], raw)
        self.assertIsNone(self.e.ultimos_resultados)

    def test_seleccionar_sin_resultados(self):
        self.e._ultimos_resultados = None
        raw = self.e._seleccionar_resultado(0)
        self.assertIn("No tengo resultados web a la vista", raw)


class PruebasTV(unittest.TestCase):
    """La voz llama a los manejadores; None significa «esta frase no es mía».

    Lo otro que había —traducir ese None a un paso fallido para el LLM— eran las
    `herramienta_tv_*`, y se va con el dispatcher: ningún banco monta esos
    nombres y la ruta de voz no los necesita, porque cede el turno al intérprete.
    """

    def test_sin_bridge_la_configuracion_delega_al_modulo(self):
        e = EjecutorHerramientas()
        with patch("modulos.tv.modulo.save_tv_mac",
                   return_value=(True, "MAC guardada.")) as guardar:
            msg = e._manejar_config_tv("la mac de mi tele es AA:BB:CC:DD:EE:FF")
        guardar.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        self.assertEqual("MAC guardada.", msg)

    def test_el_bridge_inyectado_tiene_prioridad(self):
        bridge = Mock()
        bridge.apply_mac = Mock(return_value="MAC aplicada.")
        e = EjecutorHerramientas(servicios=Servicios(tv_bridge=lambda: bridge))
        msg = e._manejar_config_tv("la mac de mi tele es AA:BB:CC:DD:EE:FF")
        bridge.apply_mac.assert_called_once_with("AA:BB:CC:DD:EE:FF")
        self.assertEqual("MAC aplicada.", msg)

    def test_tv_bridge_perezoso_se_consulta_en_cada_llamada(self):
        actual = [None]
        e = EjecutorHerramientas(servicios=Servicios(tv_bridge=lambda: actual[0]))
        self.assertIsNone(e._tv_bridge)
        actual[0] = Mock()
        self.assertIsNotNone(e._tv_bridge)

    def test_volumen_sin_mencion_a_la_tele_cede_al_interprete(self):
        e = EjecutorHerramientas()
        self.assertIsNone(e._manejar_control_tv("sube el volumen"))
        self.assertIsNone(e._manejar_control_tv("pon música"))

    def test_destino_ui_sin_overlay(self):
        e = EjecutorHerramientas()
        self.assertEqual("No hay interfaz activa.",
                         e._manejar_destino_ui("modo televisor"))

    def test_destino_ui_activa_modo_televisor(self):
        ov = Mock()
        e = EjecutorHerramientas(servicios=Servicios(overlay_obj=ov))
        with patch("modulos.tv.modulo.presentar_interfaz_tv"):
            msg = e._manejar_destino_ui("modo televisor")
        ov.modo_televisor.assert_called_once_with(True)
        self.assertIn("Sigo en el televisor", msg)

    def test_diagnostico_no_lo_secuestra_el_destino_ui(self):
        e = EjecutorHerramientas()
        self.assertIsNone(e._manejar_destino_ui("vuelve al computador y mira la ram"))


class PruebasFalloHablado(unittest.TestCase):
    """Un fallo ya hablado no puede leerse como éxito.

    Las capacidades de imágenes hablan su propio mensaje y devolvían "", y
    `_normalizar_resultado` convierte "" en ToolResult(True, ""). El orquestador
    necesita el fallo en `ok`/`detalle_error`, no en el mensaje. Se afirma sobre
    el `ToolResult` de la hoja; la traducción a paso es del núcleo y ya tiene su
    propia prueba (`test_una_sola_lista_de_prefijos.py`).
    """

    def setUp(self):
        self.hablado = []
        self.e = EjecutorHerramientas(servicios=Servicios(
            hablar=self.hablado.append,
            # El candado del overlay se comprueba aparte; aquí lo que se mide es
            # la clasificación de un fallo que ya habló. Con el overlay en `idle`
            # nada de esto llegaría a ejecutarse.
            estado_overlay=lambda: "showing_results",
            http=Mock(),
        ))

    def _accion(self, accion, **extra):
        return self.e._despachar_accion_imagenes(accion=accion, **extra)

    def test_lista_vacia_descargar_es_fallo_definitivo(self):
        tr = self._accion("descargar", indices=[0])
        self.assertFalse(tr.ok)
        self.assertFalse(veredicto(self.e, tr)[2])
        self.assertIn("No tengo imágenes a la vista", tr.detalle_error)

    def test_lista_vacia_wallpaper_es_fallo_definitivo(self):
        self.assertFalse(self._accion("wallpaper", indices=[0]).ok)

    def test_lista_vacia_aplicar_es_fallo_definitivo(self):
        self.assertFalse(self._accion("aplicar", indices=[0]).ok)

    def test_ampliar_sin_busqueda_previa_es_fallo(self):
        tr = self._accion("ampliar")
        self.assertFalse(tr.ok)
        self.assertIn("No hay una búsqueda de imágenes previa", tr.detalle_error)

    def test_expandir_sin_imagen_disponible_es_fallo(self):
        self.assertFalse(self._accion("expandir", indices=[3]).ok)

    def test_accion_no_reconocida_es_fallo_de_parametro(self):
        self.e._resultados_visuales = [{"url": "https://x.test/a.jpg"}]
        tr = self._accion("recortar")
        self.assertFalse(tr.ok)
        self.assertIn("mensaje_invalido", tr.detalle_error)
        self.assertEqual((False, "param", False), veredicto(self.e, tr))

    def test_el_mensaje_no_se_repite_al_orquestador(self):
        """Ya lo dijo la capacidad: el mensaje del paso queda vacío y el
        texto viaja en detalle_error, para no hablarlo dos veces."""
        tr = self._accion("limpiar")
        self.assertTrue(tr.ok)
        self.assertEqual(tr.mensaje, "")
        self.assertEqual(self.hablado, ["Listo, las quité."])

    def test_limitar_indices_vacios_es_fallo(self):
        self.e._resultados_visuales = [{"url": "https://x.test/a.jpg"}]
        tr = self._accion("descargar", indices=[99])
        self.assertFalse(tr.ok)
        self.assertIn("No tengo esa imagen disponible", tr.detalle_error)

    def test_index_fuera_de_rango_en_wallpaper_por_sesion_es_fallo(self):
        self.e._resultados_visuales = [{"url": "https://x.test/a.jpg"}]
        self.assertFalse(self._accion("wallpaper", indices=[7]).ok)


class PruebasTvNoEsMia(unittest.TestCase):
    """None en TV significa «esta frase no la reconozco», no «hecho»."""

    def test_config_tv_valida_sigue_dando_un_mensaje(self):
        e = EjecutorHerramientas()
        msg = e._manejar_config_tv("la ip de mi tele es 192.168.1.62")
        self.assertIsInstance(msg, str)
        self.assertTrue(msg, "la configuración válida no dijo nada")

    def test_el_camino_de_voz_sigue_recibiendo_none(self):
        """Ceder el turno al intérprete depende de que None siga siendo
        None dentro del ejecutor; solo la herramienta lo traducía."""
        e = EjecutorHerramientas()
        self.assertIsNone(e._manejar_control_tv("reproduce música de jazz"))


class PruebasNegativaSeguridad(unittest.TestCase):
    def test_usa_la_frase_del_orquestador_si_se_inyecta(self):
        e = EjecutorHerramientas(servicios=Servicios(
            frase_bloqueado=lambda: "Lo siento señor, no puedo hacer eso."))
        self.assertEqual(e._frase_comando_bloqueado(),
                         "Lo siento señor, no puedo hacer eso.")

    def test_sin_hook_conserva_la_persona(self):
        e = EjecutorHerramientas()
        self.assertIn("señor", e._frase_comando_bloqueado())

    def test_el_hook_roto_no_deriva_en_exito(self):
        def rota():
            raise RuntimeError("sin cerebro")
        e = EjecutorHerramientas(servicios=Servicios(frase_bloqueado=rota))
        self.assertIn("señor", e._frase_comando_bloqueado())


class PruebasInvestigacionSinFuentes(unittest.TestCase):
    def test_como_herramienta_sin_fuentes_es_fallo(self):
        e = EjecutorHerramientas()
        with patch.object(e, "_buscar_resultados_web", return_value=[]):
            raw = e.investigar_a_fondo("algo")
        self.assertIn("No encontré resultados", raw)
        self.assertFalse(veredicto(e, raw)[0], raw)

    def test_el_recolector_interno_devuelve_none_sin_fuentes(self):
        """buscar_web trata el valor como material de síntesis si es
        verdadero: un fallo no puede llegar a escribirse en el prompt."""
        e = EjecutorHerramientas()
        with patch.object(e, "_buscar_resultados_web", return_value=[]):
            self.assertIsNone(e._investigar_interno("algo"))

    def test_el_recolector_interno_devuelve_texto_con_fuentes(self):
        e = EjecutorHerramientas()
        fuentes = [{"title": "paisaje", "href": "https://x.test/a",
                    "body": "un cuerpo"}]
        with patch.object(e, "_buscar_resultados_web", return_value=fuentes):
            with patch.object(e, "_obtener_texto_pagina", return_value="texto"):
                self.assertTrue(e._investigar_interno("paisaje"))


class PruebasPrefijosNoDiverjan(unittest.TestCase):
    """El ejecutor tiene que conocer al menos los fallos del núcleo.

    Se compara por AST, sin importar el núcleo: esta suite debe poder
    correr sin DarkNucleo.
    """

    def _prefijos(self, ruta, nombre):
        import ast
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign) and any(
                    getattr(t, "id", None) == nombre for t in nodo.targets):
                return {e.value for e in nodo.value.elts}
        return set()

    def test_el_ejecutor_no_redefine_los_prefijos_en_su_casa(self):
        """Antes esta prueba comparaba las dos copias y exigía que fueran
        equivalentes. Desde que `contratos` las declara, lo que hay que vigilar
        es que el ejecutor no vuelva a definirlas módulo arriba: la igualdad de
        las dos listas ya no es un asunto de conteos, es un solo objeto
        (`tests/test_una_sola_lista_de_prefijos.py`).
        """
        for nombre in ("PREFIJOS_NO_REINTENTABLES", "PREFIJOS_FALLO_TRANSITORIO"):
            self.assertEqual(
                set(), self._prefijos(
                    "dark_python/herramientas/internas/ejecutor.py", nombre),
                "el ejecutor volvió a declarar %s" % nombre)


if __name__ == "__main__":
    unittest.main(verbosity=2)
