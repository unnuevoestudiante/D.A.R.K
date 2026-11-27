"""Contrato del gesto de la variante Nebulosa: deformar, no trasladar.

Solo stdlib y lectura de fuente, como `test_interfaz_nebulosa.py`. La geometría
(la mano cae en el mismo sitio de la pantalla en los dos lienzos, el surco mide
lo mismo aunque la pieza esté ampliada) se prueba con node en
`dark_frontend/src/lib/interfaces/nebulosa-gesto.test.mjs`; aquí se pacta el
CABLEADO que hace llegar esa geometría a la pantalla, y las guardas del lado
contrario: la interfaz base sigue trasladando sus entidades y girándolas con
`tumble`, y su anillo de agarre sigue dibujado.

Las pruebas de la variante nacen rojas en HEAD porque HEAD traslada el centro de
la nebulosa como cualquier otro objeto y no tiene ni estela ni pieza.
"""
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "dark_frontend" / "src"
ATRIBUTO = '[data-interfaz="nebulosa"]'


def fuente(*partes):
    """El fichero con los blancos colapsados: el contrato es lo que se escribe,
    no cómo lo parte prettier. Sin esto, un ternario que se vuelve multilinea
    rompe una guarda que no ha cambiado de significado."""
    return re.sub(r"\s+", " ", SRC.joinpath(*partes).read_text(encoding="utf-8"))


def sin_comentarios(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def bloque_regla(hoja, selector):
    """El cuerpo de la primera regla cuyo preludio sea EXACTAMENTE `selector`."""
    hoja = sin_comentarios(hoja)
    for hallado in re.finditer(r"([^{}]+)\{([^{}]*)\}", hoja):
        if hallado.group(1).strip() == selector:
            return hallado.group(2)
    return None


class PruebaPiezaUnica(unittest.TestCase):
    def test_el_lienzo_sube_los_uniformes_de_la_pieza_y_de_la_mano(self):
        """Sin estos cinco uniformes el shader no recibe ni el giro de la pieza
        ni el rastro: la nebulosa se quedaría quieta por mucho que la mano pase."""
        lienzo = fuente("components", "interfaces", "LienzoNebulosa.tsx")
        for subida in (
            "gl.uniform2f(u.u_pivot",
            "gl.uniform1f(u.u_giro",
            "gl.uniform1f(u.u_escala",
            "gl.uniform1f(u.u_px",
            "gl.uniform4fv(u.u_estela",
        ):
            self.assertIn(subida, lienzo, f"no se sube {subida}")
        self.assertIn("motor.css = { w: lienzo.clientWidth", lienzo)
        self.assertIn("medirLienzo(lienzo, datos.modo, motor.css)", lienzo)

    def test_el_pivote_es_el_corazon_del_nucleo(self):
        """La pieza gira sobre el centro del núcleo, no sobre el centro del
        campo: si no, al girar la nebulosa el núcleo y el fondo se separan."""
        lienzo = fuente("components", "interfaces", "LienzoNebulosa.tsx")
        self.assertIn("function corazonDeLaPieza()", lienzo)
        self.assertIn('".dark-nebulosa-nucleo"', lienzo)
        self.assertIn('corazon: modo === "campo" ? corazonDeLaPieza() : null', lienzo)
        gesto = fuente("lib", "interfaces", "nebulosa-gesto.ts")
        self.assertIn("!esNucleo && corazon !== null", gesto)

    def test_el_nucleo_no_se_gira_dos_veces(self):
        """El giro y la escala los lleva la caja entera (`.dark-core-transform`).
        Aplicarlos también dentro del lienzo sería girar el núcleo dos veces y
        dejarlo desfasado del campo; y escalar el gas dentro de su propio canvas
        lo recorta contra el borde en cuanto crece."""
        nucleo = fuente("components", "interfaces", "NebulaCore.tsx")
        self.assertNotIn("--entity-tumble", nucleo)
        self.assertNotIn("tumble", nucleo)
        self.assertIn("gesto={gesto}", nucleo)
        tipos = fuente("types", "interfaces.ts")
        self.assertIn("gesto?: GestoNebulosa", tipos)

    def test_la_mano_deforma_antes_de_la_pieza(self):
        """El orden es el contrato del surco físico: deformar en coordenadas de
        pantalla y LUEGO aplicar la pieza. Al revés, el surco del campo crecía
        con la escala de la pieza y el del núcleo —que la lleva en el CSS— no, y
        donde los lienzos se solapan se veían dos surcos distintos."""
        gl = fuente("lib", "interfaces", "nebulosa-gl.ts")
        self.assertIn("vec2 uvMano = deformar(uv, avive);", gl)
        self.assertIn("vec2 uvGas = pieza(uvMano);", gl)
        self.assertIn("vec2 uvPieza = pieza(uv);", gl)
        self.assertIn("avive *= 1.0 - m;", gl)

    def test_la_linea_del_input_no_gira_con_la_pieza(self):
        """Se escribe en el renglón: aunque la pieza se haya quedado girada de
        un agarre anterior, la franja sigue pasando por donde está el input."""
        gl = fuente("lib", "interfaces", "nebulosa-gl.ts")
        self.assertIn("float yc = uv.y - (0.5 - u_linea_y);", gl)
        self.assertIn("vec2 pLinea = vec2(uv.x", gl)
        for coordenada in ("uvGas", "uvPieza", "uvMano"):
            self.assertNotIn(
                f"vec2 pLinea = vec2({coordenada}",
                gl,
                "el renglón no puede ir sobre la coordenada de la pieza",
            )

    def test_con_movimiento_reducido_la_pieza_sigue_la_mano_pero_no_hay_rastro(self):
        """El movimiento reducido apaga la deriva del gas, no el gesto: el giro
        y la escala se siguen aplicando (y repintando cuando cambian), y lo que
        no se pinta es la estela, que es movimiento añadido."""
        lienzo = fuente("components", "interfaces", "LienzoNebulosa.tsx")
        self.assertIn("fuente === undefined || reducido", lienzo)
        self.assertIn("|${v.giro}|${v.escala}|${v.pivot[0]}|${v.pivot[1]}", lienzo)


class PruebaDeformacionLocal(unittest.TestCase):
    def test_la_estela_llega_a_los_dos_lienzos_desde_el_overlay(self):
        overlay = fuente("components", "DarkOverlay.tsx")
        self.assertIn('import { useEstela } from "@/lib/gestos/use-estela";', overlay)
        self.assertIn("const estela = useEstela(gestos.estado);", overlay)
        self.assertIn("giro: giroDe(gestos.estado, entityId)", overlay)
        self.assertIn("escala: escalaDe(gestos.estado, entityId)", overlay)
        self.assertEqual(
            overlay.count("gesto={gestoNebulosa}"),
            2,
            "el campo de fondo y la entidad del escenario reciben el mismo gesto",
        )
        campo = fuente("components", "NebulaField.tsx")
        self.assertIn("gesto={gesto}", campo)

    def test_la_estela_vive_en_un_ref_para_no_repintar_el_overlay(self):
        """El motor manda 19-30 cuadros por segundo: si la estela fuera estado de
        React, el overlay entero se repintaría a esa frecuencia. Y el decaimiento
        se calcula al leer, no se integra, para que los dos lienzos —que pintan en
        cuadros distintos— vean exactamente la misma fuerza."""
        hook = fuente("lib", "gestos", "use-estela.ts")
        self.assertIn("useRef<Estela>(ESTELA_INICIAL)", hook)
        self.assertNotIn("useState", hook)
        self.assertIn("performance.now() / 1000", hook)
        estela = fuente("lib", "gestos", "estela.ts")
        self.assertIn("Math.exp(-edad / cfg.tau)", estela)

    def test_la_nebulosa_se_marca_como_no_trasladable(self):
        overlay = fuente("components", "DarkOverlay.tsx")
        self.assertIn('data-agarrable-fijo={esNebulosa ? "1" : undefined}', overlay)
        hook = fuente("lib", "gestos", "use-gestos.ts")
        self.assertIn('fijo: el.dataset["agarrableFijo"] === "1"', hook)

    def test_el_reducer_no_traslada_lo_fijo_pero_lo_gira_y_lo_escala(self):
        logica = fuente("lib", "gestos", "gestos-logica.ts")
        self.assertIn("const fijo = rect?.fijo === true;", logica)
        self.assertIn("rect === null || fijo ? null : cajaNatural(rect, bruta)", logica)
        self.assertIn("dx: estado.fijo ? 0 :", logica)
        self.assertIn("dy: estado.fijo ? 0 :", logica)
        self.assertIn("export function escalaDe(", logica)
        self.assertIn("fijo: false,", logica, "soltar tiene que limpiar la marca")

    def test_el_agarre_de_la_variante_no_dibuja_un_anillo(self):
        """La confirmación del agarre existe, pero en la lengua de la variante:
        un halo de gas cuyo alfa llega a CERO antes de la arista, no el aro de
        1 px de la base."""
        hoja = fuente("nebulosa.css")
        selector = f'{ATRIBUTO} .dark-core-transform[data-agarrado]::after'
        cuerpo = bloque_regla(hoja, selector)
        self.assertIsNotNone(cuerpo, f"falta la regla {selector}")
        self.assertIn("border: 0", cuerpo)
        self.assertIn("box-shadow: none", cuerpo)
        self.assertIn("transparent 72%", cuerpo)
        self.assertNotIn("border-radius: 50%", cuerpo)


class PruebaBaseIntacta(unittest.TestCase):
    """Guardas del lado contrario: tienen que estar verdes ANTES y DESPUÉS."""

    def test_el_anillo_de_agarre_de_la_base_sigue_dibujado(self):
        estilos = fuente("styles.css")
        cuerpo = bloque_regla(estilos, ".dark-core-transform[data-agarrado]::after")
        self.assertIsNotNone(cuerpo)
        self.assertIn("border: 1px solid", cuerpo)
        self.assertIn("border-radius: 50%", cuerpo)

    def test_la_base_sigue_girando_sus_entidades_con_tumble(self):
        estilos = fuente("styles.css")
        cuerpo = bloque_regla(estilos, ".dark-entidad-giro")
        self.assertIsNotNone(cuerpo)
        self.assertIn("rotate(var(--entity-tumble, 0rad))", cuerpo)
        overlay = fuente("components", "DarkOverlay.tsx")
        self.assertIn("tumble={giroDe(gestos.estado, entityId)}", overlay)
        for entidad in ("CyberReactorCore.tsx", "QuantumOrbCore.tsx"):
            fuente_entidad = fuente("components", "interfaces", entidad)
            self.assertIn("useGiroEntidad(active,", fuente_entidad)
            self.assertIn(
                "tumble={tumbleAngle}",
                fuente_entidad,
                f"{entidad} dejó de pasar el giro a su figura",
            )
        self.assertIn(
            '"--entity-tumble": `${tumble}rad`',
            fuente("components", "interfaces", "FiguraConstelacion.tsx"),
            "la figura común dejó de aplicar el giro de la mano",
        )
        self.assertIn(
            "const giro4d = typeof tumble",
            fuente("components", "TesseractCore.tsx"),
            "el teseracto sigue girando en 4D con la mano",
        )

    def test_la_base_no_lleva_la_marca_de_no_trasladable(self):
        """La marca es condicional a la piel: con la interfaz base puesta el
        atributo no se escribe, y el teseracto se traslada como siempre."""
        overlay = fuente("components", "DarkOverlay.tsx")
        self.assertIn("const esNebulosa = skin === SKIN_NEBULOSA;", overlay)
        self.assertNotIn('data-agarrable-fijo="1"', overlay)
        logica = fuente("lib", "gestos", "gestos-logica.ts")
        self.assertIn("fijo?: boolean", logica)
        self.assertIn(
            "const base = fijo ? { ...encajada, dx: 0, dy: 0 } : encajada;",
            logica,
        )

    def test_el_traslado_de_la_base_sigue_entero(self):
        """El camino de siempre no se ha tocado: la rama no-fija del reducer
        sigue sumando el delta del motor sobre la base del tramo."""
        logica = fuente("lib", "gestos", "gestos-logica.ts")
        self.assertIn("b.dx + (ev.dx / estado.aspecto / span) * entorno.ancho", logica)
        self.assertIn("b.dy + (ev.dy / span) * entorno.alto", logica)
        self.assertIn("escala: b.escala * ev.escala", logica)
        self.assertIn("giro: b.giro + ev.giro", logica)


if __name__ == "__main__":
    unittest.main()