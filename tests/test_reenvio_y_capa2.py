"""K.3.3: el reenvío desde `abrir_aplicacion` y la capa 2 (el modelo propone un dominio).

Dos huecos que quedaron abiertos al cerrar K.3.2:

  * «abre Amazon» nombraba una app que no está instalada y se quedaba en
    «No encontré ninguna aplicación instalada que coincida con…». Desde aquí el
    orquestador, cuando ninguna app coincide, reenvía el nombre al banco como
    `abrir_en_navegador`. La intención sigue siendo `abrir_aplicacion`: el
    reenvío es una decisión de ejecución, no de emparejado.
  * entre la tabla y la búsqueda se encaja la capa 2: el modelo propone un
    DOMINIO (nunca una URL arbitraria), se pasa por la misma política de URL del
    punto 3 de K.3 y se comprueba LOCALMENTE que resuelve. Si no resuelve, o si
    hay duda, se busca el nombre en lugar de adivinar.

Ninguna prueba hace red ni DNS: `dominio_resuelve` recibe un `resolver`
inyectado, el proveedor de chat del dueño de capacidades va simulado y
`webbrowser.open` queda parcheado.
"""
from __future__ import annotations

import socket
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from herramientas.internas.ejecutor import EjecutorHerramientas, Servicios  # noqa: E402
from nucleo import sitios_web  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.intenciones.gestor import CAPACIDADES_NUCLEO, GestorIntenciones  # noqa: E402
from especialistas.especialista_comunicacion import (  # noqa: E402
    EspecialistaComunicacion,
)


def _intencion_abrir_aplicacion(nombre):
    return SimpleNamespace(
        action="abrir_aplicacion",
        params_planos=lambda: {"nombre": nombre},
        relaciones=[],
    )


def _nucleo_para_reenvio(*, coincide):
    especialista = Mock()
    especialista.aplicacion_coincide.return_value = coincide

    def despacho(tool, args, **kwargs):
        return ("Abriendo Amazon en el navegador."
                if tool == "abrir_en_navegador" else "Abriendo Amazon.")

    return SimpleNamespace(
        intencion=SimpleNamespace(_intenciones={}, _recientes=[]),
        esp_comunicacion=especialista,
        ejecutar_comando=Mock(side_effect=despacho),
        _anunciar_pre_accion=Mock(),
    )


def _especialista_sin_instaladas():
    """Un especialista con las tres búsquedas de disco vaciadas a mano."""
    esp = EspecialistaComunicacion.__new__(EspecialistaComunicacion)
    esp._apps_registry_path = None
    esp._cargar_registro_apps = Mock(return_value={})
    esp._buscar_acceso_directo = Mock(return_value=None)
    esp._buscar_app_registrada = Mock(return_value=None)
    esp._buscar_ejecutable_instalado = Mock(return_value=None)
    return esp


class PruebasReenvioDelOrquestador(unittest.TestCase):
    def test_sin_app_coincidente_reenvia_al_navegador(self):
        nucleo = _nucleo_para_reenvio(coincide=False)

        respuesta = DarkNucleo._despachar_intencion(
            nucleo, _intencion_abrir_aplicacion("Amazon"))

        self.assertEqual(respuesta, "Abriendo Amazon en el navegador.")
        nucleo.ejecutar_comando.assert_called_once_with(
            "abrir_en_navegador", {"consulta": "Amazon"},
            desde_modulo=False, ya_confirmado=False)

    def test_el_reenvio_lleva_el_contexto_de_quien_llamo(self):
        """Antes el reenvío llamaba al método y perdía las dos banderas.

        `abrir_en_navegador` no pide confirmación, así que hoy no cambia lo que
        se abre; lo que se fija es que el reenvío entra por la misma puerta que
        cualquier herramienta y no por un atajo que se salta el despacho.
        """
        nucleo = _nucleo_para_reenvio(coincide=False)

        DarkNucleo._despachar_intencion(
            nucleo, _intencion_abrir_aplicacion("Amazon"),
            desde_modulo=True, ya_confirmado=True)

        nucleo.ejecutar_comando.assert_called_once_with(
            "abrir_en_navegador", {"consulta": "Amazon"},
            desde_modulo=True, ya_confirmado=True)

    def test_con_app_coincidente_no_reenvia(self):
        nucleo = _nucleo_para_reenvio(coincide=True)

        respuesta = DarkNucleo._despachar_intencion(
            nucleo, _intencion_abrir_aplicacion("Spotify"))

        self.assertEqual(respuesta, "Abriendo Amazon.")
        nucleo.ejecutar_comando.assert_called_once_with(
            "abrir_aplicacion", {"nombre": "Spotify"},
            desde_modulo=False, ya_confirmado=False)

    def test_sin_nombre_no_reenvia(self):
        # «abre» a secas se queda en el mensaje humano de la aplicación: no hay
        # nada que abrir en el navegador y reenviarlo sería inventar un destino.
        nucleo = _nucleo_para_reenvio(coincide=False)

        DarkNucleo._despachar_intencion(nucleo, _intencion_abrir_aplicacion("   "))

        nucleo.ejecutar_comando.assert_called_once_with(
            "abrir_aplicacion", {"nombre": "   "},
            desde_modulo=False, ya_confirmado=False)

    def test_la_frase_sigue_siendo_abrir_aplicacion(self):
        # El reenvío es de ejecución: el emparejado no cambia, y con él se va la
        # afirmación de que «abre la marca X» termina en un callejón.
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "abre Amazon")

        self.assertEqual(resultado.action, "abrir_aplicacion")
        self.assertEqual(resultado.params_planos()["nombre"], "Amazon")

    def test_el_predicado_coincide_con_lo_que_hace_el_executor(self):
        esp = _especialista_sin_instaladas()
        esp._buscar_ejecutable_instalado = Mock(
            return_value=("Opera", r"C:\opera\opera.exe"))

        self.assertTrue(esp.aplicacion_coincide("opera"))

        esp2 = _especialista_sin_instaladas()
        self.assertFalse(esp2.aplicacion_coincide("pajarito-de-mi-barrio"))

    def test_utilidad_de_sistema_cuenta_como_app(self):
        # «abre el bloc de notas» no es una página: UTILIDADES_SISTEMA gana antes
        # de cualquier búsqueda y el reenvío no debe tocarlo.
        esp = _especialista_sin_instaladas()

        self.assertTrue(esp.aplicacion_coincide("bloc de notas"))
        esp._buscar_acceso_directo.assert_not_called()

    def test_el_predicado_no_abre_nada(self):
        esp = _especialista_sin_instaladas()
        modulo = "especialistas.especialista_comunicacion"

        with patch(f"{modulo}.subprocess.Popen") as popen:
            self.assertTrue(esp.aplicacion_coincide("notepad"))
            self.assertFalse(esp.aplicacion_coincide("pajarito"))
        popen.assert_not_called()

    def test_predicado_y_ejecutor_ven_lo_mismo(self):
        # La única defensa contra la deriva de los dos caminos: si el executor
        # dice «no encontré», el predicado tiene que decir exactamente lo mismo.
        esp = _especialista_sin_instaladas()
        self.assertFalse(esp.aplicacion_coincide("pajarito-de-mi-barrio"))
        with patch("especialistas.especialista_comunicacion.subprocess.Popen"):
            mensaje = esp.abrir_aplicacion("pajarito-de-mi-barrio")
        self.assertIn("No encontré", mensaje)

        esp = _especialista_sin_instaladas()
        esp._cargar_registro_apps = Mock(
            return_value={"spotify": r"C:\spotify\spotify.exe"})
        self.assertTrue(esp.aplicacion_coincide("spotify"))
        with patch("especialistas.especialista_comunicacion.subprocess.Popen"), \
                patch("especialistas.especialista_comunicacion.os.path.isfile",
                      return_value=True):
            mensaje = esp.abrir_aplicacion("spotify")
        self.assertIn("Abriendo", mensaje)


class PruebasCapa2EnElModulo(unittest.TestCase):
    def test_dominio_valido_acepta_desnudo_y_con_esquema(self):
        self.assertEqual(sitios_web.dominio_valido("pajarito.com"),
                          "pajarito.com")
        self.assertEqual(sitios_web.dominio_valido("https://pajarito.com"),
                          "pajarito.com")
        self.assertEqual(sitios_web.dominio_valido("  WWW.Pajarito.COM "),
                          "www.pajarito.com")
        # El modelo puede devolver una URL hecha: se queda el dominio y nada más.
        self.assertEqual(sitios_web.dominio_valido("https://pajarito.com/notas"),
                          "pajarito.com")

    def test_dominio_valido_rechaza_lo_que_no_es_un_dominio(self):
        for valor in ("javascript:alert(1)", "file:///C:/notas.txt",
                      "data:text/html,hola",
                      "https://usuario:clave@pajarito.com",
                      "pajarito", "notas.txt", "dos palabras.com", "",
                      None, "pajarito .com"):
            self.assertIsNone(sitios_web.dominio_valido(valor), valor)

    def test_extrae_el_dominio_de_la_respuesta_del_modelo(self):
        self.assertEqual(sitios_web.extraer_dominio("pajarito.com"),
                          "pajarito.com")
        self.assertEqual(sitios_web.extraer_dominio("  pajarito.com\n"),
                          "pajarito.com")
        self.assertEqual(sitios_web.extraer_dominio("Responde: pajarito.com"),
                          "pajarito.com")
        self.assertIsNone(sitios_web.extraer_dominio("NINGUNO"))
        self.assertIsNone(sitios_web.extraer_dominio("no estoy seguro"))
        self.assertIsNone(sitios_web.extraer_dominio(None))

    def test_la_capa_2_va_entre_la_tabla_y_la_busqueda(self):
        vista = []
        url, origen = sitios_web.resolver_destino(
            "Pajarito de mi barrio",
            sugerir=lambda texto: vista.append(texto) or "pajarito.com",
            resuelve=lambda dominio: True)

        self.assertEqual((url, origen), ("https://pajarito.com", "modelo"))
        self.assertEqual(vista, ["Pajarito de mi barrio"])

    def test_un_dominio_inventado_se_busca_en_lugar_de_abrirse(self):
        # El requisito firmado: comprobar localmente que resuelve. Lo que no
        # resuelve no se abre, aunque el modelo lo afirme.
        url, origen = sitios_web.resolver_destino(
            "Pajarito de mi barrio",
            sugerir=lambda texto: "pajarito-inventado-9k23.com",
            resuelve=lambda dominio: False)

        self.assertEqual(origen, "busqueda")
        self.assertTrue(url.startswith(sitios_web.DIRECCION_DE_BUSQUEDA))
        self.assertIn("Pajarito%20de%20mi%20barrio", url)

    def test_la_tabla_gana_a_la_capa_2(self):
        sugerir = Mock(return_value="otra.com")

        url, origen = sitios_web.resolver_destino(
            "youtube", sugerir=sugerir, resuelve=lambda dominio: True)

        self.assertEqual((url, origen),
                          ("https://www.youtube.com", "tabla"))
        sugerir.assert_not_called()

    def test_la_url_escrita_gana_a_todo(self):
        sugerir = Mock(return_value="otra.com")

        url, origen = sitios_web.resolver_destino(
            "https://pajarito.com/notas", sugerir=sugerir,
            resuelve=lambda dominio: True)

        self.assertEqual((url, origen), ("https://pajarito.com/notas", "url"))
        sugerir.assert_not_called()

    def test_sin_sugeridor_el_camino_de_k32_sigue_igual(self):
        self.assertEqual(sitios_web.resolver_destino("pajarito"),
                          (sitios_web.url_de_busqueda("pajarito"), "busqueda"))

    def test_la_duda_del_modelo_es_busqueda(self):
        for sugerir in (lambda texto: "NINGUNO",
                        lambda texto: "no estoy seguro",
                        lambda texto: None):
            url, origen = sitios_web.resolver_destino(
                "pajarito raro", sugerir=sugerir, resuelve=lambda dominio: True)
            self.assertEqual(origen, "busqueda")

        def falla(texto):
            raise RuntimeError("el modelo no responde")

        self.assertEqual(
            sitios_web.resolver_destino("pajarito raro", sugerir=falla,
                                         resuelve=lambda dominio: True)[1],
            "busqueda")

    def test_dominio_resuelve_usa_el_resolver_inyectado(self):
        self.assertTrue(sitios_web.dominio_resuelve(
            "pajarito.com", resolver=lambda *a, **k: [("x",)]))
        self.assertFalse(sitios_web.dominio_resuelve(
            "pajarito.com", resolver=lambda *a, **k: []))

        def no_existe(*a, **k):
            raise socket.gaierror("desconocido")

        self.assertFalse(sitios_web.dominio_resuelve(
            "pajarito-inventado.com", resolver=no_existe))

    def test_dominio_resuelve_no_toca_el_socket_cuando_hay_resolver(self):
        resolver = Mock(return_value=[("x",)])

        self.assertTrue(sitios_web.dominio_resuelve("pajarito.com",
                                                    resolver=resolver))
        self.assertEqual(resolver.call_args[0][0], "pajarito.com")

    def test_dominio_resuelve_rechaza_lo_que_no_es_un_dominio(self):
        resolver = Mock(return_value=[("x",)])
        for valor in ("", None, "pajarito", "notas.txt",
                      "https://pajarito.com/x", "user@pajarito.com",
                      "dos palabras.com"):
            self.assertFalse(sitios_web.dominio_resuelve(valor,
                                                          resolver=resolver), valor)
        resolver.assert_not_called()


class PruebasCapa2EnElEjecutor(unittest.TestCase):
    """La capa 2 vive en el dueño de capacidades, no en el núcleo.

    El modelo lo sigue poniendo el orquestador —llega por `Servicios`— y la
    política de la dirección sigue siendo `nucleo/sitios_web.py`. Lo que se mide
    aquí es que el dueño pregunta, que sin modelo preparado no pregunta, y que
    la página abierta es la que salió de esa consulta.
    """

    def ejecutor_con_modelo(self, *, contenido=None, status=200, preparado=True,
                            falla=False):
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios(preparar_modelo=Mock(return_value=preparado))
        ejecutor._llm_lock = threading.Lock()
        provider = Mock()
        if falla:
            provider.complete = Mock(side_effect=RuntimeError("sin modelo"))
        else:
            provider.complete = Mock(return_value=SimpleNamespace(
                status_code=status, content=contenido or ""))
        ejecutor._llm_provider = provider
        return ejecutor

    def ejecutor_que_abre(self, sugerido):
        ejecutor = EjecutorHerramientas.__new__(EjecutorHerramientas)
        ejecutor._s = Servicios()
        ejecutor._sugerir_dominio = Mock(return_value=sugerido)
        # El almacén real no se lee: lo que haya en `config/sitios_web.json`
        # mandaría sobre la tabla y el resultado dependería de la máquina.
        ejecutor._almacen_sitios_web = lambda: None
        return ejecutor

    def test_sugerir_dominio_devuelve_lo_que_dijo_el_modelo(self):
        ejecutor = self.ejecutor_con_modelo(contenido="pajarito.com")

        self.assertEqual(ejecutor._sugerir_dominio("Pajarito de mi barrio"),
                         "pajarito.com")
        solicitud = ejecutor._llm_provider.complete.call_args[0][0]
        system = solicitud.messages[0]["content"].lower()
        self.assertIn("dominio", system)
        self.assertLessEqual(solicitud.options["max_output_tokens"], 64)

    def test_sin_modelo_preparado_no_se_sugiere_nada(self):
        ejecutor = self.ejecutor_con_modelo(preparado=False)

        self.assertIsNone(ejecutor._sugerir_dominio("Pajarito de mi barrio"))
        ejecutor._llm_provider.complete.assert_not_called()

    def test_una_respuesta_mala_no_es_un_dominio(self):
        ejecutor = self.ejecutor_con_modelo(contenido="pajarito.com", status=500)
        self.assertIsNone(ejecutor._sugerir_dominio("Pajarito"))

        ejecutor = self.ejecutor_con_modelo(falla=True)
        self.assertIsNone(ejecutor._sugerir_dominio("Pajarito"))

    def test_sin_nombre_no_se_pregunta_al_modelo(self):
        ejecutor = self.ejecutor_con_modelo(contenido="pajarito.com")

        self.assertIsNone(ejecutor._sugerir_dominio("   "))
        ejecutor._llm_provider.complete.assert_not_called()

    def test_abrir_en_navegador_abre_el_dominio_que_resuelve(self):
        ejecutor = self.ejecutor_que_abre("pajarito.com")
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre), \
                patch("nucleo.sitios_web.dominio_resuelve",
                      lambda dominio, **k: True):
            mensaje = ejecutor.abrir_en_navegador("Pajarito de mi barrio")

        self.assertEqual(abre.call_args[0][0], "https://pajarito.com")
        self.assertIn("Pajarito de mi barrio", mensaje)

    def test_abrir_en_navegador_busca_si_el_dominio_no_resuelve(self):
        ejecutor = self.ejecutor_que_abre("pajarito-inventado.com")
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre), \
                patch("nucleo.sitios_web.dominio_resuelve",
                      lambda dominio, **k: False):
            ejecutor.abrir_en_navegador("Pajarito de mi barrio")

        self.assertTrue(
            abre.call_args[0][0].startswith(sitios_web.DIRECCION_DE_BUSQUEDA))

    def test_abrir_en_navegador_no_pregunta_al_modelo_si_la_tabla_coincide(self):
        ejecutor = self.ejecutor_que_abre("otra.com")
        abre = Mock(return_value=True)

        with patch("herramientas.internas.ejecutor.webbrowser.open", abre):
            ejecutor.abrir_en_navegador("YouTube")

        self.assertEqual(abre.call_args[0][0], "https://www.youtube.com")
        ejecutor._sugerir_dominio.assert_not_called()


if __name__ == "__main__":
    unittest.main()
