"""Pruebas del paso de contenido investigado al generador de código."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

RAIZ = Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from especialistas.especialista_codigo import EspecialistaCodigo  # noqa: E402
from proveedores.llm.contrato import ChatResult  # noqa: E402
from proveedores.llm.remoto import ErrorRemoto  # noqa: E402


class PruebasPipelineCoder(unittest.TestCase):
    def _plan(self):
        return {
            "nombre_proyecto": "biografia_web",
            "archivos": [{
                "path": "index.html",
                "lenguaje": "html",
                "descripcion": "Página biográfica",
                "secciones": [{
                    "id": "contenido",
                    "descripcion": "Contenido principal",
                    # Simula un planner que no enlazó el encabezado correcto.
                    "md_heading": "Encabezado que no existe",
                }],
            }],
        }

    def test_inyecta_markdown_aunque_el_planner_no_asigne_encabezado(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            raiz = Path(temporal)
            ruta_md = raiz / "_contenido.md"
            texto_fuente = (
                "## Vida temprana\nEinstein nació en Ulm en 1879.\n\n"
                "## Trabajo científico\nDesarrolló la relatividad especial."
            )
            ruta_md.write_text(texto_fuente, encoding="utf-8")
            coder = EspecialistaCodigo()
            coder._planificar_proyecto = Mock(return_value=self._plan())
            coder._generar_seccion = Mock(side_effect=AssertionError(
                "el proyecto genérico ya no concatena secciones"))
            prompts = []

            def generar_online(prompt, _sistema, _lenguaje, max_tokens=4000):
                prompts.append(prompt)
                self.assertEqual(max_tokens, 4000)
                return True, "<section>Contenido biográfico</section>"

            coder._llamar_online = generar_online
            coder._liberar_coder = Mock()

            with patch("builtins.print"):
                resultado = coder.tool_escribir_codigo(
                    tarea="Crea una web sobre la biografía de Einstein",
                    nombre_archivo="einstein",
                    extension="html",
                    ruta_destino=str(raiz / "salida"),
                    contenido_md=str(ruta_md),
                )

            self.assertIn("Proyecto 'biografia_web' generado", resultado)
            self.assertEqual(len(prompts), 1)
            self.assertIn("Genera el archivo COMPLETO index.html", prompts[0])
            self.assertIn("Entrega el código final ensamblado", prompts[0])
            self.assertIn("Einstein nació en Ulm en 1879", prompts[0])
            self.assertIn("Desarrolló la relatividad especial", prompts[0])
            self.assertTrue((raiz / "salida" / "biografia_web" / "index.html").is_file())

    def test_si_no_hay_markdown_genera_desde_la_peticion(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            coder = EspecialistaCodigo()
            coder._planificar_proyecto = Mock(return_value=self._plan())
            prompts = []

            def generar_online(prompt, _sistema, _lenguaje, max_tokens=4000):
                prompts.append(prompt)
                self.assertEqual(max_tokens, 4000)
                return True, "<section>Contenido generado desde la petición</section>"

            coder._llamar_online = generar_online
            coder._liberar_coder = Mock()
            with patch("builtins.print"):
                resultado = coder.tool_escribir_codigo(
                    tarea="Crea un sitio web sobre la biografía de Einstein",
                    nombre_archivo="einstein",
                    extension="html",
                    ruta_destino=temporal,
                    contenido_md=str(Path(temporal) / "no_existe.md"),
                )
            self.assertIn("Proyecto 'biografia_web' generado", resultado)
            self.assertEqual(coder._planificar_proyecto.call_args.kwargs["contenido_md"], {})
            self.assertIn("biografía de Einstein", prompts[0])



class _TrabajoFalso:
    """Motor de nube del proyecto: responde, o lanza lo que se le dé."""

    def __init__(self, resultado=None, error=None, esperas=()):
        self.resultado, self.error, self.esperas = resultado, error, esperas
        self.solicitudes, self.soltado = [], 0

    def complete_paciente(self, solicitud, timeout=None, *, al_esperar=None, cancelado=None):
        self.solicitudes.append(solicitud)
        for segundos in self.esperas:
            al_esperar(segundos, "límite por minuto", "groq")
        if self.error is not None:
            raise self.error
        return ChatResult(content=self.resultado)

    def soltar_trabajo(self):
        self.soltado += 1


class PruebasCoderPaciente(unittest.TestCase):
    """El coder usa la nube en modo paciente: la cuota espera, no rompe el proyecto."""

    def coder(self, trabajo, avisar=None):
        coder = EspecialistaCodigo(chat_provider=Mock(), avisar_espera=avisar)
        coder._trabajo = trabajo
        return coder

    def test_llama_al_motor_del_proyecto_y_limpia_el_razonamiento(self):
        trabajo = _TrabajoFalso("<think>plan</think><main>ok</main>")
        ok, texto = self.coder(trabajo)._llamar_online("haz", "sistema", "html", max_tokens=900)
        self.assertEqual((ok, texto), (True, "<main>ok</main>"))
        solicitud = trabajo.solicitudes[0]
        self.assertEqual(solicitud.messages[0], {"role": "system", "content": "sistema"})
        self.assertEqual(solicitud.options["max_output_tokens"], 900)

    def test_la_cuota_diaria_no_cae_al_local_sin_consultar(self):
        trabajo = _TrabajoFalso(error=ErrorRemoto("429 diario", diario=True))
        ok, motivo = self.coder(trabajo)._llamar_online("haz", "s", "html")
        self.assertFalse(ok)
        self.assertIn("pausado", motivo)

    def test_cuota_diaria_guarda_el_proyecto_y_espera_una_decision(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            trabajo = _TrabajoFalso(error=ErrorRemoto(
                "429 diario", proveedor="groq", diario=True, agotado=3600))
            coder = self.coder(trabajo)
            coder._estado_proyecto_activo = {"estado": "en_progreso"}
            coder._ruta_estado_proyecto_activo = str(Path(temporal) / ".dark_project.json")
            coder._fase_proyecto = "composición"
            coder._decidir_cuota_diaria = Mock(return_value=None)
            progreso = []
            coder._informar_progreso_cb = lambda *args: progreso.append(args)

            ok, motivo = coder._llamar_online("pedido", "sistema", "json")

            estado = json.loads(Path(coder._ruta_estado_proyecto_activo).read_text(encoding="utf-8"))
            self.assertFalse(ok)
            self.assertIn("pausado", motivo)
            self.assertEqual(estado["estado"], "pausado_cuota_diaria")
            self.assertEqual(estado["pausa_cuota"]["fase"], "composición")
            self.assertEqual(estado["pausa_cuota"]["proveedor"], "groq")
            self.assertEqual(estado["pausa_cuota"]["opciones"],
                             ["modelo_local", "esperar_reinicio"])
            self.assertIn("esperando su decisión", progreso[-1][2])

    def test_elegir_modelo_local_repite_la_llamada_y_guarda_la_decision(self):
        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            trabajo = _TrabajoFalso(error=ErrorRemoto(
                "429 diario", proveedor="groq", diario=True))
            coder = self.coder(trabajo)
            coder._estado_proyecto_activo = {"estado": "en_progreso"}
            coder._ruta_estado_proyecto_activo = str(Path(temporal) / ".dark_project.json")
            coder._decidir_cuota_diaria = Mock(return_value="modelo_local")
            coder._llamar_ollama = Mock(return_value=(True, "<think>oculto</think>JSON"))

            self.assertEqual(coder._llamar_online("pedido", "sistema", "json"),
                             (True, "JSON"))
            coder._llamar_ollama.assert_called_once_with(
                coder.coder_model, "sistema", "pedido", 8192,
                max_tokens=4000, timeout=600)
            estado = json.loads(Path(coder._ruta_estado_proyecto_activo).read_text(encoding="utf-8"))
            self.assertEqual(estado["decision_cuota"], "modelo_local")
            self.assertEqual(estado["estado"], "en_progreso")

    def test_esperar_reintenta_la_misma_solicitud_y_reanuda_el_proyecto(self):
        class TrabajoConReinicio:
            def __init__(self):
                self.solicitudes = []

            def complete_paciente(self, solicitud, **_opciones):
                self.solicitudes.append(solicitud)
                if len(self.solicitudes) == 1:
                    raise ErrorRemoto("429 diario", proveedor="groq", diario=True)
                return ChatResult(content="respuesta tras el reinicio")

        with tempfile.TemporaryDirectory(dir=RAIZ) as temporal:
            trabajo = TrabajoConReinicio()
            coder = self.coder(trabajo)
            coder._estado_proyecto_activo = {"estado": "en_progreso"}
            coder._ruta_estado_proyecto_activo = str(Path(temporal) / ".dark_project.json")
            coder._decidir_cuota_diaria = Mock(return_value="esperar_reinicio")

            self.assertEqual(coder._llamar_online("pedido", "sistema", "json"),
                             (True, "respuesta tras el reinicio"))
            self.assertEqual(trabajo.solicitudes[0], trabajo.solicitudes[1])
            estado = json.loads(Path(coder._ruta_estado_proyecto_activo).read_text(encoding="utf-8"))
            self.assertEqual(estado["estado"], "en_progreso")
            self.assertEqual(estado["decision_cuota"], "esperar_reinicio")

    def test_solo_local_no_sube_nada_a_la_nube(self):
        coder = EspecialistaCodigo(chat_provider=Mock(nube_de_trabajo=Mock(return_value=False)))
        ok, motivo = coder._llamar_online("haz", "s", "html")
        self.assertFalse(ok)
        self.assertIn("solo local", motivo)

    def test_una_espera_larga_se_dice_y_no_se_repite_enseguida(self):
        avisos = []
        trabajo = _TrabajoFalso("x", esperas=(30, 30, 3))
        self.coder(trabajo, avisar=avisos.append)._llamar_online("haz", "s", "html")
        self.assertEqual(len(avisos), 1, "dos esperas seguidas, un solo aviso")
        self.assertIn("30 segundos", avisos[0])

    def test_una_espera_corta_no_se_dice(self):
        avisos = []
        self.coder(_TrabajoFalso("x", esperas=(3,)), avisar=avisos.append)._llamar_online(
            "haz", "s", "html")
        self.assertEqual(avisos, [])

    def test_al_cerrar_el_proyecto_suelta_el_motor(self):
        trabajo = _TrabajoFalso("x")
        self.coder(trabajo)._liberar_coder()
        self.assertEqual(trabajo.soltado, 1)



SPEC_INMERSIVA = """# Especificación: Cumbre Andina

## 1. Visión
Fotografía de alta montaña en los Andes.

## 2. Usuarios y escenarios
Agencias y revistas de viaje.

## 3. Pantallas y flujo
- Portada
- Logística
- Contacto

## 4. Datos
Sin datos guardados.

## 5. Funcionalidades
- MVP: presentar el estudio.

## 6. Dirección visual
Azul glaciar sobre casi negro.

## 7. Stack
Inmersivo: un mundo 3D recorrido con el scroll.

## 8. Criterios de aceptación
- Se abre con doble clic.

## 9. Fuera de alcance
Tienda.
"""

MUNDO_JSON = json.dumps({
    "titulo": "Cumbre Andina", "descripcion": "Fotografía de montaña.", "tipografia": "sobria",
    "paleta": {"fondo": "#0a0a0f", "texto": "#e0e0e0", "acento": "#4ea8de",
               "colores": ["#1f3a71", "#8ab6d6", "#b0c4de"]},
    "sonido": {"caracter": "luminoso"},
    "estaciones": [
        {"indice": "01", "titulo": "Cumbre Andina", "texto": "Amanecer en la cumbre.",
         "objeto": {"tipo": "nebulosa"}},
        {"indice": "02", "titulo": "Logística", "texto": "Guía y refugio </script> incluidos.",
         "objeto": {"tipo": "cristal", "ficha": {"titulo": "Equipo", "breve": "Todo listo"}}},
        {"indice": "03", "titulo": "Reserva", "texto": "Escríbenos.", "objeto": {"tipo": "ninguno"},
         "llamada": {"texto": "Solicita información", "enlace": "mailto:hola@cumbre.test"}},
    ],
}, ensure_ascii=False)


class PruebasWebInmersiva(unittest.TestCase):
    """El coder compone el mundo (JSON) y el kit lo pone en escena."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.spec = self.raiz / "cumbre.md"
        self.spec.write_text(SPEC_INMERSIVA, encoding="utf-8")

    SIN_REVISION = {"revisado": False, "motivo_sin_revisar": "sin Electron en la prueba",
                    "aprobado": None, "hallazgos": [], "errores_consola": [], "capturas": []}

    def coder(self, *respuestas):
        coder = EspecialistaCodigo(chat_provider=Mock())
        # Aislado del historial real de variedad del usuario: cada prueba, el suyo.
        coder._ruta_variedad = str(self.raiz / "variedad.json")
        cola = list(respuestas)
        coder._llamar_online = Mock(side_effect=lambda *a, **k: (True, cola.pop(0)))
        coder._liberar_coder = Mock()
        # La Fase 4 (Electron + visión) no corre en esta suite: cada prueba la activa
        # a propósito si quiere comprobarla (ver PruebasRevisionVisual).
        coder._revisar_visualmente = Mock(return_value=dict(self.SIN_REVISION))
        return coder

    def generar(self, coder):
        return coder.tool_escribir_codigo(
            tarea="(plan)", ruta_destino=str(self.raiz), contenido_md=str(self.spec))

    def test_un_plan_inmersivo_produce_una_web_que_se_abre_sola(self):
        coder = self.coder(MUNDO_JSON)
        mensaje = self.generar(coder)
        carpeta = Path(coder.ultima_carpeta_proyecto)
        self.assertIn("3 estaciones", mensaje)
        indice = (carpeta / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="kit/inmersivo.min.js"></script>', indice)
        self.assertIn('<h1 class="marca larga" data-revuelve>Cumbre Andina</h1>', indice)
        self.assertIn('href="mailto:hola@cumbre.test"', indice)
        self.assertIn("--acento: #4ea8de;", indice)
        # «</script>» dentro del texto no puede cerrar el JSON incrustado.
        self.assertIn("<\\/script>", indice)
        self.assertEqual(indice.count("</script>"), 2)
        kit = carpeta / "kit"
        for nombre in ("inmersivo.min.js", "inmersivo.css", "fuentes.css", "LICENCIAS.txt"):
            self.assertTrue((kit / nombre).is_file(), nombre)
        fuentes = sorted(p.name for p in (kit / "fuentes").iterdir())
        self.assertTrue(fuentes and all(n.startswith("ibm-plex") for n in fuentes),
                        "solo viajan las fuentes de la tipografía elegida")
        licencias = (kit / "LICENCIAS.txt").read_text(encoding="utf-8")
        self.assertIn("MIT", licencias)
        self.assertIn("SIL Open Font License", licencias)
        estado = json.loads((carpeta / ".dark_project.json").read_text(encoding="utf-8"))
        self.assertEqual((estado["estado"], estado["tipo"]), ("completo", "inmersivo"))
        self.assertEqual(estado["objetos"], ["nebulosa", "cristal", "ninguno"])
        self.assertEqual(estado["revision_visual"], self.SIN_REVISION, "sin Electron, no se revisó")
        self.assertIn("No pude completar la revisión visual", mensaje)

    def test_los_errores_vuelven_al_modelo_y_el_segundo_intento_vale(self):
        coder = self.coder('{"titulo": "x"}', MUNDO_JSON)
        self.assertIn("3 estaciones", self.generar(coder))
        segundo = coder._llamar_online.call_args_list[1].args[0]
        self.assertIn("Tenía estos errores", segundo)
        self.assertIn("de 2 a 7 estaciones", segundo)

    def test_si_solo_quedan_errores_de_estilo_la_web_se_entrega_con_aviso(self):
        con_relleno = MUNDO_JSON.replace("Amanecer en la cumbre.", "Bienvenido a la cumbre.")
        coder = self.coder(con_relleno, con_relleno, con_relleno)
        mensaje = self.generar(coder)
        self.assertIn("Revisa el texto", mensaje)
        estado = json.loads((Path(coder.ultima_carpeta_proyecto) / ".dark_project.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(estado["estado"], "completo")
        self.assertTrue(estado["avisos_de_estilo"])

    def test_un_error_de_estructura_que_no_se_corrige_no_entrega_nada(self):
        roto = '{"titulo": "x", "estaciones": []}'
        coder = self.coder(roto, roto, roto)
        resultado = self.generar(coder)
        self.assertFalse(resultado["ok"])
        self.assertFalse((Path(coder.ultima_carpeta_proyecto) / "index.html").exists())

    def test_un_plan_vanilla_o_python_sigue_el_camino_generico_como_encargo(self):
        for stack in ("Vanilla, sin framework.", "Python, sin framework."):
            with self.subTest(stack=stack):
                self.spec.write_text(SPEC_INMERSIVA.replace(
                    "Inmersivo: un mundo 3D recorrido con el scroll.", stack),
                    encoding="utf-8")
                coder = EspecialistaCodigo(chat_provider=Mock())
                coder.generar_web_inmersiva = Mock()
                coder.generar_app_react = Mock()
                coder.generar_proyecto_completo = Mock(return_value="hecho")
                coder._es_proyecto = Mock(return_value=True)
                # El camino de siempre imprime «→», que una consola cp1252 no sabe pintar.
                with patch("builtins.print"):
                    coder.tool_escribir_codigo(
                        tarea="Construye «Cumbre»", ruta_destino=str(self.raiz),
                        contenido_md=str(self.spec))
                coder.generar_web_inmersiva.assert_not_called()
                coder.generar_app_react.assert_not_called()
                self.assertIsNone(
                    coder.generar_proyecto_completo.call_args.kwargs["contenido_md_path"],
                    "una especificación es un encargo, no un documento para volcar",
                )

    def test_un_documento_de_contenido_no_se_confunde_con_una_especificacion(self):
        contenido = self.raiz / "contenido.md"
        contenido.write_text("# Einstein\n\n## Vida temprana\nNació en Ulm.\n", encoding="utf-8")
        self.assertIsNone(EspecialistaCodigo._es_especificacion(str(contenido)))
        self.assertIsNotNone(EspecialistaCodigo._es_especificacion(str(self.spec)))

    def test_el_motor_empaquetado_corresponde_a_su_fuente(self):
        kit = DARK_PYTHON / "especialistas" / "kit" / "inmersivo"
        fuente = (kit / "motor.js").read_text(encoding="utf-8")
        paquete = (kit / "inmersivo.min.js").read_text(encoding="utf-8")
        # Cadenas que el minificador conserva: si faltan, alguien cambió motor.js
        # sin volver a empaquetar (el comando está en su cabecera).
        for marca in ("kit-sonido", "Sonido apagado", "sin-webgl"):
            self.assertIn(marca, fuente)
            self.assertIn(marca, paquete)
        self.assertIn("SPDX-License-Identifier: MIT", paquete)


class _BuscadorFalso:
    """Entrega fotos de verdad (PNG generados con Pillow) y anota su crédito."""

    def __init__(self, fallan=()):
        self.creditos, self.fallan, self.pedidas = [], set(fallan), []

    def reiniciar(self):
        self.creditos = []

    def obtener(self, consulta, destino_base, **_):
        from PIL import Image
        self.pedidas.append(consulta)
        if consulta in self.fallan:
            return None
        ruta = f"{destino_base}.png"
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (2400, 1600), (40, 90, 160)).save(ruta)
        self.creditos.append({"texto": f"Foto de Ana en Pexels ({consulta[:8]})", "url": ""})
        return ruta


MUNDO_CON_FOTOS = json.dumps({
    "titulo": "Cumbre Andina", "tipografia": "calida", "ambiente": "niebla", "recorrido": "descenso",
    "paleta": {"fondo": "#0a0a0f", "texto": "#e0e0e0", "acento": "#4ea8de",
               "colores": ["#1f3a71", "#8ab6d6", "#b0c4de"]},
    "estaciones": [
        {"titulo": "Cumbre Andina", "texto": "Amanecer en la cumbre.",
         "objeto": {"tipo": "nebulosa", "variante": "velo"}},
        {"titulo": "Las cumbres", "texto": "Seis mil metros sobre el mar.",
         "objeto": {"tipo": "fotos", "variante": "constelacion", "fotos": [
             {"consulta": "aconcagua summit sunrise", "titulo": "Aconcagua", "breve": "6.961 m"},
             {"consulta": "andes glacier blue ice", "titulo": "Glaciar", "breve": "Hielo azul"},
             {"consulta": "mountain climber ridge", "titulo": "La arista", "breve": "Último tramo"}]}},
        {"titulo": "Reserva", "texto": "Escríbenos.", "objeto": {"tipo": "terreno", "variante": "picos"},
         "llamada": {"texto": "Solicita información", "enlace": "mailto:hola@cumbre.test"}},
    ],
}, ensure_ascii=False)


class PruebasFotosYVariedad(PruebasWebInmersiva):
    """Fotos reales en el mundo, y que cada web tenga su propia forma."""

    def test_las_fotos_viajan_comprimidas_como_datos_y_como_jpg(self):
        coder = self.coder(MUNDO_CON_FOTOS)
        coder._buscador_imagenes = _BuscadorFalso()
        mensaje = self.generar(coder)
        self.assertIn("3 estaciones", mensaje)
        carpeta = Path(coder.ultima_carpeta_proyecto)
        datos = (carpeta / "kit" / "fotos.js").read_text(encoding="utf-8")
        self.assertTrue(datos.startswith("window.FOTOS_DEL_MUNDO = "))
        self.assertEqual(datos.count("data:image/jpeg;base64,"), 3)
        from PIL import Image
        with Image.open(carpeta / "fotos" / "f1.jpg") as foto:
            self.assertLessEqual(max(foto.size), 1600, "comprimida a tamaño web")
        self.assertFalse(list((carpeta / "fotos").glob("*_original*")), "la original no se queda")
        indice = (carpeta / "index.html").read_text(encoding="utf-8")
        self.assertIn('<script src="kit/fotos.js"></script>', indice)
        self.assertIn('<img src="fotos/f2.jpg" alt="Glaciar"', indice)
        self.assertIn('<p class="creditos">Fotos: Foto de Ana en Pexels', indice)
        mundo = json.loads(re.search(r'<script id="mundo" type="application/json">(.*?)</script>',
                                     indice, re.S).group(1))
        foto = mundo["estaciones"][1]["objeto"]["fotos"][0]
        self.assertEqual((foto["id"], foto["archivo"]), ("f1", "fotos/f1.jpg"))
        self.assertIn("Pexels", foto["credito"])
        self.assertEqual((mundo["ambiente"], mundo["recorrido"]), ("niebla", "descenso"))
        self.assertGreater(mundo["semilla"], 0, "cada web nace con su propia semilla")

    def test_sin_fotos_suficientes_el_objeto_se_queda_en_cielo_y_se_avisa(self):
        coder = self.coder(MUNDO_CON_FOTOS)
        coder._buscador_imagenes = _BuscadorFalso(fallan={"andes glacier blue ice", "mountain climber ridge"})
        mensaje = self.generar(coder)
        self.assertIn("no encontré fotos para «Las cumbres»", mensaje)
        carpeta = Path(coder.ultima_carpeta_proyecto)
        self.assertFalse((carpeta / "kit" / "fotos.js").exists())
        indice = (carpeta / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("kit/fotos.js", indice)

    def test_dos_webs_no_comparten_semilla(self):
        semillas = set()
        for _ in range(2):
            coder = self.coder(MUNDO_JSON)
            self.generar(coder)
            estado = json.loads((Path(coder.ultima_carpeta_proyecto) / ".dark_project.json")
                                .read_text(encoding="utf-8"))
            semillas.add(estado["semilla"])
        self.assertEqual(len(semillas), 2)

    def test_una_web_distinta_evita_los_objetos_de_la_anterior(self):
        coder = self.coder(MUNDO_JSON)
        self.generar(coder)  # web A: nebulosa:nube y cristal:racimo

        otro_spec = self.raiz / "faro.md"
        otro_spec.write_text(SPEC_INMERSIVA.replace("Cumbre Andina", "Faro del Sur"),
                             encoding="utf-8")
        coder._llamar_online = Mock(side_effect=lambda *a, **k: (
            True, MUNDO_JSON.replace("Cumbre Andina", "Faro del Sur")))
        coder.tool_escribir_codigo(tarea="(plan)", ruta_destino=str(self.raiz),
                                   contenido_md=str(otro_spec))
        pedido = coder._llamar_online.call_args_list[0].args[0]
        self.assertIn("cristal:racimo", pedido)
        self.assertIn("nebulosa:nube", pedido)

    def test_rehacer_la_misma_web_no_cuenta_como_repetirse(self):
        coder = self.coder(MUNDO_JSON, MUNDO_JSON)
        self.generar(coder)
        self.generar(coder)
        pedido = coder._llamar_online.call_args_list[1].args[0]
        self.assertNotIn("Combinaciones objeto:variante", pedido)

    def test_el_catalogo_que_ve_el_modelo_nombra_cada_variante(self):
        from contratos.especialista import VARIANTES
        from especialistas.especialista_codigo import _FORMA_MUNDO
        for tipo, variantes in VARIANTES.items():
            if tipo == "ninguno":
                continue
            self.assertIn(f"{tipo} ({' | '.join(variantes)})", _FORMA_MUNDO)

    def test_un_hallazgo_de_la_revision_visual_se_dice_en_el_mensaje(self):
        coder = self.coder(MUNDO_JSON, MUNDO_JSON, MUNDO_JSON)
        coder._revisar_visualmente = Mock(return_value={
            "revisado": True, "motivo_sin_revisar": None, "aprobado": False,
            "hallazgos": ["el título tapa la foto"], "errores_consola": [], "capturas": ["x.png"]})
        mensaje = self.generar(coder)
        self.assertIn("Quedó pendiente: el título tapa la foto", mensaje)
        self.assertEqual(coder._revisar_visualmente.call_count, 3)
        estado = json.loads((Path(coder.ultima_carpeta_proyecto) / ".dark_project.json")
                            .read_text(encoding="utf-8"))
        self.assertTrue(estado["revision_visual"]["revisado"])

    def test_un_hallazgo_de_la_revision_visual_no_tapa_el_aviso_de_estilo(self):
        con_relleno = MUNDO_JSON.replace("Amanecer en la cumbre.", "Bienvenido a la cumbre.")
        coder = self.coder(con_relleno, con_relleno, con_relleno,
                           MUNDO_JSON, MUNDO_JSON, MUNDO_JSON)
        coder._revisar_visualmente = Mock(return_value={
            "revisado": True, "motivo_sin_revisar": None, "aprobado": False,
            "hallazgos": ["el contraste es bajo"], "errores_consola": [], "capturas": []})
        mensaje = self.generar(coder)
        self.assertIn("Revisa el texto", mensaje)
        self.assertIn("Quedó pendiente: el contraste es bajo", mensaje)


SPEC_REACT = """# Especificación: Bitácora

## 1. Visión
Una app de notas personales.

## 2. Usuarios y escenarios
Alguien que anota pendientes y notas rápidas.

## 3. Pantallas y flujo
- Notas

## 4. Datos
Las notas se guardan solo en memoria.

## 5. Funcionalidades
- MVP: ver y añadir notas.

## 6. Dirección visual
Oscura y técnica.

## 7. Stack
React con Vite y TypeScript.

## 8. Criterios de aceptación
- Se puede añadir una nota y verla en la lista.

## 9. Fuera de alcance
Sincronizar en la nube.
"""

APP_JSON = json.dumps({
    "titulo": "Bitácora", "descripcion": "Notas rápidas.", "personalidad": "tecnica",
    "navegacion": "superior", "fondo3d": True,
    "secciones": [
        {"id": "notas", "titulo": "Notas", "bloques": [
            {"tipo": "estadisticas", "chips": [{"etiqueta": "Notas", "valor": "8"}]},
            {"tipo": "lista", "vacio": "Todavía no hay notas.",
             "items": [{"titulo": "Ideas para el viaje", "detalle": "Rutas por el norte", "nota": "Hoy"}]},
            {"tipo": "formulario", "boton_abrir": "Nueva nota",
             "campos": [{"etiqueta": "Título", "tipo": "texto"}, {"etiqueta": "Texto", "tipo": "area"}]},
        ]},
    ],
}, ensure_ascii=False)


class PruebasAppReact(unittest.TestCase):
    """El coder compone la app (JSON) y el kit la convierte en proyecto React."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.spec = self.raiz / "bitacora.md"
        self.spec.write_text(SPEC_REACT, encoding="utf-8")

    def coder(self, *respuestas):
        coder = EspecialistaCodigo(chat_provider=Mock())
        cola = list(respuestas)
        coder._llamar_online = Mock(side_effect=lambda *a, **k: (True, cola.pop(0)))
        coder._liberar_coder = Mock()
        coder._ruta_variedad_apps = str(self.raiz / "apps_variedad.json")
        coder._ruta_ultimo_proyecto = str(self.raiz / "coder_ultimo_proyecto.json")
        return coder

    def generar(self, coder):
        return coder.tool_escribir_codigo(
            tarea="(plan)", ruta_destino=str(self.raiz), contenido_md=str(self.spec))

    def test_un_plan_de_react_produce_un_proyecto_instalable(self):
        coder = self.coder(APP_JSON)
        mensaje = self.generar(coder)
        self.assertIn("1 pantallas", mensaje)
        self.assertIn("Necesito confirmación", mensaje)
        carpeta = Path(coder.ultima_carpeta_proyecto)
        paquete = json.loads((carpeta / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(paquete["name"], "bitacora")
        self.assertIn("react", paquete["dependencies"])
        self.assertIn("three", paquete["dependencies"])
        indice = (carpeta / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>Bitácora</title>", indice)
        src = carpeta / "src"
        for nombre in ("main.tsx", "App.tsx", "app.json"):
            self.assertTrue((src / nombre).is_file(), nombre)
        kit = src / "kit"
        for nombre in ("Fondo.tsx", "Fondo.css", "Cascaron.tsx", "Cascaron.css", "tokens.css", "fuentes.css"):
            self.assertTrue((kit / nombre).is_file(), nombre)
        tokens = (kit / "tokens.css").read_text(encoding="utf-8")
        self.assertIn('[data-p="tecnica"]', tokens)
        self.assertIn('[data-p="sobria"]', tokens)
        self.assertIn('[data-p="calida"]', tokens)
        fondo = (kit / "Fondo.tsx").read_text(encoding="utf-8")
        self.assertIn("tecnica: 0x5ee6ff, sobria: 0x2f4ad0, calida: 0xc4623a", fondo)
        cascaron = (kit / "Cascaron.tsx").read_text(encoding="utf-8")
        for tipo in ("tabla", "grafico", "progreso", "agenda", "kanban"):
            self.assertIn(f'b.tipo === "{tipo}"', cascaron)
        fuentes = sorted(p.name for p in (kit / "fuentes").iterdir())
        self.assertTrue(fuentes and all(n.startswith("space-grotesk") or n.startswith("jetbrains")
                                        for n in fuentes), "solo viajan las fuentes de la personalidad elegida")
        licencias = (carpeta / "LICENCIAS.txt").read_text(encoding="utf-8")
        self.assertIn("MIT", licencias)
        self.assertIn("SIL Open Font License", licencias)
        app = json.loads((src / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(app["navegacion"], "superior")
        self.assertEqual(len(app["secciones"][0]["bloques"]), 3)
        variedad = json.loads((self.raiz / "apps_variedad.json").read_text(encoding="utf-8"))
        self.assertEqual(variedad[0]["firma"], "tecnica:superior:con 3D")
        vite = (carpeta / "vite.config.ts").read_text(encoding="utf-8")
        self.assertIn('base: "./"', vite)
        estado = json.loads((carpeta / ".dark_project.json").read_text(encoding="utf-8"))
        self.assertEqual((estado["estado"], estado["tipo"]),
                         ("pendiente_confirmacion_instalacion", "app_react"))
        self.assertEqual(estado["mapa"]["pantallas"][0]["nombre"], "Notas")
        self.assertIn("Ideas para el viaje", estado["mapa"]["piezas"][1]["alias"])
        self.assertEqual(estado["mapa"]["piezas"][1]["selector_css"],
                         'main.contenido[data-pantalla="notas"] [data-bloque="notas-1"]')
        cascaron = (carpeta / "src" / "kit" / "Cascaron.tsx").read_text(encoding="utf-8")
        self.assertIn("data-pantalla={seccion.id}", cascaron)
        self.assertIn("data-bloque={`${seccion.id}-${i}`}", cascaron)

    def test_una_app_distinta_recibe_las_combinaciones_anteriores(self):
        from contratos.especialista import leer_especificacion
        coder = self.coder(APP_JSON)
        coder._anotar_variedad_app("huella-anterior", json.loads(APP_JSON))

        coder._componer_app(leer_especificacion(SPEC_REACT), huella="huella-nueva")

        pedido = coder._llamar_online.call_args.args[0]
        self.assertIn("Combinaciones de presentación usadas en otras apps", pedido)
        self.assertIn("tecnica:superior:con 3D", pedido)

    def test_la_misma_app_puede_repetir_su_combinacion(self):
        from contratos.especialista import leer_especificacion
        coder = self.coder(APP_JSON)
        coder._anotar_variedad_app("misma-huella", json.loads(APP_JSON))

        coder._componer_app(leer_especificacion(SPEC_REACT), huella="misma-huella")

        pedido = coder._llamar_online.call_args.args[0]
        self.assertNotIn("Combinaciones de presentación usadas en otras apps", pedido)

    def test_el_prompt_separa_el_id_tecnico_de_columna_del_id_de_dato(self):
        from contratos.especialista import leer_especificacion
        coder = self.coder(APP_JSON)

        coder._componer_app(leer_especificacion(SPEC_REACT))

        pedido = coder._llamar_online.call_args.args[0]
        self.assertIn("El «id» de cada columna es una clave técnica", pedido)
        self.assertIn("El id de un registro es un valor de celda", pedido)

    def test_instalar_y_compilar_queda_detras_de_confirmar_accion(self):
        coder = self.coder(APP_JSON)
        coder._confirmar_instalacion = Mock(return_value="¿Autoriza instalar?")
        self.assertEqual(self.generar(coder), "¿Autoriza instalar?")
        ejecutar = coder._confirmar_instalacion.call_args.args[0]
        self.assertTrue(callable(ejecutar))
        coder._comando_npm = Mock()
        coder._confirmar_instalacion.assert_called_once()
        coder._comando_npm.assert_not_called()

    def _proyecto_app_completo(self, coder):
        from contratos.especialista import validar_app
        app, errores = validar_app(json.loads(APP_JSON))
        self.assertFalse(errores)
        carpeta = self.raiz / "proyecto"
        (carpeta / "src").mkdir(parents=True)
        (carpeta / "src" / "app.json").write_text(
            json.dumps(app, ensure_ascii=False, indent=1), encoding="utf-8")
        estado = {
            "version": 1, "tipo": "app_react", "estado": "completo",
            "especificacion": str(self.spec), "archivos": ["src/app.json"],
            "mapa": coder._mapa_app(app),
        }
        (carpeta / ".dark_project.json").write_text(
            json.dumps(estado, ensure_ascii=False), encoding="utf-8")
        coder.ultima_carpeta_proyecto = str(carpeta)
        return carpeta

    def test_coder_pregunta_si_no_identifica_la_pieza_y_anota_la_busqueda(self):
        coder = self.coder('{"destino": null, "pregunta": "¿Qué bloque?"}')
        carpeta = self._proyecto_app_completo(coder)
        ruta = carpeta / "src" / "app.json"
        antes = ruta.read_text(encoding="utf-8")

        salida = coder.modificar_ultimo_proyecto("cambie el indicador no existente")

        self.assertIn("¿Cuál desea cambiar?", salida)
        self.assertEqual(ruta.read_text(encoding="utf-8"), antes)
        estado = json.loads((carpeta / ".dark_project.json").read_text(encoding="utf-8"))
        self.assertEqual(estado["busquedas_edicion"][-1]["resultado"], "pregunta")
        self.assertTrue(estado["pendiente_edicion"]["candidatos"])

    def test_mapa_inmersivo_localiza_estaciones_y_objetos_3d(self):
        mundo = {"estaciones": [{
            "indice": "01 · Inicio", "titulo": "Inicio",
            "objeto": {"tipo": "hipercubo", "variante": "teseracto",
                       "ficha": {"titulo": "La estructura", "breve": "Geometría"}},
        }]}
        mapa = EspecialistaCodigo._mapa_mundo(mundo)
        objeto = next(pieza for pieza in mapa["piezas"] if pieza["tipo"] == "objeto 3D")
        self.assertEqual(mapa["pantallas"][0]["archivo"], "index.html")
        self.assertIn("teseracto", objeto["alias"])
        self.assertEqual(objeto["ruta_json"], "/estaciones/0/objeto")
        relativo, _ = EspecialistaCodigo._archivo_edicion(
            str(self.raiz), objeto, "mueva el teseracto")
        self.assertEqual(relativo, "index.html")

    def test_mapa_inmersivo_apunta_a_ficha_satelites_y_fotos(self):
        mundo = {"estaciones": [{
            "indice": "01 · Inicio", "titulo": "Inicio",
            "objeto": {
                "tipo": "hipercubo",
                "ficha": {"titulo": "La estructura"},
                "satelites": [{"titulo": "La órbita"}],
                "fotos": [{"titulo": "El reflejo"}],
            },
        }]}

        mapa = EspecialistaCodigo._mapa_mundo(mundo)
        rutas = {pieza["tipo"]: pieza["ruta_json"] for pieza in mapa["piezas"]}

        self.assertEqual(rutas["ficha"], "/estaciones/0/objeto/ficha")
        self.assertEqual(rutas["satelite-0"], "/estaciones/0/objeto/satelites/0")
        self.assertEqual(rutas["foto-0"], "/estaciones/0/objeto/fotos/0")

    def test_cambio_puntual_unico_se_compila_y_actualiza_el_mapa(self):
        coder = self.coder(json.dumps({
            "buscar": "Ideas para el viaje", "reemplazar": "Ideas para el fin de semana",
            "pregunta": "",
        }, ensure_ascii=False))
        carpeta = self._proyecto_app_completo(coder)
        coder._presupuesto_para_build = Mock(return_value=(True, ""))
        coder._comando_npm = Mock(return_value={"ok": True, "error": ""})
        coder._revisar_app_compilada = Mock(return_value={
            "revisado": True, "aprobado": True, "hallazgos": []})

        salida = coder.modificar_ultimo_proyecto("cambie Ideas para el viaje")

        ruta = carpeta / "src" / "app.json"
        app = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(app["secciones"][0]["bloques"][1]["items"][0]["titulo"],
                         "Ideas para el fin de semana")
        coder._comando_npm.assert_called_once_with(str(carpeta), "compilar", 240)
        coder._revisar_app_compilada.assert_called_once()
        self.assertIn("React compiló correctamente", salida)
        estado = json.loads((carpeta / ".dark_project.json").read_text(encoding="utf-8"))
        self.assertIn("Ideas para el fin de semana", estado["mapa"]["piezas"][1]["alias"])
        self.assertEqual(estado["busquedas_edicion"][-1]["resultado"], "aplicado")
        self.assertFalse(Path(str(ruta) + ".dark_bak").exists())

    def test_cambio_puntual_restaura_el_archivo_si_falla_el_build(self):
        coder = self.coder(json.dumps({
            "buscar": "Ideas para el viaje", "reemplazar": "Ideas para el fin de semana",
            "pregunta": "",
        }, ensure_ascii=False))
        carpeta = self._proyecto_app_completo(coder)
        coder._presupuesto_para_build = Mock(return_value=(True, ""))
        coder._comando_npm = Mock(return_value={"ok": False, "error": "TypeScript inválido"})
        ruta = carpeta / "src" / "app.json"
        antes = ruta.read_text(encoding="utf-8")

        salida = coder.modificar_ultimo_proyecto("cambie Ideas para el viaje")

        self.assertIn("lo restauré", salida)
        self.assertEqual(ruta.read_text(encoding="utf-8"), antes)
        self.assertFalse(Path(str(ruta) + ".dark_bak").exists())

    def test_entrega_de_app_muestra_etapas_abre_y_resume_sus_supuestos(self):
        self.spec.write_text(SPEC_REACT.replace(
            "Sincronizar en la nube.",
            "Sincronizar en la nube. [supuesto: no habrá cuentas de usuario]."),
            encoding="utf-8")
        coder = self.coder(APP_JSON)
        progreso = []
        coder._informar_progreso_cb = lambda *args: progreso.append(args)
        coder._confirmar_instalacion = lambda ejecutar: ejecutar()
        coder._presupuesto_para_build = Mock(return_value=(True, ""))
        coder._comando_npm = Mock(return_value={"ok": True, "error": ""})
        coder._revisar_app_compilada = Mock(return_value={
            "revisado": True, "aprobado": True, "hallazgos": []})
        coder._abrir_app_compilada = Mock(return_value={
            "ok": True, "url": "http://127.0.0.1:4173/"})

        with patch.object(os, "startfile", create=True) as abrir:
            mensaje = self.generar(coder)

        etiquetas = [evento[2] for evento in progreso]
        self.assertTrue(any("estimación" in etiqueta for etiqueta in etiquetas))
        self.assertTrue(any("Construyendo la app · ronda 1 de 3" in etiqueta
                            for etiqueta in etiquetas))
        self.assertTrue(any("Revisando la app · ronda 1 de 3" in etiqueta
                            for etiqueta in etiquetas))
        self.assertIn("no habrá cuentas de usuario", mensaje)
        self.assertIn("No quedaron hallazgos pendientes", mensaje)
        self.assertIn("http://127.0.0.1:4173/", mensaje)
        abrir.assert_not_called()
        coder._abrir_app_compilada.assert_called_once_with(coder.ultima_carpeta_proyecto)

    def test_abrir_app_compilada_sirve_dist_y_no_cierra_el_servidor(self):
        carpeta = self.raiz / "proyecto"
        dist = carpeta / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<div id=\"root\">Arca</div>", encoding="utf-8")
        coder = self.coder()
        proceso = Mock()
        proceso.poll.return_value = None
        proceso.pid = 4321

        with patch("especialistas.especialista_codigo.subprocess.Popen",
                   return_value=proceso) as lanzar, \
                patch("especialistas.especialista_codigo.urllib.request.urlopen") as responder, \
                patch("especialistas.especialista_codigo.time.sleep"), \
                patch.object(os, "startfile", create=True) as abrir:
            resultado = coder._abrir_app_compilada(str(carpeta))

        self.assertTrue(resultado["ok"], resultado)
        self.assertTrue(resultado["url"].startswith("http://127.0.0.1:"))
        puerto = int(resultado["url"].rsplit(":", 1)[1].rstrip("/"))
        abrir.assert_called_once_with(resultado["url"])
        proceso.terminate.assert_not_called()
        self.assertEqual(lanzar.call_args.args[0][:3],
                         [sys.executable, "-m", "http.server"])
        self.assertEqual(lanzar.call_args.args[0][3], str(puerto))
        self.assertEqual(lanzar.call_args.kwargs["cwd"], str(dist))
        self.assertFalse(lanzar.call_args.kwargs["shell"])
        if os.name == "nt":
            self.assertNotEqual(lanzar.call_args.kwargs.get("creationflags", 0), 0)
        else:
            self.assertTrue(lanzar.call_args.kwargs.get("start_new_session"))
        responder.assert_called_once_with(resultado["url"], timeout=1)

    def test_si_el_navegador_no_abre_cierra_el_servidor(self):
        carpeta = self.raiz / "proyecto"
        dist = carpeta / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<div id=\"root\">Arca</div>", encoding="utf-8")
        coder = self.coder()
        proceso = Mock()
        proceso.poll.return_value = None

        with patch("especialistas.especialista_codigo.subprocess.Popen",
                   return_value=proceso), \
                patch("especialistas.especialista_codigo.urllib.request.urlopen"), \
                patch("especialistas.especialista_codigo.time.sleep"), \
                patch.object(os, "startfile", create=True,
                             side_effect=OSError("no hay navegador")):
            resultado = coder._abrir_app_compilada(str(carpeta))

        self.assertFalse(resultado["ok"])
        self.assertIn("no hay navegador", resultado["error"])
        proceso.terminate.assert_called_once()
        proceso.wait.assert_called_once_with(timeout=5)

    def test_revision_app_usa_el_servidor_local_y_lo_cierra(self):
        from contratos.especialista import leer_especificacion
        coder = self.coder()
        carpeta = self.raiz / "proyecto"
        dist = carpeta / "dist"
        dist.mkdir(parents=True)
        (dist / "index.html").write_text("<div id=\"root\">Arca</div>", encoding="utf-8")
        proceso = Mock()
        url = "http://127.0.0.1:43210/"
        coder._iniciar_servidor_app = Mock(return_value=(proceso, url, ""))

        with patch("especialistas.especialista_codigo.revisor_visual.revisar_url",
                   return_value={"revisado": True, "aprobado": True,
                                 "hallazgos": []}) as revisar:
            resultado = coder._revisar_app_compilada(
                leer_especificacion(SPEC_REACT), str(carpeta))

        coder._iniciar_servidor_app.assert_called_once_with(str(carpeta))
        self.assertEqual(revisar.call_args.args[0], url)
        self.assertTrue(resultado["revisado"])
        proceso.terminate.assert_called_once()
        proceso.wait.assert_called_once_with(timeout=5)

    def test_los_errores_vuelven_al_modelo_y_el_segundo_intento_vale(self):
        coder = self.coder('{"titulo": "x"}', APP_JSON)
        self.assertIn("Necesito confirmación", self.generar(coder))
        segundo = coder._llamar_online.call_args_list[1].args[0]
        self.assertIn("Tenía estos errores", segundo)
        self.assertIn("lista de 1 a 8 pantallas", segundo)

    def test_un_error_de_estructura_que_no_se_corrige_no_entrega_nada(self):
        roto = '{"titulo": "x", "secciones": []}'
        coder = self.coder(roto, roto, roto)
        resultado = self.generar(coder)
        self.assertFalse(resultado["ok"])
        self.assertFalse((Path(coder.ultima_carpeta_proyecto) / "package.json").exists())

    def test_un_plan_inmersivo_no_pasa_por_el_camino_de_apps(self):
        self.spec.write_text(SPEC_REACT.replace(
            "React con Vite y TypeScript.", "Inmersivo: un mundo 3D recorrido con el scroll."),
            encoding="utf-8")
        coder = EspecialistaCodigo(chat_provider=Mock())
        coder.generar_app_react = Mock()
        coder.generar_web_inmersiva = Mock(return_value="hecho")
        self.generar(coder)
        coder.generar_app_react.assert_not_called()
        coder.generar_web_inmersiva.assert_called_once()


class PruebasRevisionVisual(unittest.TestCase):
    """`_revisar_visualmente` arma la URL y nunca rompe la entrega si algo falla."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory(dir=RAIZ)
        self.addCleanup(self.temporal.cleanup)
        self.raiz = Path(self.temporal.name)
        self.spec = self.raiz / "cumbre.md"
        self.spec.write_text(SPEC_INMERSIVA, encoding="utf-8")

    def test_arma_la_url_de_archivo_y_pasa_la_direccion_visual_y_los_criterios(self):
        from contratos.especialista import leer_especificacion
        coder = EspecialistaCodigo(chat_provider=Mock())
        esp = leer_especificacion(SPEC_INMERSIVA)
        indice = str(self.raiz / "sitio" / "index.html")
        with patch("especialistas.especialista_codigo.revisor_visual.revisar_url",
                  return_value={"revisado": False}) as mock_revisar:
            coder._revisar_visualmente(esp, indice)
        args, kwargs = mock_revisar.call_args
        url, carpeta, visual, criterios = args
        self.assertTrue(url.startswith("file:///"))
        self.assertTrue(url.endswith("index.html"))
        self.assertIn("Azul glaciar", visual)
        self.assertIn("doble clic", criterios)
        self.assertEqual(carpeta, str(Path(indice).parent / ".revision"))

    def test_una_excepcion_al_revisar_no_se_propaga(self):
        from contratos.especialista import leer_especificacion
        coder = EspecialistaCodigo(chat_provider=Mock())
        esp = leer_especificacion(SPEC_INMERSIVA)
        with patch("especialistas.especialista_codigo.revisor_visual.revisar_url",
                  side_effect=RuntimeError("Electron reventó")):
            with patch("builtins.print"):
                resultado = coder._revisar_visualmente(esp, str(self.raiz / "index.html"))
        self.assertFalse(resultado["revisado"])
        self.assertIn("Electron reventó", resultado["motivo_sin_revisar"])

    def test_revision_conserva_fallos_automaticos_sin_modelo_de_vision(self):
        from especialistas import revisor_visual
        capturas = [
            revisor_visual.Captura(
                ancho=1440, ruta="escritorio.png",
                comprobaciones={"hallazgos": ["desbordamiento horizontal"]}),
            revisor_visual.Captura(ancho=390, ruta="movil.png"),
        ]
        with patch("especialistas.revisor_visual.capturar_pantallas",
                   return_value=(capturas, None)), \
                patch("especialistas.revisor_visual.criticar_captura",
                      return_value=(False, None, [])):
            resultado = revisor_visual.revisar_url(
                "http://localhost", str(self.raiz), "sobria", "sin desbordes",
                errores_build=["falló la compilación"])
        self.assertFalse(resultado["revisado"])
        self.assertIn("falló la compilación", resultado["hallazgos"])
        self.assertIn("desbordamiento horizontal", resultado["hallazgos"])
        self.assertEqual(len(resultado["capturas"]), 2)

    def test_revision_critica_escritorio_y_movil(self):
        from especialistas import revisor_visual
        capturas = [
            revisor_visual.Captura(ancho=1440, ruta="escritorio.png"),
            revisor_visual.Captura(ancho=390, ruta="movil.png"),
        ]
        with patch("especialistas.revisor_visual.capturar_pantallas",
                   return_value=(capturas, None)), \
                patch("especialistas.revisor_visual.criticar_captura",
                      side_effect=[(True, True, []), (True, False, ["texto cortado"])]) as criticar:
            resultado = revisor_visual.revisar_url(
                "http://localhost", str(self.raiz), "sobria", "se lee en móvil")
        self.assertEqual(criticar.call_count, 2)
        self.assertFalse(resultado["aprobado"])
        self.assertIn("390px: texto cortado", resultado["hallazgos"])

    def test_comando_npm_rechaza_acciones_fuera_de_la_lista(self):
        coder = EspecialistaCodigo(chat_provider=Mock())
        with self.assertRaises(ValueError):
            coder._comando_npm(str(self.raiz), "ejecutar_script_del_modelo", 1)


if __name__ == "__main__":
    unittest.main()
