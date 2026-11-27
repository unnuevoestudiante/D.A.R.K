"""Pruebas del perfil gradual, el prompt dinámico y la Guardia de voz."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.identidades.cerebro import Cerebro  # noqa: E402
from nucleo.memoria.contexto import ContextoSesion, Memoria  # noqa: E402
from nucleo.identidades.guardia import GuardiaHabla, sanear  # noqa: E402
from nucleo.identidades.perfil import PerfilConductual  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo import dark_nucleo as dark_nucleo_mod  # noqa: E402
from nucleo.identidades.personalidad import (  # noqa: E402
    _probabilidad_forma_b, dar_forma_resultado, decir,
)
from nucleo.identidades.frases import (  # noqa: E402
    AUTOCONTENIDAS, FRASES, RETOMAR, donde_esta,
)
from proveedores.llm.fabrica import crear_proveedor_chat  # noqa: E402
from herramientas.internas import ejecutor as ejecutor_mod  # noqa: E402
from herramientas.internas.ejecutor import (  # noqa: E402
    EjecutorHerramientas, Servicios,
)


class PruebasIdentidad(unittest.TestCase):
    def test_cerebro_elige_el_banco_del_especialista_enfocado(self):
        cerebro = Cerebro.__new__(Cerebro)
        cerebro.especialista_enfocado = "tareas"
        cerebro.estado = Mock(return_value={"nivel": "medio", "modo": "normal"})
        cerebro.perfil_conductual = None
        cerebro.registrar_salida = Mock()
        with patch("nucleo.identidades.cerebro.decir", return_value="frase de tareas") as decir_mock:
            self.assertEqual(cerebro.responder("especialista_hueco", decision="datos"),
                             "frase de tareas")
        self.assertEqual(decir_mock.call_args.args[0], "tareas_hueco")
        self.assertEqual(decir_mock.call_args.kwargs["decision"], "datos")

        cerebro.especialista_enfocado = None
        with patch("nucleo.identidades.cerebro.decir", return_value="frase general") as decir_mock:
            self.assertEqual(cerebro.responder("especialista_hueco"), "frase general")
        self.assertEqual(decir_mock.call_args.args[0], "comando_en_camino")

    def perfil_temporal(self, directorio):
        return PerfilConductual.cargar(
            str(Path(directorio) / "dark_perfil_conductual.json"))

    def test_usuario_cansado_modula_suavemente_brevedad_y_profundidad(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directorio:
            perfil = self.perfil_temporal(directorio)
            perfil.actualizar("usuario_cansado")
            self.assertAlmostEqual(perfil.brevedad, 0.65)
            self.assertAlmostEqual(perfil.profundidad, 0.45)
            self.assertAlmostEqual(perfil.cercania, 0.55)
            self.assertEqual(perfil.humor, 0.0)
            recuperado = PerfilConductual.cargar(perfil.ruta_persistencia)
            self.assertAlmostEqual(recuperado.brevedad, 0.65)

    def test_decaimiento_temporal_devuelve_a_la_base(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directorio:
            perfil = self.perfil_temporal(directorio)
            perfil.brevedad = 0.65
            perfil.ultima_interaccion = 1000
            perfil.decaimiento_temporal(1000 + 86400)
            self.assertAlmostEqual(perfil.brevedad, 0.6)

    def test_archivo_corrupto_usa_las_tendencias_base(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directorio:
            ruta = Path(directorio) / "perfil.json"
            ruta.write_text("esto no es JSON", encoding="utf-8")
            perfil = PerfilConductual.cargar(str(ruta))
            self.assertEqual(perfil.cercania, 0.5)
            self.assertEqual(perfil.humor, 0.0)

    def test_nucleo_actualiza_tendencia_solo_ante_estado_expresado(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        perfil = Mock()
        nucleo.cerebro = SimpleNamespace(perfil_conductual=perfil)
        evento = DarkNucleo._actualizar_perfil_conductual(
            nucleo, "Estoy cansado")
        self.assertEqual(evento, "usuario_cansado")
        perfil.actualizar.assert_called_once_with("usuario_cansado")

    def test_prompt_dinamico_incluye_preferencia_de_brevedad_y_contexto(self):
        perfil = PerfilConductual(brevedad=0.9)
        prompt = Cerebro.generar_prompt_dinamico(perfil, "Contexto de sesión")
        self.assertIn(
            "El usuario está ocupado. Sé extremadamente breve, de una sola frase.",
            prompt,
        )
        self.assertIn("Contexto de sesión", prompt)

    def test_perfil_base_no_convierte_tendencias_en_guiones_rigidos(self):
        prompt = Cerebro.generar_prompt_dinamico(
            PerfilConductual(), "Contexto mínimo")
        self.assertNotIn("extremadamente breve", prompt)
        self.assertNotIn("paso a paso", prompt)

    def test_guardia_quita_nombre_y_cierre_de_ofrecimiento(self):
        frase, _ = sanear("Hola Samuel, ¿en qué puedo ayudarte?")
        resultado = GuardiaHabla(log=False).filtrar(
            "Hola Samuel, ¿en qué puedo ayudarte?")
        seguro = resultado or frase or ""
        self.assertNotIn("Samuel", seguro)
        self.assertNotIn("¿en qué puedo ayudarte", seguro.lower())

    def test_guardia_permite_usted_y_conserva_los_demas_filtros(self):
        casos = (
            (
                "No tengo necesidad de compañía adicional, señor; "
                "mi función es asistirle a usted.",
                "No tengo necesidad de compañía adicional, señor; "
                "mi función es asistirle a usted.",
            ),
            (
                "¿En qué puedo ayudarle, señor?",
                "¿En qué puedo ayudarle, señor?",
            ),
            ("¿En qué puedo ayudarle?", None),
            ("¿En qué más puedo ayudarle?", None),
            ("Estoy aquí para ayudarle.", None),
            ("¿Necesita usted algo más?", "¿Necesita usted algo más?"),
            ("Esto es para usted.", "Esto es para usted."),
            ("No quiero que lo haga por usted.", "No quiero que lo haga por usted."),
            (
                "Le agradezco que lo haya hecho por usted.",
                "Le agradezco que lo haya hecho por usted.",
            ),
            ("Con gusto, señor; lo reviso.", "Señor; lo reviso."),
            ("Dime qué te pareció.", "Dígame qué le pareció."),
            ("¿Y tú?", None),
            ("No puedo realizar acciones como abrir o cerrar aplicaciones.", None),
            ("La solicitud fue enviada al especialista de tareas.", None),
            ("El archivo está listo, señor.", "El archivo está listo, señor."),
        )

        for frase, esperado in casos:
            with self.subTest(frase=frase):
                resultado, _ = sanear(frase)
                self.assertEqual(resultado, esperado)

    def test_frase_autocontenida_no_anade_un_cierre(self):
        perfil = PerfilConductual(cercania=0.2, seriedad=0.3,
                                  espontaneidad=0.1)
        frase = FRASES["app_ok"][0]
        with patch(
            "nucleo.identidades.personalidad.random.choice",
            return_value=frase,
        ):
            resultado = decir("app_ok", app="Spotify", perfil=perfil)
        self.assertIn("app_ok", AUTOCONTENIDAS)
        self.assertEqual(resultado, frase.format(app="Spotify"))
        self.assertEqual(_probabilidad_forma_b(perfil), 1.0)

    def test_frase_autocontenida_solo_anade_retomar_si_hay_hilo(self):
        frase = FRASES["musica_ok"][0]
        retomar = RETOMAR[0].format(hilo="el documento")
        with patch(
            "nucleo.identidades.personalidad.random.choice",
            side_effect=[frase, RETOMAR[0]],
        ):
            resultado = decir("musica_ok", hilo="el documento")
        self.assertEqual(resultado, f"{frase} {retomar}")

    def test_archivo_usa_ubicacion_humana_y_placeholder_seguro(self):
        self.assertEqual(
            donde_esta(r"C:\Users\samue\Desktop\Facturas\informe.pdf"),
            "en la carpeta Facturas del escritorio",
        )
        with patch(
            "nucleo.identidades.personalidad.random.choice",
            return_value=FRASES["archivo_ok"][1],
        ):
            resultado = decir("archivo_ok", archivo="informe.pdf")
        self.assertIn("está eso", resultado)

    def test_guardia_descarta_narracion_de_proceso_y_pide_repetir(self):
        guardia = GuardiaHabla(log=False)
        resultado = guardia.filtrar(
            "La solicitud fue enviada al especialista de tareas.")
        self.assertIsNone(resultado)
        self.assertEqual(guardia.clave_de_respaldo(), "no_entendi")

    def test_brevedad_alta_siempre_conserva_forma_a(self):
        perfil = PerfilConductual(brevedad=0.9)
        resultado = dar_forma_resultado("Listo.", perfil=perfil)
        self.assertEqual(resultado, "Listo.")
        self.assertEqual(_probabilidad_forma_b(perfil), 0.0)

    def test_contexto_no_asume_trabajo_si_no_hay_actividad_reciente(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directorio:
            memoria = Memoria(str(Path(directorio) / "memoria.json"))
            contexto = ContextoSesion(memoria=memoria)
            contexto.app_actual = "code.exe"
            with patch("nucleo.memoria.contexto.segundos_inactivo", return_value=150):
                prompt = contexto.contexto_para_prompt()
        self.assertIn("no asumir que el usuario está trabajando", prompt)
        self.assertNotIn("App en pantalla con actividad reciente: VS Code", prompt)

    def test_guardia_conserva_el_trato_y_el_ofrecimiento_del_mayordomo(self):
        resultado = GuardiaHabla(log=False).filtrar(
            "Listo. ¿Necesita algo más, señor?")
        self.assertIn("señor", resultado.lower())
        self.assertIn("¿Necesita algo más", resultado)

    def test_busqueda_web_no_abre_navegador_y_reutiliza_modelo_residente(self):
        # El nombre decía «abre navegador» porque `buscar_web` abría Google antes
        # de sintetizar. Desde K.3.1 `investigar` no toca el navegador; lo que
        # sigue siendo cierto es que reutiliza el modelo residente y su timeout.
        # El cuerpo se fue al dueño de capacidades, así que el doble es el dueño.
        # La preparación del modelo se inyecta de verdad —es el método del núcleo
        # que la hace— para que el `asegurar` parcheado sea el mismo que se mide:
        # sin él, «no carga modelos» sería cierto por vacío.
        e = EjecutorHerramientas.__new__(EjecutorHerramientas)
        e._s = Servicios(preparar_modelo=lambda modelo:
                         DarkNucleo._preparar_modelo_de_trabajo(
                             SimpleNamespace(), modelo))
        e._llm_lock = threading.Lock()
        respuesta = Mock(status_code=200)
        respuesta.json.return_value = {
            "message": {"content": "Einstein desarrolló la relatividad."}}
        e._http = Mock()
        e._http.post.return_value = respuesta
        e._llm_provider = crear_proveedor_chat(session=e._http)
        e._buscar_resultados_web = Mock(return_value=[{
            "title": "Einstein", "body": "Físico alemán.",
            "href": "https://example.test/einstein",
        }])
        e._investigar_interno = Mock(return_value=None)
        e._ultimos_resultados = None
        with patch("webbrowser.open") as abrir:
            with patch.object(dark_nucleo_mod.broker, "asegurar") as asegurar:
                # Ningún modelo está residente: así el método real recorre su
                # lista y, si llamara a `asegurar`, el patch lo vería.
                with patch.object(dark_nucleo_mod.broker, "esta_cargado",
                                  Mock(return_value=False)):
                    resultado = e.investigar("Albert Einstein")
        abrir.assert_not_called()
        asegurar.assert_not_called()
        self.assertIn("relatividad", resultado)
        self.assertIn("https://example.test/einstein", resultado)
        payload = e._http.post.call_args.kwargs["json"]
        self.assertEqual(payload["keep_alive"], ejecutor_mod.KEEP_ALIVE_MODELO)
        self.assertEqual(e._http.post.call_args.kwargs["timeout"], (5, 60))

    def test_busqueda_web_usa_frase_fija_con_tema_y_sintesis(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(return_value="Sobre datos encontré información."))
        intencion = SimpleNamespace(
            action="investigar", params_planos=lambda: {"query": "datos"})
        sintesis = "La búsqueda encontró tres fuentes relevantes."
        texto = DarkNucleo._narrar_resultado(nucleo, sintesis, intencion)
        self.assertEqual(texto, "Sobre datos encontré información.")
        nucleo.cerebro.responder.assert_called_once_with(
            "busqueda_lista",
            extra=False,
            tema="datos",
            sintesis=sintesis,
        )

    def test_musica_usa_frase_distinta_en_reproducciones_consecutivas(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(side_effect=["primera", "siguiente", "detenida", "primera"]))
        intencion = SimpleNamespace(
            action="reproducir_musica", params_planos=lambda: {})
        self.assertEqual(
            DarkNucleo._narrar_resultado(nucleo, "Reproduciendo canción.", intencion),
            "primera",
        )
        self.assertEqual(
            DarkNucleo._narrar_resultado(nucleo, "Reproduciendo otra canción.", intencion),
            "siguiente",
        )
        detener = SimpleNamespace(
            action="detener_musica", params_planos=lambda: {})
        self.assertEqual(
            DarkNucleo._narrar_resultado(nucleo, "Música detenida.", detener),
            "detenida",
        )
        self.assertEqual(
            DarkNucleo._narrar_resultado(nucleo, "Reproduciendo canción.", intencion),
            "primera",
        )
        self.assertEqual(
            [llamada.args[0] for llamada in nucleo.cerebro.responder.call_args_list],
            ["musica_ok", "musica_cambio", "musica_stop", "musica_ok"],
        )

    def test_resultados_de_archivo_documento_y_descarga_incluyen_datos(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            responder=Mock(side_effect=["archivo", "documento", "descarga"]))
        acciones = [
            (
                "buscar_archivo",
                "Archivos encontrados:\n- C:\\Users\\samue\\Desktop\\Facturas\\informe.pdf",
                {"nombre": "informe"},
            ),
            (
                "escribir_documento",
                "Documento generado y guardado en: C:\\Users\\samue\\Documents\\reporte.md",
                {"tema": "ventas"},
            ),
            (
                "descargar_archivo",
                "Descargado en C:\\Users\\samue\\Downloads\\app.exe (1.0MB).",
                {},
            ),
        ]
        for accion, mensaje, params in acciones:
            intencion = SimpleNamespace(
                action=accion, params_planos=lambda params=params: params)
            DarkNucleo._narrar_resultado(nucleo, mensaje, intencion)
        llamadas = nucleo.cerebro.responder.call_args_list
        self.assertEqual(llamadas[0].args[0], "archivo_ok")
        self.assertEqual(llamadas[0].kwargs["donde"], "en la carpeta Facturas del escritorio")
        self.assertEqual(llamadas[1].args[0], "documento_listo")
        self.assertEqual(llamadas[1].kwargs["tema"], "ventas")
        self.assertEqual(llamadas[1].kwargs["donde"], "en documentos")
        self.assertEqual(llamadas[2].args[0], "descarga_ok")
        self.assertEqual(llamadas[2].kwargs["archivo"], "app.exe")

    def test_cautela_de_madrugada_depende_de_seriedad_y_aumento(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.cerebro = SimpleNamespace(
            perfil_conductual=SimpleNamespace(seriedad=0.9))
        nucleo.esp_comunicacion = Mock()
        intencion = SimpleNamespace(
            action="ajustar_volumen_musica",
            params_planos=lambda: {"direccion": "subir"},
        )
        with patch.object(dark_nucleo_mod.datetime, "datetime", Mock()) as fecha:
            fecha.now.return_value.hour = 3
            self.assertTrue(DarkNucleo._requiere_cautela_por_horario(
                nucleo, intencion))
            nucleo.cerebro.perfil_conductual.seriedad = 0.7
            self.assertFalse(DarkNucleo._requiere_cautela_por_horario(
                nucleo, intencion))


if __name__ == "__main__":
    unittest.main()
