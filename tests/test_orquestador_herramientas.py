"""Integración del orquestador: las seis rutas del despacho, sin motores.

El smoke manual del 25-oct se corrió contra especialistas reales y destapó el
defecto 6 (la terminal de desarrollo se podía pedir por su nombre real y saltarse
el gate). Este archivo lo fija dentro de la suite: el mismo núcleo partido por
`object.__new__` y el banco perezoso de la Fase C, pero con dueños de juguete
escritos a mano, para que no dependa de VLC, de la red ni del Task Manager.

Lo que se prueba aquí es el **camino**, no los handlers: qué nombre cae en qué
dueño, qué permiso se aplica, y con qué forma sale el paso.
"""
import pathlib
import sys
import threading
import unittest
from collections import defaultdict
from types import SimpleNamespace
from unittest.mock import Mock, patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo, NullTracer  # noqa: E402


class DobleConRegistro:
    """Dueño falso que recuerda lo que le llegó, con firma abierta.

    `**kwargs` a propósito: la política de argumentos es del banco y ya la vigilan
    `test_banco_herramientas.py`; aquí importa quién recibe la llamada, no cómo se
    desarma.
    """

    capacidad = ""

    def __init__(self):
        self.llamadas = []

    def _marca(self, nombre, kwargs):
        self.llamadas.append((nombre, dict(kwargs)))
        return f"{self.capacidad}:{nombre}:" + ",".join(sorted(kwargs))


class DobleCodigo(DobleConRegistro):
    capacidad = "codigo"

    def tool_buscar_archivo(self, **kwargs):
        return self._marca("buscar_archivo", kwargs)


class DobleComunicacion(DobleConRegistro):
    capacidad = "comunicacion"

    def tool_investigar(self, **kwargs):
        return self._marca("investigar", kwargs)

    def tool_abrir_aplicacion(self, **kwargs):
        return self._marca("abrir_aplicacion", kwargs)


class DobleTareas(DobleConRegistro):
    capacidad = "tareas"

    def tool_listar_tareas(self, **kwargs):
        return self._marca("listar_tareas", kwargs)


class DobleTerminal(DobleConRegistro):
    capacidad = "terminal"

    def tool_terminal_coder(self, **kwargs):
        return self._marca("terminal_coder", kwargs)

    def tool_terminal_diagnostico(self, **kwargs):
        return self._marca("terminal_diagnostico", kwargs)


class NucleoDeDespacho(DarkNucleo):
    """El núcleo real de orquestación, con los cuatro dueños de juguete.

    Se hereda en vez de montar un `object.__new__` pelado porque el banco pide el
    núcleo como dueño: le interesa la puerta, no los cuerpos. Desde el corte de
    conmutación este doble no define ninguna herramienta: el núcleo ya no ejecuta,
    solo orquesta.
    """


class PruebaOrquestador(unittest.TestCase):
    def setUp(self):
        self.nucleo = NucleoDeDespacho.__new__(NucleoDeDespacho)
        self.nucleo._banco = None
        self.nucleo._tracer = NullTracer()
        self.nucleo._llm_lock = threading.Lock()
        self.nucleo._pasos_originales = {"T-code": [{"tool": "escribir_codigo"}]}
        self.nucleo.codigo = DobleCodigo()
        self.nucleo.comunicacion = DobleComunicacion()
        self.nucleo.tareas = DobleTareas()
        self.nucleo.terminal = DobleTerminal()
        self.nucleo.esp_codigo = self.nucleo.codigo
        self.nucleo.esp_comunicacion = self.nucleo.comunicacion
        self.nucleo.esp_tareas = self.nucleo.tareas
        self.nucleo.esp_terminal = self.nucleo.terminal
        self.nucleo.cerebro = SimpleNamespace(ctx=SimpleNamespace(
            pedidos_herramienta=defaultdict(int),
            memoria=SimpleNamespace(sumar=Mock()),
        ))

    def banco(self):
        return self.nucleo._banco_herramientas()

    # -- las cuatro rutas de resolución ------------------------------------------

    def test_ninguna_herramienta_se_monta_contra_el_nucleo(self):
        """El corte de conmutación cierra la última ruta propia del núcleo.

        No es una afirmación sobre el banco —la ruta sin prefijo sigue existiendo
        y la cubre la prueba de `descargar_archivo`—: es una afirmación sobre la
        política. Si alguien devuelve un nombre a `HERRAMIENTAS_DEL_NUCLEO`, aquí
        aparece un dueño `nucleo`.
        """
        banco = self.banco()
        propias = [d.nombre for d in banco.descriptores()
                   if (montada := banco.montada(d.nombre)) is not None
                   and montada.dueño == "nucleo"]

        self.assertEqual([], propias)

    def test_la_ruta_sin_prefijo_tambien_es_del_dueo_de_capacidades(self):
        """Corte 1: `descargar_archivo` se monta contra el módulo de capacidades.

        Misma ruta de resolución (nombre pelado, sin `tool_`), otro dueño. Si
        alguien le devuelve el método al núcleo, el banco seguiría ejecutando y
        esta prueba no se entera: por eso se mira el dueño de la montada.
        """
        banco = self.banco()
        montada = banco.montada("descargar_archivo")
        self.assertIsNotNone(montada)
        self.assertEqual(montada.dueño, "capacidades")
        self.assertEqual(banco.descriptor("descargar_archivo").resolucion,
                         "nucleo")

    def test_abrir_en_navegador_ejecuta_el_dueo_real_y_abre_la_pagina(self):
        """El camino entero con el dueño de verdad, no con un doble.

        El banco recorta los argumentos por la firma del ejecutable: si el
        método del dueño no aceptara `consulta`, el paso saldría en verde sin
        haber abierto nada. Lo que se mide es la página que llega al navegador.
        El almacén se anula en la fábrica —los dos dueños posibles la llaman—
        para que lo escrito en el `config/` de esta máquina no decida el destino.
        """
        with patch("webbrowser.open", return_value=True) as abrir, \
                patch("nucleo.sitios_web.crear_almacen_sitios_web",
                      return_value=None):
            paso = self.nucleo._ejecutar_herramienta(
                "abrir_en_navegador", {"consulta": "YouTube"}, {})

        self.assertTrue(paso.ok, paso.mensaje)
        abrir.assert_called_once_with("https://www.youtube.com")
        self.assertEqual(self.banco().montada("abrir_en_navegador").dueño,
                         "capacidades")

    def test_ruta_del_contrato_ejecuta_en_el_dueño_que_declaran_las_tuplas(self):
        paso = self.nucleo._ejecutar_herramienta(
            "buscar_archivo", {"nombre": "manifest_tools"}, {})

        self.assertTrue(paso.ok, paso.mensaje)
        self.assertEqual(self.nucleo.codigo.llamadas[0][0], "buscar_archivo")
        descriptor = self.banco().descriptor("buscar_archivo")
        self.assertEqual((descriptor.resolucion, descriptor.especialista),
                         ("contrato", "codigo"))

    def test_ruta_de_alias_ejecuta_el_objetivo_pero_con_el_nombre_pedido(self):
        """`terminal_desarrollo` no existe como `tool_*`: el alias lo atiende.

        El contador del cerebro registra el nombre que pidió el modelo, no el
        ejecutable: es lo que hace legible el historial de usos.
        """
        contexto = {"tarea_id": "T-code", "paso_id": "p3"}
        paso = self.nucleo._ejecutar_herramienta(
            "terminal_desarrollo", {"operacion": "estado_git"}, contexto)

        self.assertTrue(paso.ok, paso.mensaje)
        self.assertEqual(self.nucleo.terminal.llamadas[0][0], "terminal_coder")
        self.assertEqual(
            self.nucleo.cerebro.ctx.pedidos_herramienta["terminal_desarrollo"], 1)
        descriptor = self.banco().descriptor("terminal_desarrollo")
        self.assertEqual(descriptor.resolucion, "alias")
        self.assertEqual(descriptor.ejecutor, "tool_terminal_coder")

    def test_una_invisible_ejecuta_aunque_el_modelo_no_la_ve(self):
        """Defecto 1, parte ejecutable: `listar_tareas` no está en el MANIFEST."""
        self.assertFalse(self.banco().descriptor("listar_tareas").visible_al_modelo)
        paso = self.nucleo._ejecutar_herramienta("listar_tareas", {}, {})

        self.assertTrue(paso.ok, paso.mensaje)
        self.assertEqual(self.nucleo.tareas.llamadas[0][0], "listar_tareas")

    # -- el gate y la puerta de nombres ------------------------------------------

    def test_el_gate_de_la_terminal_pide_tarea_de_codigo(self):
        """Con una tarea de código en el plan, la terminal de desarrollo pasa."""
        paso = self.nucleo._ejecutar_herramienta(
            "terminal_desarrollo", {"operacion": "estado_git"},
            {"tarea_id": "T-code", "paso_id": "p3"})

        self.assertTrue(paso.ok, paso.mensaje)

    def test_el_gate_niega_fuera_de_tarea_de_codigo(self):
        paso = self.nucleo._ejecutar_herramienta(
            "terminal_desarrollo", {"operacion": "estado_git"}, {})

        self.assertFalse(paso.ok)
        self.assertIn("tarea de código", paso.mensaje)
        self.assertFalse(paso.reintentable,
                         "un permiso negado no se reintenta: reintentarlo es insistir")
        self.assertEqual(self.nucleo.terminal.llamadas, [],
                         "el gate negó pero el especialista se ejecutó igual")

    def test_el_gate_niega_tambien_por_el_nombre_real_del_ejecutable(self):
        """Defecto 6, el hueco que abrió la Fase C y que este test cierra.

        `terminal_coder` es invisible para el modelo pero ejecutable desde la Fase C.
        Si el permiso se compara contra el nombre pedido, este nombre entra sin gate.
        """
        for nombre in ("terminal_coder", "terminal_desarrollo"):
            with self.subTest(nombre=nombre):
                paso = self.nucleo._ejecutar_herramienta(
                    nombre, {"operacion": "estado_git"}, {})
                self.assertFalse(paso.ok, f"{nombre} se saltó el gate")
                self.assertIn("tarea de código", paso.mensaje)

        self.assertEqual(self.nucleo.terminal.llamadas, [])

        # Y dentro de una tarea de código autorizada, las dos puertas abren.
        contexto = {"tarea_id": "T-code", "paso_id": "p1"}
        self.assertTrue(self.nucleo._ejecutar_herramienta(
            "terminal_coder", {"operacion": "estado_git"}, contexto).ok)
        self.assertTrue(self.nucleo._ejecutar_herramienta(
            "terminal_desarrollo", {"operacion": "estado_git"}, contexto).ok)

    def test_un_nombre_inventado_devuelve_tool_not_found_sin_ejecutar_nada(self):
        """Defecto 5: el emparejamiento difuso murió; nada de ejecutar lo que suena.

        El slug `tool_not_found:<nombre>` no viaja en el paso: `_clasificar_error`
        lo convierte en `param` no reintentable y el mensaje se queda con el nombre
        pedido. Se comprueban las dos cosas porque son lo que lee el modelo.
        """
        for inventado in ("buscar_web_larga", "abrir_aplicacion_v2",
                          "listar_tareas_pendientes"):
            with self.subTest(nombre=inventado):
                paso = self.nucleo._ejecutar_herramienta(inventado, {}, {})
                self.assertFalse(paso.ok)
                self.assertEqual(paso.tipo_error, "param")
                self.assertFalse(paso.reintentable)
                self.assertIn(f"Herramienta desconocida: {inventado}", paso.mensaje)

        self.assertIsNone(self.banco().resolver("buscar_web_larga"))
        self.assertEqual(self.nucleo.comunicacion.llamadas, [])

    # -- lo que el núcleo sigue siendo dueño de hacer ------------------------------

    def test_el_nucleo_reescribe_la_operacion_bloqueada_con_su_frase(self):
        """La traducción de `operacion_bloqueada` es política del núcleo, no del banco."""
        self.nucleo._frase_comando_bloqueado = lambda: "eso no lo hago sin confirmación"

        def bloqueado(**kwargs):
            self.nucleo.terminal.llamadas.append(("terminal_diagnostico", kwargs))
            return {"codigo": "operacion_bloqueada", "mensaje": "cruda del handler"}

        self.nucleo.terminal.tool_terminal_diagnostico = bloqueado
        paso = self.nucleo._ejecutar_herramienta(
            "terminal_diagnostico", {"operacion": "borrar_todo"}, {})

        self.assertIn("eso no lo hago sin confirmación", paso.mensaje)

    def test_el_giro_de_un_nombre_sobado_no_cambia_la_forma_del_paso(self):
        """Todo lo que sale del orquestador es `PasoResultado`, también el fallo."""
        paso = self.nucleo._ejecutar_herramienta("no_existe", {}, {})

        self.assertEqual(paso.tool, "no_existe")
        self.assertEqual(paso.paso_id, "no_existe")
        self.assertEqual(paso.estado, "fallo")
        self.assertFalse(paso.reintentable,
                         "un nombre inexistente no se puede reintentar igual")


class OverlayDeFachada:
    """Doble con el API del contrato: `estado()` y `pintar()`, sin atributos privados.

    `FachadaOverlay` no expone `_state`, así que un doble que lo simule acepta
    lecturas que la producción jamás va a responder.
    """

    def __init__(self, estado="listening"):
        self._estado = estado
        self.pintados = []

    def estado(self):
        return self._estado

    def pintar(self, state, text=None, menu_data=None, results_data=None):
        self._estado = state
        self.pintados.append((state, {"text": text, "menu_data": menu_data,
                                      "results_data": results_data}))


class PruebaCableadoDelDuenoDeCapacidades(unittest.TestCase):
    """El dueño nuevo tiene que recibir la presentación o su candado miente.

    Sin `overlay`/`overlay_obj` inyectados, `_estado_overlay()` devuelve "idle"
    siempre: el candado de las tarjetas rechaza todo y, como el rechazo es
    silencioso, cada paso del cluster se registra como éxito sin haber hecho
    nada. Nadie lo ve hoy porque ningún nombre del cluster está montado todavía.
    """

    def setUp(self):
        self.nucleo = NucleoDeDespacho.__new__(NucleoDeDespacho)
        self.nucleo._capacidades = None
        self.nucleo._http = Mock()
        self.nucleo.overlay = OverlayDeFachada()

    def capacidades(self):
        return self.nucleo._capacidades_herramientas()

    def test_el_ejecutor_ve_lo_que_el_overlay_real_muestra(self):
        c = self.capacidades()
        self.assertFalse(c._hay_imagenes_visibles())
        self.nucleo.overlay._estado = "showing_results"
        self.assertTrue(c._hay_imagenes_visibles())

    def test_pintar_le_llega_a_la_fachada_por_su_nombre_real(self):
        c = self.capacidades()
        c._set_overlay("showing_results", results_data={"items": [1]})
        self.assertEqual("showing_results", self.nucleo.overlay.pintados[-1][0])
        self.assertEqual({"items": [1]},
                         self.nucleo.overlay.pintados[-1][1]["results_data"])

    def test_el_ejecutor_ve_el_bridge_que_el_nucleo_ya_tiene(self):
        """Sin `tv_bridge`, el dueño escribe la config en disco y responde
        "el bridge no está activo" aunque la tele esté conectada aquí."""
        self.nucleo._tv_bridge = "PUENTE"
        self.assertEqual("PUENTE", self.capacidades()._tv_bridge)

    def test_el_puente_llega_tarde_y_aun_se_ve(self):
        """`tv_bridge` viaja como consulta, no como valor.

        `_iniciar_modulo_tv` puede montar el puente después de la primera
        frase del usuario, y para entonces el dueño ya está construido. Si
        el cable anclara el valor, las cuatro compuertas seguirían creyendo
        que no hay tele y «el bridge del TV no está activo» sonaría para
        siempre.
        """
        c = self.capacidades()
        self.assertIsNone(c._tv_bridge)
        self.nucleo._tv_bridge = "PUENTE-TARDIO"
        self.assertEqual("PUENTE-TARDIO", c._tv_bridge)

    def test_el_arranque_del_puente_lo_pone_el_nucleo(self):
        c = self.capacidades()
        self.assertIsNotNone(
            c._s.arrancar_tv,
            "sin el hook, «tele en 192.168.x.x» guarda la IP y el bridge "
            "nunca arranca")
        self.nucleo._iniciar_modulo_tv = Mock()
        c._s.arrancar_tv()
        self.nucleo._iniciar_modulo_tv.assert_called_once_with()

    def test_el_dueo_recibe_la_inferencia_del_nucleo(self):
        """El ciclo de vida del modelo sigue siendo del núcleo; la consulta, no.

        Sin `llm`/`lock_llm` el ejecutor se queda con `None` y un cerrojo vacío:
        `_sugerir_dominio` devuelve None sin llamar a nadie. Sin los otros dos
        hooks, `_preparar_modelo_de_trabajo` contesta True sin cargar nada y
        `_filtrar_respuesta_llm` devuelve el texto crudo.
        """
        proveedor = Mock()
        cerrojo = threading.Lock()
        self.nucleo._llm_provider = proveedor
        self.nucleo._llm_lock = cerrojo
        self.nucleo._preparar_modelo_de_trabajo = Mock(return_value=True)
        self.nucleo._filtrar_respuesta_llm = Mock(return_value="filtrado")

        c = self.capacidades()

        self.assertIs(c._llm_provider, proveedor)
        self.assertIs(c._llm_lock, cerrojo)
        self.assertTrue(c._preparar_modelo_de_trabajo("modelo-de-trabajo"))
        self.nucleo._preparar_modelo_de_trabajo.assert_called_once_with(
            "modelo-de-trabajo")
        self.assertEqual(
            "filtrado", c._filtrar_respuesta_llm("crudo", alternativa="otro"))
        self.nucleo._filtrar_respuesta_llm.assert_called_once_with(
            "crudo", alternativa="otro")

    def test_la_capa_2_del_navegador_llega_al_modelo_por_el_cableado(self):
        """La secuencia que se pierde si el cable falta: «abre Pajarito de mi
        barrio» no está en la tabla ni en la lista del usuario, así que el dueño
        pregunta al modelo, comprueba que el dominio resuelve y abre esa página.
        Medido con `llm=None`: se abre la búsqueda de Google, el usuario oye
        «Abriendo Pajarito de mi barrio en el navegador.» y el único aviso de que
        la capa 2 no contestó queda en el log."""
        proveedor = Mock()
        proveedor.complete.return_value = SimpleNamespace(
            status_code=200, content="pajarito.com")
        self.nucleo._llm_provider = proveedor
        self.nucleo._llm_lock = threading.Lock()
        self.nucleo._preparar_modelo_de_trabajo = Mock(return_value=True)
        c = self.capacidades()

        with patch.object(c, "_almacen_sitios_web", return_value=None), \
                patch("nucleo.sitios_web.dominio_resuelve",
                      lambda dominio, **k: True), \
                patch("herramientas.internas.ejecutor.webbrowser.open",
                      return_value=True) as abrir:
            c.abrir_en_navegador("Pajarito de mi barrio")

        proveedor.complete.assert_called_once()
        self.assertEqual(abrir.call_args[0][0], "https://pajarito.com")


class PruebaLasDosRutasDeVozConmutadas(unittest.TestCase):
    """`abrir_en_navegador` y `guardar_sitio_web` ya no tienen return propio.

    Las dos frases caían en un método del núcleo antes de llegar al banco, así
    que la política de confirmación de `guardar_sitio_web` solo la sostenía la
    bandera `peligrosa` de la capacidad. Al quitar los returns, la voz pasa por
    `ejecutar_comando` con `desde_modulo`/`ya_confirmado`: quien ya preguntó no
    vuelve a preguntar, y lo que viene de la tele o del móvil se rechaza plano.
    """

    def _nucleo(self, respuesta="Abriendo YouTube en el navegador."):
        nucleo = Mock()
        nucleo.intencion = SimpleNamespace(_intenciones={}, _recientes=[])
        nucleo.ejecutar_comando = Mock(return_value=respuesta)
        return nucleo

    def _intencion(self, action, params):
        return SimpleNamespace(action=action, params_planos=lambda: dict(params),
                               relaciones=[])

    def test_abrir_pasa_por_el_banco_con_sus_parametros(self):
        nucleo = self._nucleo()

        mensaje = DarkNucleo._despachar_intencion(
            nucleo, self._intencion("abrir_en_navegador",
                                    {"consulta": "YouTube"}))

        self.assertEqual(mensaje, "Abriendo YouTube en el navegador.")
        nucleo.ejecutar_comando.assert_called_once_with(
            "abrir_en_navegador", {"consulta": "YouTube"},
            desde_modulo=False, ya_confirmado=False)
        nucleo.abrir_en_navegador.assert_not_called()

    def test_guardar_lleva_la_confirmacion_ya_dada(self):
        """La voz pregunta antes por `peligrosa`; el banco no puede repetirlo."""
        nucleo = self._nucleo("Guardado mi banco en https://mi-banco.com.")

        DarkNucleo._despachar_intencion(
            nucleo,
            self._intencion("guardar_sitio_web",
                            {"nombre": "mi banco", "url": "https://mi-banco.com"}),
            ya_confirmado=True)

        nucleo.ejecutar_comando.assert_called_once_with(
            "guardar_sitio_web",
            {"nombre": "mi banco", "url": "https://mi-banco.com"},
            desde_modulo=False, ya_confirmado=True)
        nucleo.guardar_sitio_web.assert_not_called()

    def test_lo_que_viene_de_un_modulo_viaja_marcado(self):
        nucleo = self._nucleo()

        DarkNucleo._despachar_intencion(
            nucleo, self._intencion("guardar_sitio_web",
                                    {"nombre": "x", "url": "https://x.com"}),
            desde_modulo=True, ya_confirmado=True)

        self.assertTrue(
            nucleo.ejecutar_comando.call_args.kwargs["desde_modulo"],
            "sin la marca, el texto encolado sin origen escribiría en disco")


class PruebaDosClasificadores(unittest.TestCase):
    """Un prefijo nuevo tiene que enseñarse a los DOS clasificadores.

    El del ejecutor solo sirve a su dispatcher propio; el que da forma a
    `tipo_error`/`reintentable` de un paso despachado por el banco es el del
    núcleo (`dark_nucleo.py:6810`, llamado en :6887 y :6914). Lo que se fija
    aquí es la etiqueta: `precondition:` sin rama caía al default y el paso se
    registraba como "interno" en vez de "tool". El reintento no cambiaba —los
    dos dan `reintentable=False`— y `tipo_error` solo se consulta para el
    backoff de "ram" (dark_nucleo.py:6763), así que el daño es de diagnóstico,
    no de bucle.
    """

    PRECONDICION = "precondition:accion_imagenes sin tarjetas visibles"

    def _del_ejecutor(self, detalle):
        from herramientas.internas import ejecutor as capacidades_ej
        return capacidades_ej.EjecutorHerramientas._clasificar_error(detalle)

    def test_el_nucleo_la_clasifica_como_herramienta_no_reintentable(self):
        self.assertEqual(
            ("tool", False), DarkNucleo._clasificar_error(self.PRECONDICION))

    def test_el_ejecutor_coincide_con_el_nucleo(self):
        self.assertEqual(
            DarkNucleo._clasificar_error(self.PRECONDICION),
            self._del_ejecutor(self.PRECONDICION))

    def test_sin_detalle_no_es_precondicion(self):
        self.assertEqual(("interno", False), DarkNucleo._clasificar_error(""))

    MUESTRAS = [
        "",
        "missing_param: query",
        "handler_not_found: no_existe",
        "tool_not_found: no_existe",
        PRECONDICION,
        "Ruta bloqueada por seguridad",
        "No encontré el archivo informe.txt",
        "El formato de la ruta es inválido",
        "This video is not available",
        "No encontré resultados para gatitos",
        "El archivo superó los 500 MB permitidos",
        "No tengo suficiente memoria",
        "Read timed out",
        "No pude conectarme con el sitio",
        "El modelo tardó demasiado",
        "Un detalle que nadie clasifica",
    ]

    def test_ambos_clasificadores_dan_lo_mismo_en_el_muestreo(self):
        """La valla que faltaba: `PruebasPrefijosNoDiverjan` solo compara las
        listas, y las ramas `startswith` sueltas se separaban en silencio."""
        for detalle in self.MUESTRAS:
            with self.subTest(detalle=detalle or "(vacío)"):
                self.assertEqual(
                    DarkNucleo._clasificar_error(detalle),
                    self._del_ejecutor(detalle))

    SOLO_EN_EL_EJECUTOR = [
        "terminal_role_denied: hace falta el rol de desarrollo",
        "mensaje_invalido: la frase no describe ninguna acción de TV",
    ]

    def test_lo_que_solo_conoce_el_ejecutor_al_menos_reintenta_igual(self):
        for detalle in self.SOLO_EN_EL_EJECUTOR:
            with self.subTest(detalle=detalle[:32]):
                self.assertEqual(
                    DarkNucleo._clasificar_error(detalle)[1],
                    self._del_ejecutor(detalle)[1],
                    "la decisión de reintentar no puede depender de qué "
                    "clasificador conteste")


if __name__ == "__main__":
    unittest.main()
