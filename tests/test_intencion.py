"""Regresión del matcher, el contexto y la ejecución de intención."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.intenciones.gestor import (  # noqa: E402
    AMBIGUO_PENDIENTE, CAPACIDADES_NUCLEO, GestorIntenciones,
)
from nucleo.intenciones.entidades import GestorEntidades  # noqa: E402
from nucleo.confirmacion import AlmacenConfirmacion  # noqa: E402
from nucleo.intenciones.normalizador import normalizar  # noqa: E402
from nucleo.dark_nucleo import DarkNucleo  # noqa: E402


FRASES_CAPACIDADES = {
    "hora": ["qué hora es", "dime la hora"],
    "fecha": ["qué día es hoy", "dime la fecha"],
    "abrir_archivo": ["abre config.py", "abrir notas.txt"],
    "buscar_imagenes": ["busca imágenes de gatos", "busca 5 wallpapers de montañas", "busca fotos de perros"],
    "abrir_en_navegador": ["abre la página de Python", "llévame a YouTube",
                           "busca en el navegador el manual de la cafetera"],
    "investigar": ["busca en internet sobre astronomía", "investiga en la web sobre Queen"],
    "guardar_sitio_web": ["guarda que mi banco es https://mi-banco.com",
                          "apunta el foro como sitio web foro-x.net"],
    "abrir_pagina_sitios": ["quiero agregar un nuevo link",
                            "añade una url nueva"],
    "conectar_servicio": ["oye dark, quiero agregar mi correo", "conecta mi gmail",
                          "dale acceso a mi correo electrónico",
                          "vincula mi cuenta de correo", "sincroniza mi bandeja de entrada",
                          "quiero agregar mi calendario", "conecta google drive",
                          "añade mis contactos de google"],
    "desconectar_servicio": ["desconecta mi correo", "ya no leas mi correo",
                             "quítale el acceso a mi calendario", "desvincula drive"],
    "estado_conexiones": ["qué tengo conectado", "cuáles son mis conexiones",
                          "qué cuentas tienes conectadas"],
    "buscar_archivo": ["busca config.py", "buscar archivo notas.txt"],
    "cambiar_nombre_archivo": ["cámbiale el nombre", "renómbrame el nombre"],
    "poner_wallpaper": ["poner de fondo", "pon la segunda como fondo", "usa esta imagen de fondo"],
    "ajustar_volumen_musica": ["baja el volumen", "pon el volumen en 30", "sube la música", "silencia el reproductor"],
    "detener_musica": ["detén la música", "pausa el reproductor"],
    "escribir_codigo": ["escribe una página web sobre gatos", "crea un script python para ordenar fotos", "haz una aplicación web"],
    "escribir_documento": ["escribe un documento sobre gatos", "escribe un ensayo sobre historia"],
    "seleccionar_resultado_web": ["opción dos resultado", "resultado tres enlace"],
    "abrir_aplicacion": ["abre spotify", "inicia opera", "lanza chrome"],
    "cerrar_aplicacion": ["cierra spotify", "termina el proceso de opera", "mata la aplicación chrome"],
    "reproducir_musica": ["pon música jazz", "poner la canción Bohemian Rhapsody", "reproduce Queen", "cambiar canción por rock", "toca jazz"],
    "traducir_archivo": ["traduce notas.txt al inglés", "traducir archivo manual.pdf al español"],
    "accion_imagenes": ["expande la tercera imagen", "descarga la primera imagen", "guarda la segunda imagen", "amplía la segunda imagen", "agranda la tercera foto"],
    "menu": ["muestra tareas", "muestra recursos", "crea un menú de tareas"],
    "orden_modulo": ["dile al teléfono que encienda la linterna", "enciende la linterna del teléfono", "dile a la tv que cambie de canal"],
}


class PruebasIntencion(unittest.TestCase):
    def nuevo_gestor(self):
        return GestorIntenciones(CAPACIDADES_NUCLEO)

    def test_busqueda_local_de_archivo_no_se_confunde_con_busqueda_web(self):
        casos = (
            ("busca config.py", {"nombre": "config.py"}),
            ("buscar archivo notas", {"nombre": "notas"}),
            ("buscar archivo notas.txt", {"nombre": "notas.txt"}),
        )
        for frase, parametros in casos:
            with self.subTest(frase=frase):
                resultado = self.nuevo_gestor().interpretar(frase)
                self.assertEqual(resultado.action, "buscar_archivo")
                self.assertEqual(resultado.params_planos(), parametros)

    def test_rechazo_de_todas_las_imagenes_no_se_convierte_en_busqueda(self):
        resultado = self.nuevo_gestor().interpretar("no quiero ninguna")
        self.assertEqual(resultado.action, "accion_imagenes")
        self.assertEqual(resultado.params_planos(), {"accion": "limpiar"})

    def test_limpiar_resultados_publica_payload_vacio_en_estado_activo(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._resultados_visuales = [{"url": "https://example.test/img.jpg"}]
        nucleo._imagenes_vistas = {"https://example.test/img.jpg"}
        nucleo._ultima_query_imagenes = "gatos"
        nucleo._intencion_imagenes = "wallpaper"
        nucleo._timer_ocultar_resultados = None
        nucleo.overlay = SimpleNamespace(estado=lambda: "speaking")
        nucleo._set_overlay = Mock()

        # Desde el escalón 3 el borrado lo ejecuta el dueño; lo que se prueba
        # aquí es que escribe en la MISMA sesión que lee el núcleo y que llama
        # a la fachada de presentación de arriba, no a una segunda. El dueño se
        # monta al final porque `overlay` viaja como valor.
        nucleo._capacidades_herramientas()._ocultar_resultados_visuales()

        self.assertIsNone(nucleo._resultados_visuales)
        # El dueño rellena los tres campos del payload en cada publicación, así
        # que `text` y `menu_data` llegan explícitos a la fachada del núcleo;
        # valen igual que el omisión porque `_set_overlay` los declara a None.
        nucleo._set_overlay.assert_called_once_with(
            "speaking",
            text=None,
            menu_data=None,
            results_data={
                "items": [],
                "carousel": False,
                "intencion": None,
                "query": "",
            },
        )

    def test_accion_clear_results_del_renderer_limpia_sin_entrar_al_chat(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._modo_bloqueado = False
        ocultar = Mock()
        nucleo._capacidades_herramientas()._ocultar_resultados_visuales = ocultar
        nucleo._text_queue = Mock()

        DarkNucleo._encolar_texto_manual(
            nucleo, '{"action":"clear_results"}')

        ocultar.assert_called_once_with()
        nucleo._text_queue.put.assert_not_called()

    def test_anticipa_reproducir_musica_desde_necesidad(self):
        resultado = self.nuevo_gestor().inferir_intencion_implicita(
            "necesito escuchar música de Michael Jackson")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.action, "reproducir_musica")
        self.assertTrue(resultado.implicita)

    def test_anticipa_abrir_aplicacion_desde_deseo(self):
        resultado = self.nuevo_gestor().inferir_intencion_implicita(
            "quiero abrir la calculadora")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.action, "abrir_aplicacion")

    def test_anticipa_buscar_archivo_desde_necesidad(self):
        resultado = self.nuevo_gestor().inferir_intencion_implicita(
            "necesito encontrar config.py")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.action, "buscar_archivo")

    def test_anticipa_consulta_de_hora(self):
        resultado = self.nuevo_gestor().inferir_intencion_implicita(
            "me gustaría saber qué hora es")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.action, "hora")

    def test_anticipa_busqueda_web_desde_necesidad(self):
        resultado = self.nuevo_gestor().inferir_intencion_implicita(
            "necesito buscar en internet sobre astronomía")
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado.action, "investigar")
        self.assertEqual(resultado.params_planos()["query"], "astronomía")

    def test_anticipacion_se_persiste_y_pide_confirmacion_antes_de_ejecutar(self):
        gestor = self.nuevo_gestor()
        intencion = gestor.inferir_intencion_implicita("quiero abrir la calculadora")
        gestor.esperar_confirmacion(intencion.id)
        self.assertIs(gestor.confirmacion_pendiente(), intencion)
        recuperada = type(intencion).from_dict(intencion.to_dict())
        self.assertTrue(recuperada.implicita)

    def test_nucleo_pregunta_antes_de_despachar_anticipacion(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.confirmaciones = AlmacenConfirmacion()
        nucleo.intencion = self.nuevo_gestor()
        nucleo.esp_conversacion = SimpleNamespace(temas=None)
        nucleo._silenciar_local = SimpleNamespace(activo=False)
        nucleo.cerebro = SimpleNamespace(
            ctx=None, responder=Mock(return_value="Puedo hacerlo por usted. ¿Le parece?"))
        nucleo.entidades = None
        #: `__init__` lo deja a `None` cuando el ONNX no carga: sin filtro, el
        #: matcher manda solo. El doble construido con `__new__` lo declara igual.
        nucleo.clasificador_semantico = None
        nucleo.speak = Mock()
        nucleo._despachar_intencion = Mock()

        manejado = DarkNucleo._manejar_con_intencion(
            nucleo, "quiero abrir la calculadora")

        self.assertTrue(manejado)
        self.assertEqual(nucleo.speak.call_args.args[0],
                         "Puedo hacerlo por usted. ¿Le parece?")
        self.assertEqual(nucleo.intencion.confirmacion_pendiente().action,
                         "abrir_aplicacion")
        self.assertTrue(nucleo.confirmaciones.hay_pendiente())
        nucleo._despachar_intencion.assert_not_called()

    def test_mas_de_cincuenta_frases_y_las_capacidades_declaradas(self):
        total = sum(map(len, FRASES_CAPACIDADES.values()))
        self.assertGreaterEqual(total, 50)
        self.assertEqual(set(FRASES_CAPACIDADES),
                         {c.nombre for c in CAPACIDADES_NUCLEO})
        for accion, frases in FRASES_CAPACIDADES.items():
            for frase in frases:
                with self.subTest(accion=accion, frase=frase):
                    resultado = self.nuevo_gestor().interpretar(frase)
                    self.assertEqual(resultado.action, accion)

    def test_regresiones_del_normalizador(self):
        casos = (
            ("pon el volumen en 30", "ajustar_volumen_musica", {"nivel": 30}),
            # "poner de fondo" sin temática y sin referirse a una tarjeta ya no
            # instala la primera: deja los params vacíos para que el Núcleo
            # pregunte la temática.
            ("poner de fondo", "poner_wallpaper", {}),
            ("poner la canción X", "reproducir_musica", {"query": "canción X"}),
        )
        for frase, accion, params in casos:
            with self.subTest(frase=frase):
                resultado = self.nuevo_gestor().interpretar(frase)
                self.assertEqual(resultado.action, accion)
                self.assertEqual(resultado.params_planos(), params)

    def test_poner_wallpaper_corta_sin_tema_con_tema_y_por_tarjeta(self):
        """params de `poner_wallpaper` sobre el texto canónico real.

        `normalizar()` no lematiza «usa», «coloca», «aplica» ni «establece»,
        así que las formas imperativas tienen que estar en la regex.
        """
        casos = (
            ("cambia mi fondo de pantalla", {}),
            ("cambiame el fondo", {}),
            ("quiero cambiar el fondo", {}),
            ("ponme otro fondo", {}),
            ("cambia el wallpaper", {}),
            ("coloca esta foto como fondo de pantalla", {"indice": 0}),
            ("ponme un fondo cyberpunk", {"tema": "cyberpunk"}),
            ("pon un fondo de pantalla de bosques", {"tema": "bosques"}),
            ("pon la segunda como fondo", {"indice": 1}),
            (r"usa C:\x\foto.jpg como fondo", {"url": r"C:\x\foto.jpg"}),
        )
        for frase, params in casos:
            with self.subTest(frase=frase):
                resultado = self.nuevo_gestor().interpretar(frase)
                self.assertEqual(resultado.action, "poner_wallpaper")
                self.assertEqual(resultado.params_planos(), params)

    def test_poner_wallpaper_no_le_roba_otras_capacidades(self):
        for frase, accion in (("pon música", "reproducir_musica"),
                              ("pon la segunda", "accion_imagenes"),
                              ("sube el volumen a 20",
                               "ajustar_volumen_musica")):
            with self.subTest(frase=frase):
                self.assertEqual(self.nuevo_gestor().interpretar(frase).action,
                                 accion)

    def test_normalizador_vocativos_modales_y_encliticos(self):
        self.assertEqual(normalizar("oye, podrías abrirme chrome, por favor"), "abrir chrome")
        self.assertEqual(normalizar("ciérralo"), "cerrar")
        self.assertEqual(normalizar("¿me gustaría que pongas música?"), "poner música")

    def test_correccion_entre_turnos_crea_undo(self):
        gestor = self.nuevo_gestor()
        anterior = gestor.interpretar("abre spotify")
        gestor.marcar_resuelta(anterior.id)
        nueva = gestor.interpretar("no, mejor abre chrome")
        self.assertEqual(nueva.action, "abrir_aplicacion")
        self.assertIn("deshacer", [r.tipo for r in nueva.relaciones])

    def test_correccion_en_el_mismo_turno(self):
        resultado = self.nuevo_gestor().interpretar(
            "busca imágenes de gatos, bueno, mejor busca imágenes de perros")
        self.assertEqual(resultado.action, "buscar_imagenes")
        self.assertEqual(resultado.params_planos()["query"], "perros")

    def test_correccion_fuerte_hasta_tres_turnos(self):
        gestor = self.nuevo_gestor()
        anterior = gestor.interpretar("abre spotify")
        gestor.marcar_resuelta(anterior.id)
        gestor.interpretar("hola")
        gestor.interpretar("gracias")
        nueva = gestor.interpretar("me refería a chrome")
        self.assertEqual(nueva.action, "abrir_aplicacion")
        self.assertEqual(nueva.params_planos().get("nombre"), "chrome")

    def test_referencias_a_sesion_y_entidades(self):
        gestor = self.nuevo_gestor()
        contexto = SimpleNamespace(app_actual="Spotify.exe")
        cierre = gestor.interpretar("ciérralo", ctx_sesion=contexto)
        self.assertEqual(cierre.action, "cerrar_aplicacion")
        self.assertEqual(cierre.params_planos()["nombre"], "Spotify")

        gestor = self.nuevo_gestor()
        entidades = GestorEntidades()
        gestor.interpretar("abre photoshop", ctx_entidades=entidades)
        self.assertEqual(gestor.interpretar("ábrelo", ctx_entidades=entidades)
                         .params_planos()["nombre"], "photoshop")

        gestor = self.nuevo_gestor()
        gestor.registrar_musica("Billie Jean")
        self.assertEqual(gestor.interpretar("otra vez").params_planos()["query"],
                         "Billie Jean")

    def test_no_deshacer_conserva_la_app_anterior(self):
        gestor = self.nuevo_gestor()
        anterior = gestor.interpretar("abre spotify")
        gestor.marcar_resuelta(anterior.id)
        nueva = gestor.interpretar("mejor abre chrome, no cierres spotify")
        self.assertEqual(nueva.action, "abrir_aplicacion")
        self.assertIn("no_deshacer", [r.tipo for r in nueva.relaciones])
        self.assertEqual(anterior.estado, "resuelta")

    def test_adicion_deja_vivas_las_dos_intenciones(self):
        gestor = self.nuevo_gestor()
        intenciones = gestor.interpretar("abre spotify y también abre chrome")
        anterior, nueva = intenciones
        self.assertEqual(anterior.estado, "pendiente")
        self.assertIn("adicion", [r.tipo for r in nueva.relaciones])

    def test_undo_musica_detiene_y_no_reproduce(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.esp_comunicacion = Mock()
        previa = self.nuevo_gestor().interpretar("pon música jazz")
        DarkNucleo._ejecutar_undo(nucleo, previa)
        nucleo.esp_comunicacion.detener_musica.assert_called_once_with()
        nucleo.esp_comunicacion.reproducir_musica.assert_not_called()

    def test_undo_volumen_usa_especialista(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.esp_comunicacion = Mock()
        previa = self.nuevo_gestor().interpretar("pon el volumen en 30")
        previa.estado_previo = 55
        DarkNucleo._ejecutar_undo(nucleo, previa)
        nucleo.esp_comunicacion.ajustar_volumen_musica.assert_called_once_with(nivel=55)

    def test_correccion_de_busqueda_de_imagenes_conserva_indice(self):
        gestor = self.nuevo_gestor()
        anterior = gestor.interpretar("busca 5 wallpapers de gatos")
        gestor.marcar_resuelta(anterior.id)
        corregida = gestor.interpretar("no, mejor la segunda")
        self.assertEqual(corregida.action, "accion_imagenes")
        self.assertEqual(corregida.params_planos(), {"accion": "aplicar", "indices": [1]})

    def test_expande_la_tercera_imagen(self):
        resultado = self.nuevo_gestor().interpretar("expande la tercera imagen")
        self.assertEqual(resultado.action, "accion_imagenes")
        self.assertEqual(resultado.params_planos(), {"accion": "expandir", "indices": [2]})

    def test_dispatch_imagenes_no_borra_memoria_al_aplicar_wallpaper(self):
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo._resultados_visuales = [{}, {}]
        nucleo.overlay = SimpleNamespace(estado=lambda: "showing_results")
        nucleo._intencion_imagenes = "wallpaper"
        instalar = Mock(return_value="Fondo de pantalla actualizado")
        ocultar = Mock()
        # Las dos hojas viven en el dueño desde el escalón 3: doblarlas sobre el
        # núcleo sería doblar un método que ya no existe. El dueño se construye
        # después de `overlay` porque ese servicio viaja como valor.
        dueño = nucleo._capacidades_herramientas()
        dueño._instalar_wallpaper_indice = instalar
        dueño._ocultar_resultados_visuales = ocultar
        nucleo.speak = Mock()
        DarkNucleo._despachar_accion_imagenes(
            nucleo, {"accion": "aplicar", "indices": [0]})
        instalar.assert_called_once_with(0)
        ocultar.assert_called_once_with(borrar_memoria=False)

    def test_resultado_sincrono_de_error_marca_fallida(self):
        gestor = self.nuevo_gestor()
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.intencion = gestor
        nucleo.esp_conversacion = SimpleNamespace(temas=None)
        nucleo._silenciar_local = SimpleNamespace(activo=False)
        nucleo.cerebro = SimpleNamespace(ctx=None)
        nucleo.entidades = None
        #: `__init__` lo deja a `None` cuando el ONNX no carga: sin filtro, el
        #: matcher manda solo. El doble construido con `__new__` lo declara igual.
        nucleo.clasificador_semantico = None
        nucleo._INTENCION_EN_BG = object()
        nucleo._armar_ventana_bg = Mock()
        ids_despachados = []
        nucleo._despachar_intencion = Mock(side_effect=lambda i, **kwargs: (
            ids_despachados.append(i.id) or "No pude hacer la acción."))
        nucleo._narrar_resultado = lambda mensaje, intencion: mensaje
        nucleo.speak = Mock()
        gestor.marcar_fallida = Mock(wraps=gestor.marcar_fallida)
        gestor.marcar_resuelta = Mock(wraps=gestor.marcar_resuelta)
        self.assertTrue(DarkNucleo._manejar_con_intencion(nucleo, "qué hora es"))
        gestor.marcar_fallida.assert_called_once()
        self.assertEqual(gestor.marcar_fallida.call_args.args[0], ids_despachados[0])
        gestor.marcar_resuelta.assert_not_called()

    @unittest.expectedFailure
    def test_abrir_nombre_de_archivo_sigue_preguntando_si_es_archivo_o_app(self):
        resultado = self.nuevo_gestor().interpretar("abre el config.py")
        self.assertEqual(resultado.tipo, AMBIGUO_PENDIENTE)


if __name__ == "__main__":
    unittest.main()
