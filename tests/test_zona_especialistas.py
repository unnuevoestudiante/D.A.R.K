"""Contratos de la Zona de Especialistas.

Nacieron de cinco fallos vistos en la primera versión del hub:
  1. Las dos interfaces (núcleo principal y hub) se pintaban una sobre otra.
  2. El hub era un panel con tarjetas, descripciones y fondo propio: otra app
     encima de D.A.R.K, no la identidad de D.A.R.K.
  3. Los cores del hub no eran agarrables por el sistema gestual.
  4. El hub capturaba el ratón en toda la pantalla (nada de click-through).
  5. Con el hub abierto, el teseracto principal seguía siendo agarrable por
     debajo y el zoom acumulado lo reactivaba al cerrar.

Aquí se pactan las decisiones que los cierran, leyendo la fuente como hacen
las pruebas de las variantes Nebulosa.

La tanda del 17-nov-2026 (probada con mano real) añade los contratos del
carrusel: los cores del menú no se desplazan ni encogen, el arrastre gira un
carrusel invisible, agrandar dispersa a los vecinos hasta seleccionar, y las
transiciones de entrada/salida hablan el lenguaje del bloqueo (desborde y
materialización). La matemática vive en `zona.ts` y la cubre su propio arnés
node; aquí solo se vigila que el cableado exista.
"""

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "dark_frontend" / "src"
HUB = SRC / "components" / "interfaces" / "SpecialistsHub.tsx"
OVERLAY = SRC / "components" / "DarkOverlay.tsx"
LOGICA = SRC / "lib" / "gestos" / "gestos-logica.ts"
USE_GESTOS = SRC / "lib" / "gestos" / "use-gestos.ts"
ZONA = SRC / "lib" / "gestos" / "zona.ts"
ESTILOS = SRC / "styles.css"
MOTOR = RAIZ / "dark_python" / "herramientas" / "gestos.py"


def _fuente(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8")


class PruebaSinDobleInterfaz(unittest.TestCase):
    def test_el_hub_vive_dentro_de_la_pantalla_no_encima(self):
        """El hub es una capa de `.dark-screen` (absolute), no un `fixed`
        independiente con su propio fondo: así comparte el ambiente (el campo
        de la nebulosa) y la piel `[data-interfaz]` de la interfaz activa."""
        hub = _fuente(HUB)
        self.assertNotIn("fixed inset-0", hub)
        self.assertNotIn("z-40", hub)
        estilos = _fuente(ESTILOS)
        self.assertRegex(
            estilos,
            r"\.dark-specialists-hub\s*\{[^}]*position:\s*absolute",
        )

    def test_el_nucleo_principal_no_se_pinta_con_el_hub_abierto(self):
        """La entidad principal deja de renderizarse mientras el hub está
        activo: no hay dos figuras peleando por la misma pantalla."""
        overlay = _fuente(OVERLAY)
        self.assertIn("!teleApagada && !specialistsHubActive", overlay)

    def test_la_composicion_principal_se_oculta_con_el_hub(self):
        overlay = _fuente(OVERLAY)
        self.assertIn("is-hub", overlay)
        estilos = _fuente(ESTILOS)
        self.assertRegex(
            estilos,
            r"\.dark-primary-composition\.is-hub\s*\{[^}]*visibility:\s*hidden",
        )

    def test_el_hub_mantiene_la_pantalla_levantada(self):
        """`visible` incluye el hub: con gestos apagados y estado idle la zona
        no puede desaparecer dejando su estado colgado."""
        overlay = _fuente(OVERLAY)
        visible = overlay.split("const visible =", 1)[1].split(";", 1)[0]
        self.assertIn("specialistsHubActive", visible)


class PruebaIdentidad(unittest.TestCase):
    def test_sin_tarjetas_ni_fondo_ni_explicaciones(self):
        hub = _fuente(HUB)
        for prohibido in (
            "backdrop-blur",
            "bg-black/",
            "rounded-2xl",
            "Conectar Especialista",
            "description",
            "border-cyan",
        ):
            self.assertNotIn(prohibido, hub, f"el hub sigue trayendo {prohibido!r}")

    def test_solo_los_tres_cores_con_su_nombre_encima(self):
        hub = _fuente(HUB)
        self.assertIn("data-obstaculo", hub)
        self.assertIn("{spec.name}", hub)
        for nombre in ("Coder", "Tareas", "Conversacional"):
            self.assertIn(nombre, hub)

    def test_el_core_v2_no_pinta_hud_explicativo_en_el_hub(self):
        tipos = _fuente(SRC / "types" / "interfaces.ts")
        self.assertIn("sinHud", tipos)
        v2 = _fuente(SRC / "components" / "interfaces" / "NebulaV2Core.tsx")
        self.assertIn("sinHud", v2)
        self.assertIn("sinHud", _fuente(HUB))


class PruebaCoresAgarrables(unittest.TestCase):
    def test_cada_core_tiene_su_id_agarrable_propio(self):
        """Tres ids distintos entre sí y distintos del entityId principal:
        si compartieran id, el agarre de un core transformaría el teseracto."""
        hub = _fuente(HUB)
        self.assertIn("data-agarrable", hub)
        self.assertRegex(hub, r"especialista-")
        overlay = _fuente(OVERLAY)
        self.assertNotIn("gestoHub", overlay)

    def test_solo_el_core_central_es_manipulable(self):
        """Solo el core de la ranura central se agarra y se selecciona por gestos:
        su arrastre rota el carrusel. Los laterales son vecinos visibles del
        carrusel (click-through), no agarrables — así no hay ambigüedad de qué
        core se mueve ni falta el agarre de par para elegir el exterior."""
        hub = _fuente(HUB)
        self.assertIn("v.slot === 1", hub)
        self.assertIn("manipulable", hub)
        self.assertIn("armado && !saliendo && manipulable", hub)
        self.assertIn("pointer-events-none", hub)

    def test_los_cores_se_deforman_en_su_sitio_no_se_trasladan(self):
        """`data-agarrable-fijo`: el reducer fuerza dx/dy a cero y deja solo la
        escala. El desplazamiento del menú lo decide el carrusel (vistaZona),
        no el estilo de agarre libre — con estiloAgarrable el core se iba de
        su ranura y el nombre dejaba de leerse."""
        hub = _fuente(HUB)
        self.assertIn('data-agarrable-fijo="1"', hub)
        self.assertNotIn("estiloAgarrable", hub)
        self.assertIn("vistaZona", hub)

    def test_el_teseracto_principal_no_es_agarrable_con_el_hub_abierto(self):
        overlay = _fuente(OVERLAY)
        bloque = overlay.split("const entidadAgarrable =", 1)[1].split(";", 1)[0]
        self.assertIn("!specialistsHubActive", bloque)

    def test_restablecer_devuelve_todo_a_identidad_y_suelta(self):
        """El zoom que abre la zona no puede quedar acumulado: al abrir y al
        cerrar se restablece, o el teseracto reaparece gigante y reabre el hub."""
        logica = _fuente(LOGICA)
        self.assertIn('case "restablecer"', logica)
        self.assertIn("restablecer", _fuente(USE_GESTOS))
        overlay = _fuente(OVERLAY)
        self.assertIn("restablecer", overlay)
        # Local, como recentrar: el cable nunca puede mandar un restablecer.
        cable = logica.split("export function leerEvento", 1)[1]
        self.assertNotIn('"restablecer"', cable.split("switch", 1)[1].split("default", 1)[0])

    def test_la_seleccion_la_decide_la_vista_no_el_zoom_del_overlay(self):
        """Antes el overlay miraba el zoom de cada core del hub y seleccionaba
        al pasar un umbral: con el carrusel, quien sabe cuándo los vecinos ya
        salieron de pantalla es `vistaZona` (seleccionado), y el hub avisa."""
        hub = _fuente(HUB)
        self.assertIn("seleccionado", hub)
        self.assertIn("onSelectSpecialist", hub)
        overlay = _fuente(OVERLAY)
        self.assertNotIn("idAgarrableEspecialista", overlay)
        # SPECIALISTS sigue en el overlay: de ahí sale el color del elegido.
        self.assertIn("SPECIALISTS", overlay)


class PruebaCarruselYZona(unittest.TestCase):
    def test_el_modulo_puro_existe_con_su_api(self):
        zona = _fuente(ZONA)
        for simbolo in (
            "export const ZONA",
            "export const POSICIONES",
            "export function pasosCarrusel",
            "export function ordenGirado",
            "export function avanzarAcum",
            "export function vistaZona",
            "export function reclamoZona",
            "export function construccionDe",
        ):
            self.assertIn(simbolo, zona, f"zona.ts no exporta {simbolo!r}")

    def test_el_reclamo_de_zona_vacia_cuelga_del_bucle_de_reclamo(self):
        """Dos manos quietas en vacío reclaman la zona por el mismo canal que
        los cores: use-gestos admite la regla extra y la prueba antes que la
        permanencia normal (que exige MÁS quietud, ZONA.permanencia)."""
        use = _fuente(USE_GESTOS)
        self.assertIn("reclamoZona", use)
        overlay = _fuente(OVERLAY)
        self.assertIn("reclamoZona", overlay)
        zona = _fuente(ZONA)
        self.assertRegex(zona, r"permanencia:\s*0\.[6-9]")

    def test_el_pinche_de_la_zona_sujeta_cierra_el_menu(self):
        overlay = _fuente(OVERLAY)
        self.assertIn("pincheCierre", overlay)

    def test_el_menu_espera_un_segundo_antes_de_dejar_agarrar(self):
        """Al entrar, la mano que abrió la zona caía encima del core derecho
        y lo agarraba en el primer cuadro: el hub solo es agarrable pasada la
        ventana de retardo."""
        hub = _fuente(HUB)
        self.assertIn("armado", hub)
        overlay = _fuente(OVERLAY)
        self.assertIn("retardoAgarre", overlay)

    def test_el_giro_se_compromete_antes_de_resetear_los_pasos(self):
        """El updater diferido de setOrden corre DESPUÉS de resetear: leído ahí
        dentro, el compromiso siempre giraba cero ranuras. La rotación se evalúa
        en el momento, en la rama de la suelta, con los pasos que el arrastre
        acumuló (`pasosRef`), antes de ponerlos a cero."""
        hub = _fuente(HUB)
        self.assertNotRegex(
            hub,
            r"setOrden\(\s*\(?o\)?\s*=>\s*ordenGirado\(o,\s*pasosRef",
            "el updater diferido lee pasosRef cuando ya vale cero",
        )
        self.assertIn("setOrden(ordenGirado(orden, pasosRef.current))", hub)
        self.assertIn(
            "const soltando = previoRef.current !== null && estado.agarrado === null",
            hub,
        )


class PruebaTransiciones(unittest.TestCase):
    def test_el_desborde_tiene_su_animacion(self):
        """Abrir la zona no es un corte: el core crece hasta no caber
        (scale 9, opacity 0) y entonces aparece el menú."""
        estilos = _fuente(ESTILOS)
        self.assertIn("@keyframes dark-desborda", estilos)
        overlay = _fuente(OVERLAY)
        self.assertIn("dark-desborda", overlay)
        hub = _fuente(HUB)
        self.assertIn("dark-desborda", hub)

    def test_la_materializacion_habla_el_reloj_del_bloqueo(self):
        hub = _fuente(HUB)
        self.assertIn("construccionDe", hub)
        overlay = _fuente(OVERLAY)
        self.assertIn("construccionDe", overlay)
        zona = _fuente(ZONA)
        self.assertIn("BLOQUEO", zona)

    def test_el_especialista_elegido_conserva_su_color_del_menu(self):
        """La clase de filtro del especialista viaja al núcleo principal:
        sin ella el core seleccionado se pintaba del color de la interfaz."""
        overlay = _fuente(OVERLAY)
        self.assertIn("filterClass", overlay)

    def test_encoger_mucho_cualquier_core_vuelve_al_menu(self):
        """Da igual si es el teseracto original o un especialista: por debajo
        de escalaVuelta se vuelve a la zona (y desde la zona, cerrar)."""
        overlay = _fuente(OVERLAY)
        self.assertIn("escalaVuelta", overlay)


class PruebaGanancia(unittest.TestCase):
    def test_el_motor_declara_las_ganancias_nuevas(self):
        motor = _fuente(MOTOR)
        apertura = re.search(r"^APERTURA_A_ESCALA\s*=\s*([\d.]+)", motor, re.M)
        self.assertIsNotNone(apertura)
        self.assertGreaterEqual(float(apertura.group(1)), 1.5)
        par = re.search(r"^GANANCIA_PAR\s*=\s*([\d.]+)", motor, re.M)
        self.assertIsNotNone(par, "el canal del par sigue dividiendo dist/ref a pelo")
        self.assertGreater(float(par.group(1)), 1.0)


class PruebaClickThrough(unittest.TestCase):
    def test_el_hub_no_captura_el_raton_fuera_de_los_cores(self):
        """Raíz pointer-events-none y solo los cores pointer-events-auto:
        el hook de click-through lee `.pointer-events-auto`, así que fuera de
        los tres cores los clics siguen llegando al escritorio."""
        hub = _fuente(HUB)
        marca = hub.index("dark-specialists-hub")
        raiz = hub[hub.rindex("<div", 0, marca) : hub.index(">", marca)]
        self.assertIn("pointer-events-none", raiz)
        self.assertNotIn("pointer-events-auto", raiz)
        self.assertIn("pointer-events-auto", hub)
        # Una sola aparición en fuente: la lleva el core del `map`, y solo él.
        # Los tres cores del DOM se comprueban en carga real, no aquí.
        self.assertEqual(hub.count("pointer-events-auto"), 1)
        self.assertLess(
            hub.index("pointer-events-auto"),
            hub.index("data-agarrable"),
            "el pointer-events-auto va en la caja agarrable del core",
        )

    def test_el_core_principal_recibe_el_doble_clic(self):
        """Sin pointer-events-auto en la caja del núcleo, el doble clic que
        abre la zona estaba muerto: ningún ancestro lo reactivaba."""
        overlay = _fuente(OVERLAY)
        linea = next(
            l for l in overlay.splitlines() if "dark-core-transform" in l and "className" in l
        )
        self.assertIn("pointer-events-auto", linea)


class PruebaGraciaYSeleccionDePar(unittest.TestCase):
    def test_la_gracia_de_suelta_vive_en_el_config(self):
        """Al soltar un core hay un segundo de cortesía para retirar la mano sin
        que el reclamo por permanencia la vuelva a agarrar encima del mismo
        core. Es una perilla de calibración, como la permanencia."""
        logica = _fuente(LOGICA)
        self.assertRegex(logica, r"graciaSuelta:\s*1")

    def test_el_bucle_de_reclamo_respeta_la_gracia(self):
        use = _fuente(USE_GESTOS)
        self.assertIn("graciaSuelta", use)

    def test_el_par_elige_el_core_que_pisa_la_mano(self):
        """El punto medio del par miente cuando una mano está en el lateral y
        otra en el central: la selección consulta dónde está cada mano, no solo
        el ancla. La regla pura la prueban las pruebas node del reducer."""
        logica = _fuente(LOGICA)
        self.assertIn("objetoDelPar", logica)


class PruebaSueltaAlGiro(unittest.TestCase):
    def test_el_hub_suelta_cuando_el_carrusel_gira_una_ranura(self):
        """El disparo de la soltada es el giro del carrusel (pasos != 0), no el
        primer píxel: el temblor de la mano al agarrar no es un giro. Una sola
        petición por tramo (guarda); la gracia de 1 s del hook hace el resto."""
        hub = _fuente(HUB)
        self.assertIn("onSoltar: () => void", hub)
        self.assertIn("pasosRef.current !== 0", hub)
        self.assertIn("sueltaPedidaRef", hub)
        self.assertIn("onSoltar()", hub)

    def test_el_hook_expone_una_suelta_local_por_giro(self):
        """La zona suelta por el mismo reducer que una suelta normal: una acción
        local `agarre_fin` (como recentrar/restablecer), con motivo propio."""
        use = _fuente(USE_GESTOS)
        self.assertIn('evento: "agarre_fin", motivo: "soltado al girar"', use)
        self.assertIn("soltar: () => void", use)

    def test_el_overlay_pasa_la_suelta_al_hub(self):
        overlay = _fuente(OVERLAY)
        self.assertIn("onSoltar={gestos.soltar}", overlay)

    def test_el_reducer_ya_no_suelta_por_pixeles(self):
        """El disparo por píxeles se quitó: soltaba apenas se agarraba (el temblor
        de la mano supera 1 px) y no dejaba arrastrar. El reducer ya no suelta por
        movimiento ni conserva la marca de la ronda anterior."""
        logica = _fuente(LOGICA)
        self.assertNotIn("soltado al mover", logica)
        self.assertNotIn("sueltaAlMover", logica)

    def test_la_marca_de_suelta_al_mover_desaparece_del_dom_y_del_entorno(self):
        hub = _fuente(HUB)
        self.assertNotIn("data-suelta-al-mover", hub)
        use = _fuente(USE_GESTOS)
        self.assertNotIn("sueltaAlMover", use)


if __name__ == "__main__":
    unittest.main()