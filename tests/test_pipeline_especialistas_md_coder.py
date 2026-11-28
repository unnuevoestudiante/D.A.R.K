"""Pruebas del pipeline entre Especialista Tareas (planificador de proyectos: la
especificación en MD) y Especialista Código (planificación y ejecución por fases)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from especialistas.especialista_tareas import EspecialistaTareas
from especialistas.especialista_codigo import EspecialistaCodigo
from contratos.especialista import SECCIONES_ESPECIFICACION
from nucleo.identidades.guardia import reparar_tuteo


SPEC_COMPLETA = """# Especificación: App de gastos

## 1. Visión
Anotar gastos del hogar y ver en qué se va el dinero.

## 2. Usuarios y escenarios
Una pareja que anota cada compra al salir de la tienda.

## 3. Pantallas y flujo
- Inicio: total del mes y últimos gastos.
- Nuevo gasto: importe, categoría y nota.
- Categorías: reparto del mes.

## 4. Datos
Gasto: importe, categoría, fecha y nota; en localStorage.

## 5. Funcionalidades
- MVP: anotar y listar gastos.
- Después: gráficas.

## 6. Dirección visual
Sobria y densa.
- Tema oscuro. [supuesto]

## 7. Stack
React con Vite: hay varias vistas.

## 8. Criterios de aceptación
- Un gasto anotado sigue ahí al recargar.

## 9. Fuera de alcance
Cuentas de usuario.
"""

SPEC_PARCIAL = """# Especificación: App de recetas

## 1. Visión
Guardar recetas familiares.
"""

ERRORES_COMPOSICION = (
    "falta «titulo»",
    "«secciones» debe ser una lista de 1 a 8 pantallas",
    "el plan pide datos persistentes o calculados: declara «modelos» y conecta los bloques",
    "el plan pide persistencia: «persistencia» debe ser true",
    "el plan pide registrar o modificar datos: declara un «formulario» conectado a un modelo",
)


class PruebaPlanificadorDeProyectos(unittest.TestCase):
    """Tareas como planificador: escribe la especificación y la pasa al coder."""

    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        parche = patch.object(EspecialistaTareas, "_carpeta_planes",
                              staticmethod(lambda: self.temporal.name))
        parche.start()
        self.addCleanup(parche.stop)

    def tareas(self, *respuestas):
        """Modelo simulado: una respuesta por llamada, y la última se repite.

        El planificador escribe por lotes (varias llamadas por turno) y solo
        acepta de cada respuesta las secciones que pidió, así que devolver la
        especificación entera en cada lote es lo mismo que escribirla por partes.
        """
        tareas = EspecialistaTareas(chat_provider=Mock(), cliente_manager=Mock(), helpers={})
        cola = list(respuestas)
        tareas._pensar = Mock(side_effect=lambda *a, **k: cola.pop(0) if len(cola) > 1 else cola[0])
        return tareas

    def especificacion_en_disco(self, texto=SPEC_COMPLETA):
        ruta = Path(self.temporal.name) / "app.md"
        ruta.write_text(texto, encoding="utf-8")
        return ruta

    def test_modo_rapido_escribe_todo_y_pide_aprobacion_con_los_supuestos(self):
        tareas = self.tareas(SPEC_COMPLETA)
        r = tareas.iniciar_planificacion("hazme una app para controlar mis gastos", "rapido")
        self.assertIn("3 pantallas: Inicio, Nuevo gasto y Categorías", r["decir"])
        self.assertIn("React", r["decir"])
        self.assertIn("Decidí sin consultarle: tema oscuro.", r["decir"])
        self.assertTrue(r["decir"].endswith("¿Lo construyo, o desea cambiar algo?"))
        self.assertIn("Le propongo esto, señor.", r["decir"])
        self.assertTrue(tareas.planificacion_activa())
        ruta = Path(tareas._plan["ruta"])
        self.assertIn("## 3. Pantallas y flujo", ruta.read_text(encoding="utf-8"))
        prompt = tareas._pensar.call_args.args[0]
        self.assertIn("[supuesto]", prompt, "el modo rápido pide marcar lo supuesto")

    def test_el_planificador_exige_datos_reales_e_identidad_propia(self):
        sistema = EspecialistaTareas._SISTEMA_PLANIFICADOR
        self.assertIn("No inventes saldos", sistema)
        self.assertIn("modelos de datos", sistema)
        self.assertIn("persistencia", sistema)
        self.assertIn("identidad visual propia", sistema)

    def test_el_resumen_entiende_el_formato_que_escribe_el_modelo(self):
        """Negritas y «[supuesto: motivo]», como salió de Groq el 25-11-2026."""
        real = SPEC_COMPLETA.replace(
            "- Inicio: total del mes y últimos gastos.",
            "- **Pantalla Inicio / Dashboard:** Muestra el resumen del mes actual.").replace(
            "Gasto: importe, categoría, fecha y nota; en localStorage.",
            "En localStorage. [supuesto: ambos usan el mismo dispositivo; así no hace "
            "falta autenticación ni servidor]")
        r = self.tareas(real).iniciar_planificacion("hazme una app de gastos", "rapido")
        self.assertIn("3 pantallas: Inicio, Nuevo gasto y Categorías.", r["decir"])
        self.assertIn("Decidí sin consultarle: ambos usan el mismo dispositivo y tema oscuro.",
                      r["decir"])
        self.assertNotIn("**", r["decir"])

    def test_el_resumen_ignora_subpuntos_parentesis_y_etiquetas(self):
        """Como salió de Groq el 25-11-2026 en el segundo recorrido real."""
        real = SPEC_COMPLETA.replace(
            "- Inicio: total del mes y últimos gastos.",
            "- **Principal (Listado)**: lo primero que se ve.\n"
            "  - *Propósito*: ver el mes.\n  - *Contenido*: totales.").replace(
            "- Tema oscuro. [supuesto]",
            "- [supuesto: supuesto de uso compartido: los dos usan el mismo móvil]")
        r = self.tareas(real).iniciar_planificacion("hazme una app de gastos", "rapido")
        self.assertIn("3 pantallas: Principal, Nuevo gasto y Categorías.", r["decir"])
        self.assertIn("Decidí sin consultarle: los dos usan el mismo móvil.", r["decir"])

    def test_una_web_inmersiva_se_resume_por_estaciones(self):
        inmersiva = SPEC_COMPLETA.replace("React con Vite: hay varias vistas.",
                                          "Inmersivo: un mundo 3D que se recorre.")
        r = self.tareas(inmersiva).iniciar_planificacion("hazme una landing de gastos", "rapido")
        self.assertIn("3 estaciones:", r["decir"])
        self.assertIn("una web en 3D que se recorre con el scroll", r["decir"])

    def test_el_nombre_de_la_estacion_sin_numero_ni_descripcion(self):
        nombre = EspecialistaTareas._nombre_pantalla
        self.assertEqual(nombre("Estación 1: Portada con el nombre"), "Portada con el nombre")
        self.assertEqual(nombre("**El Horizonte**. Pantalla de entrada"), "El Horizonte")
        self.assertEqual(nombre("Pantalla 2 - Logística y equipo"), "Logística y equipo")

    def test_en_la_primera_redaccion_vale_el_nombre_que_propone_el_modelo(self):
        con_nombre = SPEC_COMPLETA.replace("# Especificación: App de gastos",
                                           "# Especificación: Cuentas Claras")
        tareas = self.tareas(con_nombre)
        tareas.iniciar_planificacion("hazme una app para controlar los gastos de la casa", "rapido")
        self.assertEqual(tareas._plan["especificacion"].titulo, "Cuentas Claras")
        self.assertIn("nombre propio y corto", tareas._pensar.call_args_list[0].args[0])

    def test_un_si_corto_traspasa_al_coder_y_cierra_la_sesion(self):
        tareas = self.tareas(SPEC_COMPLETA)
        tareas.iniciar_planificacion("hazme una app de gastos", "rapido")
        r = tareas.atender_planificacion("sí, constrúyelo")
        traspaso = r["traspaso"]
        self.assertEqual(traspaso["stack"], "react")
        self.assertIn("Construye «App de gastos»", traspaso["tarea"])
        self.assertIn("Inicio: total del mes", traspaso["tarea"])
        self.assertNotIn("[supuesto]", traspaso["tarea"])
        self.assertTrue(Path(traspaso["especificacion"]).is_file())
        self.assertFalse(tareas.planificacion_activa())

    def test_el_coder_puede_reabrir_el_plan_y_aclarar_los_campos_faltantes(self):
        ruta = self.especificacion_en_disco()
        revisada = SPEC_COMPLETA.replace(
            "Gasto: importe, categoría, fecha y nota; en localStorage.",
            "Gasto: importe, categoría, fecha y nota. Modelo persistente en localStorage; "
            "el formulario de nuevo gasto guarda registros reales y las listas se derivan de ellos."
        ).replace(
            "- MVP: anotar y listar gastos.",
            "- MVP: registrar gastos con un formulario conectado al modelo y listarlos."
        ).replace(
            "- Inicio: total del mes y últimos gastos.",
            "- Inicio: total del mes calculado desde los gastos guardados y últimos gastos."
        )
        tareas = self.tareas(revisada)

        resultado = tareas.reabrir_por_error(
            str(ruta), ERRORES_COMPOSICION, pedido="Construye «App de gastos».")

        self.assertTrue(tareas.planificacion_activa())
        self.assertEqual(tareas._plan["estado"], "esperando_aprobacion")
        self.assertIn("El coder", resultado["decir"])
        self.assertTrue(resultado["decir"].endswith("¿Lo construyo, o desea cambiar algo?"))
        prompt = tareas._pensar.call_args.args[0]
        for error in ERRORES_COMPOSICION:
            self.assertIn(error, prompt)
        self.assertIn("Modelo persistente", tareas._plan["especificacion"].seccion("datos"))
        traspaso = tareas.atender_planificacion("sí, constrúyelo")["traspaso"]
        self.assertIn("Modelo persistente", traspaso["tarea"])

    def test_sin_modelo_tareas_pregunta_por_el_campo_que_no_pudo_aclarar(self):
        ruta = self.especificacion_en_disco()
        tareas = self.tareas("")

        resultado = tareas.reabrir_por_error(str(ruta), ERRORES_COMPOSICION)

        self.assertTrue(tareas.planificacion_activa())
        self.assertEqual(tareas._plan["estado"], "preguntando")
        self.assertEqual(tareas._plan["hueco"], "pantallas")
        self.assertIn("No pude aclararlo", resultado["decir"])
        self.assertTrue(resultado["decir"].endswith(
            "¿Qué pantallas imagina y qué se hace en cada una?"))
        self.assertEqual(tareas._plan["especificacion"].seccion("datos"),
                         "Gasto: importe, categoría, fecha y nota; en localStorage.")

    def test_varias_preguntas_de_recuperacion_terminan_en_aprobacion_y_traspaso(self):
        ruta = self.especificacion_en_disco()
        tareas = self.tareas("")
        tareas._texto_online = Mock(return_value="")
        tareas.reabrir_por_error(str(ruta), ERRORES_COMPOSICION)

        respuestas = (
            "inicio, catálogo y carrito",
            "productos, carrito y compras, guardados en localStorage",
            "añadir al carrito y confirmar la compra con un formulario conectado al modelo",
        )
        preguntas = []
        for respuesta in respuestas:
            preguntas.append(tareas._plan["hueco"])
            resultado = tareas.atender_planificacion(respuesta)
        self.assertEqual(preguntas, ["pantallas", "datos", "funcionalidades"])
        self.assertEqual(tareas._plan["recuperacion_pendientes"], [])
        self.assertEqual(tareas._plan["estado"], "esperando_aprobacion")
        self.assertTrue(resultado["decir"].endswith("¿Lo construyo, o desea cambiar algo?"))

        traspaso = tareas.atender_planificacion("sí, constrúyelo")["traspaso"]
        self.assertEqual(traspaso["especificacion"], str(ruta))
        for respuesta in respuestas:
            self.assertIn(respuesta, traspaso["tarea"])
        self.assertFalse(tareas.planificacion_activa())

    def test_tareas_completa_un_titulo_ausente_sin_necesitar_al_modelo(self):
        ruta = self.especificacion_en_disco(SPEC_COMPLETA.replace(
            "# Especificación: App de gastos", "# Especificación: "))
        tareas = self.tareas("")

        resultado = tareas.reabrir_por_error(
            str(ruta), ["falta «titulo»"], pedido="Construye «App de gastos».")

        self.assertEqual(tareas._plan["especificacion"].titulo, "App de gastos")
        self.assertEqual(tareas._plan["estado"], "esperando_aprobacion")
        self.assertIn("título", resultado["decir"])
        tareas._pensar.assert_not_called()

    def test_tareas_no_reabre_por_json_cortado_red_ni_build(self):
        ruta = self.especificacion_en_disco()
        for errores in (
            ("la respuesta no contiene un objeto JSON completo",),
            ("Read timed out",),
            ("falló npm run build: error de compilación",),
        ):
            with self.subTest(errores=errores):
                tareas = self.tareas("")
                self.assertIsNone(tareas.reabrir_por_error(str(ruta), errores))
                self.assertFalse(tareas.planificacion_activa())

    def test_un_segundo_fallo_de_composicion_no_abre_otro_plan(self):
        ruta = self.especificacion_en_disco()
        revisada = SPEC_COMPLETA.replace(
            "- Inicio: total del mes y últimos gastos.",
            "- Inicio: panel principal con el total calculado y últimos gastos.")
        tareas = self.tareas(revisada)
        errores = ["«secciones» debe ser una lista de 1 a 8 pantallas"]
        tareas.reabrir_por_error(str(ruta), errores)
        tareas.atender_planificacion("sí, constrúyelo")

        self.assertIsNone(tareas.reabrir_por_error(str(ruta), errores))
        self.assertFalse(tareas.planificacion_activa())

    def test_las_ordenes_de_voz_pasan_al_coder_sin_repetir_el_resumen(self):
        for frase in ("pasaselo a coder", "pasalo a coder", "construye"):
            with self.subTest(frase=frase):
                tareas = self.tareas(SPEC_COMPLETA)
                tareas.iniciar_planificacion("hazme una app de gastos", "rapido")
                r = tareas.atender_planificacion(frase)
                self.assertIn("traspaso", r)
                self.assertEqual(r["decir"], "")
                self.assertFalse(tareas.planificacion_activa())

    def test_si_con_cambio_no_es_aprobacion_sino_un_cambio(self):
        tareas = self.tareas(SPEC_COMPLETA, SPEC_COMPLETA, SPEC_COMPLETA,
                             SPEC_COMPLETA.replace("React con Vite", "Vanilla"))
        tareas.iniciar_planificacion("hazme una app de gastos", "rapido")
        r = tareas.atender_planificacion("sí, pero que se abra con doble clic")
        self.assertNotIn("traspaso", r)
        self.assertTrue(r["decir"].startswith("Así queda."))
        self.assertIn("doble clic", r["decir"])
        self.assertIn("que se abra con doble clic", tareas._pensar.call_args.args[0])

    def test_modo_guiado_pregunta_solo_por_lo_que_falta(self):
        tareas = self.tareas(SPEC_PARCIAL)
        r = tareas.iniciar_planificacion("planifiquemos una app de recetas", "guiado")
        self.assertEqual(r["decir"], "¿Quién la va a usar y en qué momento del día o situación la abriría?")
        self.assertEqual(tareas._plan["hueco"], "usuarios")
        self.assertIn("No inventes", tareas._pensar.call_args.args[0])

    def test_la_respuesta_se_integra_con_su_pregunta_y_se_sigue_preguntando(self):
        con_usuarios = SPEC_PARCIAL + "\n## 2. Usuarios y escenarios\nMi familia, al cocinar.\n"
        tareas = self.tareas(SPEC_PARCIAL, con_usuarios)
        tareas.iniciar_planificacion("planifiquemos una app de recetas", "guiado")
        r = tareas.atender_planificacion("mi familia, cuando cocinamos")
        prompt = tareas._pensar.call_args.args[0]
        self.assertIn("Pregunta: ¿Quién la va a usar", prompt)
        self.assertIn("Respuesta de la persona: mi familia, cuando cocinamos", prompt)
        self.assertEqual(r["decir"], "¿Qué pantallas imagina y qué se hace en cada una?")
        self.assertEqual(tareas._plan["especificacion"].seccion("vision"), "Guardar recetas familiares.",
                         "lo ya escrito no se pierde aunque el modelo lo omita")

    def test_decide_tu_cierra_las_preguntas_y_pasa_a_aprobacion(self):
        tareas = self.tareas(SPEC_PARCIAL, SPEC_COMPLETA)
        tareas.iniciar_planificacion("planifiquemos una app", "guiado")
        r = tareas.atender_planificacion("lo demás decídelo tú")
        self.assertIn("¿Lo construyo, o desea cambiar algo?", r["decir"])
        self.assertEqual(tareas._plan["estado"], "esperando_aprobacion")
        self.assertIn("[supuesto]", tareas._pensar.call_args.args[0])

    def test_el_rapido_escribe_por_lotes_que_caben_en_la_cuota(self):
        tareas = self.tareas(SPEC_COMPLETA)
        tareas.iniciar_planificacion("hazme una app de gastos", "rapido")
        self.assertEqual(tareas._pensar.call_count, 3, "9 secciones en lotes de 3")
        for llamada in tareas._pensar.call_args_list:
            self.assertEqual(llamada.kwargs["max_tokens"], EspecialistaTareas.MAX_TOKENS_POR_LOTE)
        self.assertIn("## 7. Stack", tareas._pensar.call_args_list[2].args[0])

    def test_en_el_guiado_el_modelo_no_puede_escribir_lo_que_no_se_pregunto(self):
        """Medido el 25-11-2026: con la especificación entera, el modelo lo inventaba todo
        y el modo guiado pasaba directo a proponer sin preguntar nada."""
        tareas = self.tareas(SPEC_COMPLETA)
        r = tareas.iniciar_planificacion("planifiquemos una app de gastos", "guiado")
        self.assertEqual(r["decir"], "¿Quién la va a usar y en qué momento del día o situación la abriría?")
        esp = tareas._plan["especificacion"]
        self.assertEqual(esp.seccion("vision"), "Anotar gastos del hogar y ver en qué se va el dinero.")
        self.assertEqual(esp.seccion("pantallas"), "", "no se preguntó: no se acepta")

    def test_el_guiado_pregunta_solo_lo_de_la_persona_y_supone_lo_tecnico(self):
        tareas = self.tareas(SPEC_COMPLETA)
        tareas.iniciar_planificacion("planifiquemos una app de gastos", "guiado")
        preguntas = []
        for respuesta in ("una pareja", "inicio y nuevo gasto", "anotar gastos", "sobria"):
            preguntas.append(tareas._plan["hueco"])
            r = tareas.atender_planificacion(respuesta)
        self.assertEqual(preguntas, ["usuarios", "pantallas", "funcionalidades", "visual"])
        self.assertTrue(r["decir"].endswith("¿Lo construyo, o desea cambiar algo?"))
        self.assertEqual(tareas._plan["especificacion"].stack(), "react",
                         "el stack no se pregunta: lo propone D.A.R.K.")

    def test_cancelar_cierra_y_deja_el_plan_guardado(self):
        tareas = self.tareas(SPEC_PARCIAL)
        tareas.iniciar_planificacion("planifiquemos una app de recetas", "guiado")
        ruta = tareas._plan["ruta"]
        r = tareas.atender_planificacion("cancela el plan")
        self.assertIn(ruta, r["decir"])
        self.assertFalse(tareas.planificacion_activa())
        self.assertTrue(Path(ruta).is_file())

    def test_la_sesion_caduca_sola(self):
        tareas = self.tareas(SPEC_PARCIAL)
        tareas.iniciar_planificacion("planifiquemos una app", "guiado")
        tareas._plan["ts"] -= EspecialistaTareas.PLAN_TTL_SEGUNDOS + 1
        self.assertFalse(tareas.planificacion_activa())

    def test_sin_modelo_el_rapido_no_finge_un_plan_y_lo_arma_preguntando(self):
        tareas = self.tareas("", "")
        r = tareas.iniciar_planificacion("hazme una app para controlar mis gastos", "rapido")
        self.assertTrue(r["decir"].startswith("Ahora no tengo un modelo libre"))
        self.assertTrue(r["decir"].endswith(
            "¿Quién la va a usar y en qué momento del día o situación la abriría?"))
        self.assertNotIn("Te propongo", r["decir"])
        self.assertEqual(tareas._plan["especificacion"].seccion("vision"),
                         "hazme una app para controlar mis gastos")
        # La respuesta, sin modelo que la ordene, se guarda tal cual en su sección.
        r = tareas.atender_planificacion("mi pareja y yo, cada noche")
        self.assertEqual(tareas._plan["especificacion"].seccion("usuarios"),
                         "mi pareja y yo, cada noche")
        self.assertEqual(r["decir"], "¿Qué pantallas imagina y qué se hace en cada una?")

    def test_preguntas_de_tareas_salen_formales_sin_reparacion_de_guardia(self):
        frases = [s.pregunta for s in SECCIONES_ESPECIFICACION]
        frases.append(EspecialistaTareas._pregunta_de("desconocida"))
        for frase in frases:
            with self.subTest(frase=frase):
                reparada, cambio = reparar_tuteo(frase)
                self.assertEqual(reparada, frase)
                self.assertFalse(cambio)

    def test_rechazo_de_documento_con_tema_largo_habla_de_forma_formal(self):
        tareas = self.tareas()
        tareas._soltar_trabajo = Mock()

        respuesta = tareas.escribir_documento("Un tema demasiado largo para esta prueba. " * 8)

        reparada, cambio = reparar_tuteo(respuesta)
        self.assertFalse(cambio, reparada)
        self.assertIn("Dígame un tema concreto", respuesta)

    def test_sin_modelo_las_pantallas_quedan_como_lista(self):
        tareas = self.tareas("", "", "")
        tareas.iniciar_planificacion("planifiquemos una app", "guiado")
        tareas._plan["hueco"] = "pantallas"
        tareas.atender_planificacion("inicio y ajustes")
        self.assertEqual(tareas._plan["especificacion"].seccion("pantallas"), "- inicio y ajustes")

    def test_el_titulo_se_corta_por_palabra_y_sin_conectores_colgando(self):
        titulo = EspecialistaTareas._titulo_de(
            "hazme una app para controlar los gastos de la casa entre mi pareja y yo")
        self.assertEqual(titulo, "App para controlar los gastos de la casa")
        self.assertEqual(EspecialistaTareas._titulo_de("planifiquemos una app de recetas"),
                         "App de recetas")

    def test_deteccion_de_pedidos(self):
        for frase in ("planifiquemos una app de recetas", "vamos a planear un proyecto web",
                      "diseñemos una aplicación para el gimnasio"):
            self.assertTrue(EspecialistaTareas.pide_planificar(frase), frase)
        for frase in ("planifica mi día", "qué hora es", "hazme una app de gastos"):
            self.assertFalse(EspecialistaTareas.pide_planificar(frase), frase)
        self.assertTrue(EspecialistaTareas.pide_app("hazme una app para controlar mis gastos"))
        self.assertFalse(EspecialistaTareas.pide_app("hazme un script en python que renombre fotos"))
        self.assertFalse(EspecialistaTareas.pide_app("crea una página web sobre gatos"))

    def test_que_cuenta_como_aprobacion(self):
        for frase in ("sí", "dale", "Perfecto, constrúyelo", "pásaselo al coder",
                      "pasaselo a coder", "pasalo a coder", "construye", "ok"):
            self.assertTrue(EspecialistaTareas._es_aprobacion(frase), frase)
        for frase in ("sí, pero cambia el color", "no", "quiero que tenga modo oscuro y gráficas"):
            self.assertFalse(EspecialistaTareas._es_aprobacion(frase), frase)


class PruebaEspecialistaCodigoPlan(unittest.TestCase):
    def test_sanear_plan_admite_hasta_4_archivos_sin_fases(self):
        """El plan genérico conserva cuatro rutas válidas y no arrastra fases."""
        plan_bruto = {
            "nombre_proyecto": "Tienda Completa",
            "archivos": [
                {"path": "index.html", "lenguaje": "html", "fase": 1,
                 "secciones": [{"id": "Inicio"}]},
                {"path": "tienda.html", "lenguaje": "html", "fase": 1,
                 "secciones": [{"id": "Catálogo"}]},
                {"path": "js/app.js", "lenguaje": "js", "fase": 2,
                 "secciones": [{"id": "Carrito"}]},
                {"path": "css/styles.css", "lenguaje": "css", "fase": 3,
                 "secciones": [{"id": "Estilos"}]},
                {"path": "carrito.html", "lenguaje": "html", "fase": 3,
                 "secciones": [{"id": "Compra"}]},
            ],
        }

        saneado = EspecialistaCodigo._sanear_plan(plan_bruto)

        self.assertEqual(saneado["nombre_proyecto"], "tienda_completa")
        self.assertEqual(len(saneado["archivos"]), 4)
        self.assertEqual(
            [archivo["path"] for archivo in saneado["archivos"]],
            ["index.html", "tienda.html", "js/app.js", "css/styles.css"],
        )
        self.assertEqual(saneado["archivos"][0]["secciones"],
                         [{"id": "inicio", "descripcion": "inicio", "md_heading": ""}])
        self.assertTrue(all("fase" not in archivo for archivo in saneado["archivos"]))

    def test_sanear_plan_descarta_rutas_que_escapan_del_proyecto(self):
        plan_bruto = {
            "archivos": [
                {"path": "../fuera.html"},
                {"path": "/absoluto.html"},
                {"path": "C:/fuera.html"},
                {"path": "seguro/index.html"},
            ],
        }

        saneado = EspecialistaCodigo._sanear_plan(plan_bruto)

        self.assertEqual([archivo["path"] for archivo in saneado["archivos"]],
                         ["seguro/index.html"])


if __name__ == "__main__":
    unittest.main()
