"""Pruebas de las acciones estructuradas que llegan desde el overlay."""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from especialistas.especialista_comunicacion import EspecialistaComunicacion  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
)


class PruebasAccionesUI(unittest.TestCase):
    def nuevo_nucleo(self, *, bloqueado=False):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._modo_bloqueado = bloqueado
        nucleo._resultados_visuales = [{"url": "https://example.test/imagen.jpg"}]
        nucleo.overlay = SimpleNamespace(estado=Mock(return_value="showing_results"))
        nucleo._imagenes_vistas = {"https://example.test/imagen.jpg"}
        nucleo._ultima_query_imagenes = "imagen"
        nucleo._intencion_imagenes = "descargar"
        nucleo._text_queue = Mock()
        nucleo._ocultar_resultados_visuales = Mock()
        nucleo._buscar_similares_a_indice = Mock(return_value="resultados")
        nucleo._instalar_wallpaper_indice = Mock(return_value="fondo")
        nucleo._descargar_imagen = Mock(return_value="descargada")
        nucleo._ejecutar_herramienta = Mock(return_value=SimpleNamespace(
            ok=True, estado="exito", mensaje="Descargada en Descargas/imagen.jpg"))
        # El doble es un especialista de verdad montado con `__new__` (igual que
        # `test_reenvio_y_capa2.py`) para que sus cuatro nombres sean las vistas
        # reales sobre el almacén compartido, no campos de un SimpleNamespace.
        especialista = EspecialistaComunicacion.__new__(EspecialistaComunicacion)
        especialista._sesion = nucleo.sesion
        nucleo.esp_comunicacion = especialista
        nucleo.speak = Mock()
        self._neutralizar_tambien_el_dueño(nucleo)
        return nucleo

    def _neutralizar_tambien_el_dueño(self, nucleo):
        """Los mismos dobles, en dos hosts: el núcleo y el dueño de capacidades.

        Mientras el núcleo tenga sus cuerpos del cluster, los del dueño no los
        llama nadie; se montan porque el corte los pone a trabajar. Cada doble es
        EL MISMO objeto en los dos hosts, así que las aserciones de abajo valen
        antes y después de conmutar y el corte no puede colarse cambiando quién
        cuenta la llamada. Sin esto, en cuanto el núcleo delegue, la suite
        descargaría imágenes de verdad y le cambiaría el fondo al escritorio.

        El dueño se construye al final, a propósito: `overlay` y la sesión viajan
        por inyección en cuanto existe, y las dos tienen que ser las de este doble.
        """
        dueño = nucleo._capacidades_herramientas()
        for nombre in ("_ocultar_resultados_visuales", "_ampliar_imagenes",
                       "_descargar_imagen", "_descargar_todas_las_imagenes",
                       "_instalar_wallpaper_indice", "_buscar_similares_a_indice",
                       "instalar_wallpaper"):
            doble = getattr(nucleo, nombre, None)
            if not isinstance(doble, Mock):
                # El núcleo no lo dobla porque nadie lo alcanza por aquí; basta
                # con que el dueño tampoco pueda tocar el disco.
                doble = Mock(return_value="")
            setattr(dueño, nombre, doble)
        return dueño

    def test_el_dueño_queda_neutralizado_con_los_dobles_del_nucleo(self):
        """El mismo doble en los dos hosts: preguntar al dueño cuenta aquí."""
        nucleo = self.nuevo_nucleo()
        dueño = nucleo._capacidades_herramientas()
        self.assertIs(dueño._ocultar_resultados_visuales,
                      nucleo._ocultar_resultados_visuales)
        self.assertIs(dueño._descargar_imagen, nucleo._descargar_imagen)
        self.assertIs(dueño._instalar_wallpaper_indice,
                      nucleo._instalar_wallpaper_indice)
        self.assertIs(dueño.sesion, nucleo.sesion)

    def test_select_result_descarga_por_el_despachador_de_herramientas(self):
        nucleo = self.nuevo_nucleo()

        DarkNucleo._encolar_texto_manual(
            nucleo,
            '{"action":"select_result","index":0,"mode":"download"}')

        nucleo._ejecutar_herramienta.assert_called_once()
        self.assertEqual(
            nucleo._ejecutar_herramienta.call_args.args[:2],
            ("descargar_imagen", {"indice": 0}),
        )
        self.assertEqual(
            nucleo._ejecutar_herramienta.call_args.args[2],
            {"origen": "ui"},
        )
        self.assertIs(
            nucleo.esp_comunicacion._resultados_visuales,
            nucleo._resultados_visuales,
        )
        nucleo._descargar_imagen.assert_not_called()
        nucleo._text_queue.put.assert_not_called()

    def test_select_result_instala_wallpaper_por_el_despachador(self):
        nucleo = self.nuevo_nucleo()
        nucleo._ejecutar_herramienta.return_value = SimpleNamespace(
            ok=True, estado="exito",
            mensaje="Fondo de pantalla actualizado.")

        DarkNucleo._encolar_texto_manual(
            nucleo,
            '{"action":"select_result","index":0,"mode":"wallpaper"}')

        self.assertEqual(
            nucleo._ejecutar_herramienta.call_args.args[:2],
            ("instalar_wallpaper_indice", {"indice": 0}),
        )
        nucleo._instalar_wallpaper_indice.assert_not_called()
        nucleo._ocultar_resultados_visuales.assert_called_once_with()

    def test_select_result_busca_similares_sin_reinterpretar_texto(self):
        nucleo = self.nuevo_nucleo()

        with patch("builtins.print") as imprimir:
            DarkNucleo._encolar_texto_manual(
                nucleo,
                '{"action":"select_result","index":0,"mode":"similar"}')

        nucleo._buscar_similares_a_indice.assert_called_once_with(0)
        nucleo._ejecutar_herramienta.assert_not_called()
        nucleo._text_queue.put.assert_not_called()
        self.assertIn(
            "[UI_ACTION] action=_seleccionar_resultado_ui "
            "outcome=dispatched",
            imprimir.call_args.args[0],
        )

    def test_clear_results_se_ejecuta_como_accion_ui(self):
        nucleo = self.nuevo_nucleo()

        DarkNucleo._encolar_texto_manual(
            nucleo, '{"action":"clear_results"}')

        nucleo._ocultar_resultados_visuales.assert_called_once_with()
        nucleo._text_queue.put.assert_not_called()

    def test_accion_de_imagenes_pasa_por_el_despachador_de_herramientas(self):
        nucleo = self.nuevo_nucleo()
        nucleo._detectar_accion_imagenes = Mock(return_value={
            "tipo": "descargar", "indices": [0]})

        DarkNucleo._encolar_texto_manual(nucleo, "descarga la primera imagen")

        nucleo._ejecutar_herramienta.assert_called_once()
        self.assertEqual(
            nucleo._ejecutar_herramienta.call_args.args[:2],
            ("descargar_imagen", {"indice": 0}),
        )
        self.assertEqual(
            nucleo._ejecutar_herramienta.call_args.args[2],
            {"origen": "ui"},
        )
        nucleo._descargar_imagen.assert_not_called()

    def test_frase_conversacional_no_secuestro_imagenes_visibles(self):
        frase = (
            "dark, estas seguro de que no quieres un compañero? no me refiero "
            "a que sea necesario pero pues, no quiero que estes tan solo en mi "
            "computador y de hecho tener a dos asistentes podria ayudarme a mi "
            "tambien si lo piensas"
        )
        nucleo = self.nuevo_nucleo()
        nucleo.overlay.estado.return_value = "listening"
        nucleo._match_comando_menu = Mock(return_value=None)

        DarkNucleo._encolar_texto_manual(nucleo, frase)

        nucleo._text_queue.put.assert_called_once_with(frase)
        nucleo._ocultar_resultados_visuales.assert_not_called()
        nucleo.speak.assert_not_called()

    def test_frase_conversacional_no_secuestro_sin_lista_residual(self):
        frase = (
            "dark, estas seguro de que no quieres un compañero? no me refiero "
            "a que sea necesario pero pues, no quiero que estes tan solo en mi "
            "computador y de hecho tener a dos asistentes podria ayudarme a mi "
            "tambien si lo piensas"
        )
        nucleo = self.nuevo_nucleo()
        nucleo._resultados_visuales = None
        nucleo.overlay.estado.return_value = "listening"
        nucleo._match_comando_menu = Mock(return_value=None)

        DarkNucleo._encolar_texto_manual(nucleo, frase)

        nucleo._text_queue.put.assert_called_once_with(frase)
        nucleo._ocultar_resultados_visuales.assert_not_called()

    def test_limpieza_imagenes_requiere_referencia_o_pronombre_corto(self):
        for frase in ("ninguna", "quita las im\u00e1genes"):
            with self.subTest(frase=frase):
                nucleo = self.nuevo_nucleo()

                DarkNucleo._encolar_texto_manual(nucleo, frase)

                nucleo._ocultar_resultados_visuales.assert_called_once_with()
                nucleo._text_queue.put.assert_not_called()

    def test_dispatch_imagenes_no_actua_con_lista_residual_oculta(self):
        nucleo = self.nuevo_nucleo()
        nucleo.overlay.estado.return_value = "listening"

        DarkNucleo._despachar_accion_imagenes(
            nucleo, {"accion": "limpiar"})

        nucleo._ocultar_resultados_visuales.assert_not_called()
        nucleo.speak.assert_not_called()

    def test_intencion_de_imagenes_no_se_maneja_con_overlay_oculto(self):
        nucleo = self.nuevo_nucleo()
        nucleo.overlay.estado.return_value = "listening"
        nucleo.intencion = GestorIntenciones(CAPACIDADES_NUCLEO)
        nucleo.esp_conversacion = SimpleNamespace(temas=None)
        nucleo._silenciar_local = SimpleNamespace(activo=False)
        nucleo.cerebro = SimpleNamespace(ctx=None)
        nucleo.entidades = None
        #: Sin filtro semántico, la misma degradación que `__init__` si el ONNX no carga.
        nucleo.clasificador_semantico = None
        nucleo._traza_intencion_actual = None
        nucleo._actualizar_traza_intencion = Mock()

        manejada = DarkNucleo._manejar_con_intencion(nucleo, "ninguna")

        self.assertFalse(manejada)
        nucleo._ocultar_resultados_visuales.assert_not_called()
        nucleo.speak.assert_not_called()

    def test_menu_se_ejecuta_como_accion_ui(self):
        nucleo = self.nuevo_nucleo()
        nucleo._ejecutar_comando_menu = Mock()

        DarkNucleo._encolar_texto_manual(nucleo, "muestra recursos")

        nucleo._ejecutar_comando_menu.assert_called_once_with(
            "recursos", "muestra recursos")
        nucleo._text_queue.put.assert_not_called()

    def test_bloqueo_facial_impide_las_cuatro_salidas(self):
        casos = (
            '{"action":"select_result","index":0,"mode":"download"}',
            '{"action":"clear_results"}',
            "descarga la primera imagen",
            "muestra recursos",
        )
        for mensaje in casos:
            with self.subTest(mensaje=mensaje):
                nucleo = self.nuevo_nucleo(bloqueado=True)
                nucleo._detectar_accion_imagenes = Mock()
                nucleo._match_comando_menu = Mock()
                DarkNucleo._encolar_texto_manual(nucleo, mensaje)
                nucleo._ejecutar_herramienta.assert_not_called()
                nucleo._descargar_imagen.assert_not_called()
                nucleo._instalar_wallpaper_indice.assert_not_called()
                nucleo._ocultar_resultados_visuales.assert_not_called()
                nucleo._detectar_accion_imagenes.assert_not_called()
                nucleo._match_comando_menu.assert_not_called()
                nucleo._text_queue.put.assert_not_called()

    def test_acciones_ui_no_tienen_entrada_desde_modulos(self):
        firma = inspect.signature(DarkNucleo._accion_ui)
        self.assertNotIn("desde_modulo", firma.parameters)
        self.assertNotIn(
            inspect.Parameter.VAR_KEYWORD,
            {parametro.kind for parametro in firma.parameters.values()},
        )
        origen_modulos = inspect.getsource(DarkNucleo._procesar_peticion_modulo)
        self.assertIn("self.handle_command(texto, desde_modulo=True)", origen_modulos)
        self.assertNotIn("_encolar_texto_manual", origen_modulos)
        origen_overlay = inspect.getsource(DarkNucleo.__init__)
        self.assertIn("on_message=self._encolar_texto_manual", origen_overlay)
