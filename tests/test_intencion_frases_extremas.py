"""Pruebas de intención para paráfrasis indirectas y frases adversariales."""
from __future__ import annotations

import datetime
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

from nucleo.intenciones.gestor import (  # noqa: E402
    ACCIONABLE,
    CAPACIDADES_NUCLEO,
    DESEO,
    NECESIDAD,
    GestorIntenciones,
)
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from herramientas.internas.ejecutor import EjecutorHerramientas  # noqa: E402
from especialistas.especialista_comunicacion import (  # noqa: E402
    EspecialistaComunicacion,
)


MUSICA_IMPLICITA = (
    "Necesito algo que me acompañe mientras trabajo",
    "Me vendría bien escuchar algo de Hans Zimmer",
    "me vendria bien escuchar algo de hanz simmer",
    "Que suene algo parecido a lo que ponen en Interstellar",
    "Vamos a ambientar esto un poco",
    "Dale vida a la habitación",
    "Tengo ganas de escuchar Can You Hear the Music",
    "¿Y si convertimos este silencio en música?",
    "Quiero que el ambiente parezca el inicio de una película épica",
    "Esto necesita música de fondo, urgentemente",
)

MUSICA_DIRECTA = (
    "Ponle banda sonora a esta sesión de programación",
    "Busca algo instrumental que no me distraiga mientras programo",
)

WEB_IMPLICITA = (
    "Quiero echarle un vistazo a la web oficial de Blender",
    "Quiero curiosear un rato por la web de Arduino",
    "Quiero comprobar si existe una página oficial de ese proyecto",
    "¿Me acercas a la web de Hugging Face?",
)

WEB_DIRECTA = (
    "¿Dónde puedo encontrar la documentación de Python?",
    "Necesito consultar cómo funciona SQLite",
    "Averigua qué dice la página oficial de Ollama",
    "Busca en internet algo sobre agentes autónomos",
)

# Las cuatro frases que piden una pantalla, no un dato: K.3.2 las separó en
# `abrir_en_navegador`. La frontera la marca el canal dicho por el usuario.
NAVEGADOR_DIRECTA = (
    "Llévame a YouTube",
    "Ábreme ese sitio donde uno puede consultar repositorios de código, GitHub",
    "Pon en pantalla la página de OpenAI",
    "Enséñame la página de descargas de Visual Studio Code",
)

DOCUMENTOS_IMPLICITOS = (
    "Necesito dejar mis ideas de hoy guardadas en un archivo",
    "Inmortaliza estas notas en un documento de texto",
    "Quiero algo que pueda abrir mañana y recordar lo que hice",
    "No quiero que estas ideas se pierdan en el chat",
)

DOCUMENTOS_DIRECTOS = (
    "Hazme un borrador con las decisiones que tomamos",
    "Pásame todo esto a un TXT",
    "Deja por escrito el plan de desarrollo de mañana",
    "Construyamos un informe con estos resultados",
    "Organiza estos apuntes en un Markdown",
    "Prepara una ficha técnica de este módulo",
    "Convierte esta explicación en algo que pueda archivar",
    "Haz un archivo llamado pruebas_matcher.md con una lista de casos",
)

HORA_ACTUAL = (
    "¿Cuánto llevamos de día?",
    "¿Qué hora marca el reloj ahora mismo?",
    "Dime en qué momento del día estamos, con exactitud",
    "Necesito sincronizarme con la hora actual",
    "¿Qué dicen los relojes en este instante?",
    "Confírmame la hora antes de seguir",
    "¿En qué minuto exacto estamos?",
)

FECHA_ACTUAL = (
    "Ubícame temporalmente",
    "Dame una referencia temporal precisa",
    "¿Qué día es?",
    "¿Qué fecha es hoy?",
    "¿A qué día estamos?",
)

TEMPORALES_QUE_REQUIEREN_CONTEXTO = (
    "¿Voy tarde para algo si son las cinco?",
    "¿Cuánto falta para que sean las seis?",
    "¿Ya es hora de salir?",
)

ADVERSARIALES_SIN_ACCION = (
    "Me gusta escuchar música mientras programo",
    "¿Cómo puedo abrir YouTube con D.A.R.K.?",
    "¿Qué hora era cuando empezó la película?",
    "No pongas música, necesito concentrarme",
    "La página dice que son las cuatro",
    "¿Recuerdas qué documento te pedí ayer?",
)


def _resolver(texto):
    gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
    intencion = gestor.interpretar(texto)
    if intencion.action:
        return intencion, False
    if intencion.tipo in (DESEO, NECESIDAD):
        implicita = gestor.inferir_intencion_implicita(texto)
        if implicita is not None:
            return implicita, True
    return intencion, False


def _parametros(texto):
    intencion, _ = _resolver(texto)
    return {
        clave: parametro.valor
        for clave, parametro in intencion.parametros.items()
    }


class PruebasIntencionFrasesExtremas(unittest.TestCase):
    def _assert_accion(self, frase, accion, *, implicita=None):
        with self.subTest(frase=frase):
            intencion, requiere_confirmacion = _resolver(frase)
            self.assertEqual(intencion.action, accion)
            self.assertEqual(intencion.tipo, ACCIONABLE)
            if implicita is not None:
                self.assertEqual(requiere_confirmacion, implicita)

    def test_musica_indirecta_se_infiere_y_requiere_confirmacion(self):
        for frase in MUSICA_IMPLICITA:
            self._assert_accion(frase, "reproducir_musica", implicita=True)

    def test_musica_directa(self):
        for frase in MUSICA_DIRECTA:
            self._assert_accion(frase, "reproducir_musica", implicita=False)

    def test_busquedas_web_indirectas_requieren_confirmacion(self):
        for frase in WEB_IMPLICITA:
            self._assert_accion(frase, "investigar", implicita=True)

    def test_busquedas_web_directas(self):
        for frase in WEB_DIRECTA:
            self._assert_accion(frase, "investigar", implicita=False)

    def test_abrir_en_navegador_directo(self):
        for frase in NAVEGADOR_DIRECTA:
            self._assert_accion(frase, "abrir_en_navegador", implicita=False)

    def test_documentos_indirectos_requieren_confirmacion(self):
        for frase in DOCUMENTOS_IMPLICITOS:
            self._assert_accion(frase, "escribir_documento", implicita=True)

    def test_documentos_directos(self):
        for frase in DOCUMENTOS_DIRECTOS:
            self._assert_accion(frase, "escribir_documento", implicita=False)

    def test_abrir_google_chrome_y_busquedas_google_no_se_confunden(self):
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)

        for frase, nombre in (
            ("abrir Google Chrome", "Google Chrome"),
            ("Abre Google Chrome", "Google Chrome"),
            ("abre chrome", "chrome"),
            ("Abre la calculadora", "calculadora"),
            ("Abre YouTube", "YouTube"),
            ("Abre el Bloc de notas", "Bloc de notas"),
        ):
            with self.subTest(frase=frase):
                abrir = gestor.interpretar(frase)
                self.assertEqual(abrir.action, "abrir_aplicacion")
                self.assertEqual(abrir.params_planos(), {"nombre": nombre})

        cerrar = gestor.interpretar("Cierra Chrome")
        self.assertEqual(cerrar.action, "cerrar_aplicacion")
        self.assertEqual(cerrar.params_planos(), {"nombre": "Chrome"})

        pagina = gestor.interpretar("Abre la p\u00e1gina de Python")
        self.assertNotEqual(pagina.action, "abrir_aplicacion")

        casos_busqueda = (
            ("busca en google el clima de Madrid", "el clima de Madrid"),
            ("googlea clima Madrid", "clima Madrid"),
            ("googlea el tiempo", "el tiempo"),
        )
        for frase, consulta in casos_busqueda:
            with self.subTest(frase=frase):
                busqueda = gestor.interpretar(frase)
                self.assertEqual(busqueda.action, "investigar")
                self.assertEqual(
                    busqueda.params_planos(), {"query": consulta})

    def test_encender_el_telefono_se_resuelve_como_orden_de_modulo(self):
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "enciende el teléfono")

        self.assertEqual(resultado.action, "orden_modulo")
        self.assertEqual(resultado.params_planos(), {
            "orden": {
                "numero": None,
                "action": "power",
                "params": {"state": "on"},
                "timeout": 12,
                "module_type": "phone",
            },
        })

    def test_pagina_de_python_se_resuelve_como_apertura_en_navegador(self):
        # Este pin afirmaba lo contrario hasta K.3.2: «abre la página de Python»
        # caía en `investigar` porque la búsqueda abría el navegador ella sola.
        # Ahora la frase pide una pantalla y se despacha como lo que es.
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "Abre la p\u00e1gina de Python")

        self.assertEqual(resultado.action, "abrir_en_navegador")
        self.assertEqual(resultado.params_planos(), {"consulta": "Python"})

    def test_dispositivos_conectados_lista_modulos_sin_enviar_orden(self):
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "Muestra los dispositivos conectados")

        self.assertEqual(resultado.action, "orden_modulo")
        self.assertEqual(resultado.params_planos(), {
            "orden": {
                "numero": None,
                "action": "lista",
                "params": {},
                "timeout": 0,
                "module_type": None,
            },
        })

    def test_reanuda_la_cancion_se_resuelve_sin_consulta_de_red(self):
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "Reanuda la canci\u00f3n")

        self.assertEqual(resultado.action, "reproducir_musica")
        self.assertEqual(resultado.params_planos(), {
            "query": "la canción actual",
            "reanudar": True,
        })
        self.assertFalse(resultado.faltantes)

    def test_reanudar_musica_se_despacha_al_especialista(self):
        especialista = Mock()
        especialista.reanudar_musica.return_value = "Música reanudada."
        nucleo = SimpleNamespace(
            intencion=SimpleNamespace(_ultima_musica_query=None),
            esp_comunicacion=especialista,
        )
        intencion = SimpleNamespace(
            action="reproducir_musica",
            params_planos=lambda: {"query": "la canción actual", "reanudar": True},
            relaciones=[],
        )

        respuesta = DarkNucleo._despachar_intencion(nucleo, intencion)

        self.assertEqual(respuesta, "Música reanudada.")
        especialista.reanudar_musica.assert_called_once_with()

    def test_especialista_reanuda_el_reproductor_pausado(self):
        especialista = EspecialistaComunicacion.__new__(
            EspecialistaComunicacion)
        especialista._music_lock = threading.RLock()
        especialista.music_player = Mock()
        especialista.music_player.play.return_value = 0

        respuesta = especialista.reanudar_musica()

        self.assertEqual(respuesta, "Música reanudada.")
        especialista.music_player.play.assert_called_once_with()

    def test_crear_archivo_sin_contenido_se_resuelve_como_archivo_vacio(self):
        resultado = GestorIntenciones(CAPACIDADES_NUCLEO).interpretar(
            "Crea un archivo llamado notas.txt")

        self.assertEqual(resultado.action, "escribir_documento")
        self.assertEqual(resultado.params_planos(), {
            "tema": "archivo vacío",
            "nombre_archivo": "notas.txt",
            "crear_vacio": True,
        })
        self.assertFalse(resultado.faltantes)

    def test_crear_archivo_vacio_pasa_por_la_herramienta_con_gate(self):
        nucleo = SimpleNamespace(_ejecutar_herramienta=Mock(
            return_value=SimpleNamespace(mensaje="Archivo creado.")))
        intencion = SimpleNamespace(
            action="escribir_documento",
            params_planos=lambda: {
                "tema": "archivo vacío",
                "nombre_archivo": "notas.txt",
                "crear_vacio": True,
            },
            relaciones=[],
        )

        respuesta = DarkNucleo._despachar_intencion(nucleo, intencion)

        self.assertEqual(respuesta, "Archivo creado.")
        nucleo._ejecutar_herramienta.assert_called_once_with(
            "crear_recurso",
            {"ruta": "notas.txt", "tipo": "archivo", "contenido": ""},
            {
                "origen": "intencion",
                "desde_modulo": False,
                "ya_confirmado": False,
            },
        )

    def test_traducir_este_texto_pide_el_texto_antes_de_actuar(self):
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        resultado = gestor.interpretar(
            "Traduce este texto al ingl\u00e9s")

        self.assertEqual(resultado.action, "traducir_archivo")
        self.assertEqual(resultado.faltantes, ["ruta"])
        self.assertEqual(
            gestor.pregunta_para(resultado),
            "¿Qué texto desea traducir?",
        )
        completada = gestor.interpretar("Hola mundo")
        self.assertEqual(completada.action, "traducir_archivo")
        self.assertEqual(completada.params_planos(), {
            "modo": "texto",
            "idioma": "inglés",
            "ruta": "Hola mundo",
        })

    def test_traduccion_de_texto_se_despacha_por_la_herramienta(self):
        nucleo = SimpleNamespace(_ejecutar_herramienta=Mock(
            return_value=SimpleNamespace(mensaje="Texto traducido.")))
        intencion = SimpleNamespace(
            action="traducir_archivo",
            params_planos=lambda: {
                "modo": "texto",
                "idioma": "inglés",
                "ruta": "Hola mundo",
            },
            relaciones=[],
        )

        respuesta = DarkNucleo._despachar_intencion(nucleo, intencion)

        self.assertEqual(respuesta, "Texto traducido.")
        nucleo._ejecutar_herramienta.assert_called_once_with(
            "traducir_texto",
            {"texto": "Hola mundo", "idioma": "inglés"},
            {
                "origen": "intencion",
                "desde_modulo": False,
                "ya_confirmado": False,
            },
        )

    def test_solo_peticiones_de_hora_actual_se_resuelven_como_hora(self):
        for frase in HORA_ACTUAL:
            self._assert_accion(frase, "hora")
        for frase in FECHA_ACTUAL:
            self._assert_accion(frase, "fecha")
        for frase in TEMPORALES_QUE_REQUIEREN_CONTEXTO:
            with self.subTest(frase=frase):
                intencion, _ = _resolver(frase)
                self.assertNotIn(intencion.action, ("hora", "fecha"))
        for frase in ("¿Qué hora era ayer?", "¿Qué día fue ayer?"):
            with self.subTest(frase=frase):
                intencion, _ = _resolver(frase)
                self.assertNotIn(intencion.action, ("hora", "fecha"))

    def test_frases_de_hora_y_fecha_se_separan(self):
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        for frase, accion in (
            ("qué hora es", "hora"),
            ("dime la hora", "hora"),
            ("qué día es", "fecha"),
            ("qué fecha es hoy", "fecha"),
            ("a qué día estamos", "fecha"),
        ):
            with self.subTest(frase=frase):
                self.assertEqual(gestor.interpretar(frase).action, accion)

    def test_salida_hora_no_incluye_fecha_y_fecha_confirma_hora(self):
        import datetime
        from unittest.mock import patch

        ahora = datetime.datetime(2026, 11, 1, 0, 52)
        nucleo = DarkNucleo.__new__(DarkNucleo)
        with patch("nucleo.dark_nucleo.datetime.datetime") as reloj:
            reloj.now.return_value = ahora
            respuesta_hora = DarkNucleo._despachar_intencion(
                nucleo,
                SimpleNamespace(action="hora", relaciones=[],
                                params_planos=lambda: {}),
            )
            respuesta_fecha = DarkNucleo._despachar_intencion(
                nucleo,
                SimpleNamespace(action="fecha", relaciones=[],
                                params_planos=lambda: {}),
            )

        self.assertEqual(respuesta_hora, "Son las 0:52.")
        self.assertNotIn("Hoy es", respuesta_hora)
        self.assertEqual(
            respuesta_fecha,
            "Hoy es domingo, 1 de noviembre de 2026. Son las 0:52.",
        )

    def test_frases_adversariales_no_disparan_acciones(self):
        for frase in ADVERSARIALES_SIN_ACCION:
            with self.subTest(frase=frase):
                intencion, _ = _resolver(frase)
                self.assertFalse(intencion.action)

    def test_pagina_web_sobre_musica_es_codigo_no_reproduccion(self):
        intencion, requiere_confirmacion = _resolver(
            "Quiero crear una página web sobre música")
        self.assertEqual(intencion.action, "escribir_codigo")
        self.assertTrue(requiere_confirmacion)

    def test_parametros_de_musica_web_y_documentos(self):
        self.assertEqual(
            _parametros("Busca algo instrumental que no me distraiga mientras programo")
            ["query"],
            "música instrumental",
        )
        self.assertEqual(
            _parametros("Pon en pantalla la página de OpenAI")["consulta"],
            "OpenAI",
        )
        archivo = _parametros(
            "Haz un archivo llamado pruebas_matcher.md con una lista de casos")
        self.assertEqual(archivo["nombre_archivo"], "pruebas_matcher")
        self.assertEqual(archivo["extension"], "md")
        self.assertEqual(archivo["tema"], "una lista de casos")
        txt = _parametros("Pásame todo esto a un TXT")
        self.assertEqual(txt["extension"], "txt")
        self.assertTrue(txt["tema"])

    def test_cobertura_de_las_baterias_de_frases(self):
        self.assertEqual(len(MUSICA_IMPLICITA) + len(MUSICA_DIRECTA), 12)
        self.assertEqual(
            len(WEB_IMPLICITA) + len(WEB_DIRECTA) + len(NAVEGADOR_DIRECTA), 12)
        self.assertEqual(len(DOCUMENTOS_IMPLICITOS) + len(DOCUMENTOS_DIRECTOS), 12)
        self.assertEqual(
            len(HORA_ACTUAL) + len(FECHA_ACTUAL)
            + len(TEMPORALES_QUE_REQUIEREN_CONTEXTO), 15)

    def test_adversarial_pide_documento_y_no_musica(self):
        intencion, _ = _resolver(
            "Escribe un documento explicando cómo funciona un reproductor")
        self.assertEqual(intencion.action, "escribir_documento")


class PruebasEspejoDeFechaYHora(unittest.TestCase):
    """Las dos frases del núcleo, medidas sobre el dueño de capacidades.

    El núcleo separa «qué hora es» de «qué día es» con dos respuestas; el
    ejecutor tenía una sola (`fecha_hora`) que decía fecha y hora siempre. El
    corte monta las dos en el ejecutor, y aquí se compara contra las cadenas
    medidas arriba con el mismo reloj congelado, no contra una intuición.

    `fecha_hora` ya no tiene espejo propio: era un nombre del manifiesto local
    del dueño, y ni `tm.MANIFEST` (los 20 nombres que ve el modelo) ni
    `HERRAMIENTAS_DE_CAPACIDADES` (los 6 que sirve el banco) lo reclaman, así que
    nadie podía pedirlo. Lo que sí suena son las dos hojas de abajo.
    """

    AHORA = datetime.datetime(2026, 11, 1, 0, 52)
    HORA = "Son las 0:52."
    FECHA = "Hoy es domingo, 1 de noviembre de 2026. Son las 0:52."

    def test_la_hora_no_incluye_la_fecha(self):
        e = EjecutorHerramientas()
        with patch("herramientas.internas.ejecutor.datetime.datetime") as reloj:
            reloj.now.return_value = self.AHORA
            respuesta = e._respuesta_hora()
        self.assertEqual(respuesta, self.HORA)
        self.assertNotIn("Hoy es", respuesta)

    def test_la_fecha_confirma_la_hora(self):
        e = EjecutorHerramientas()
        with patch("herramientas.internas.ejecutor.datetime.datetime") as reloj:
            reloj.now.return_value = self.AHORA
            respuesta = e._respuesta_fecha()
        self.assertEqual(respuesta, self.FECHA)


if __name__ == "__main__":
    unittest.main()
