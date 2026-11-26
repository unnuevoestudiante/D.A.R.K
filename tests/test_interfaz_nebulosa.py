"""Contrato de la variante Nebulosa: piel completa sin tocar la base.

Solo stdlib y lectura de fuente, como la guarda de `test_gestos_fachada.py`.
La exigencia del diseño es que la variante no altere la interfaz actual: por
eso la hoja `nebulosa.css` solo puede colgar de `[data-interfaz="nebulosa"]`,
y la base (chaflán, núcleo redondo, tesseract sin piel) queda como guarda del
lado contrario — esas pruebas deben seguir verdes con y sin variante.

Las pruebas de la variante nacen rojas en HEAD porque HEAD no tiene variante
(o, tras el checkpoint cc13bb48, porque aún dibujaba filete y vidrio en los
paneles); la hoja sin atributo o el registro sin piel las vuelven rojas también
después.
"""
import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "dark_frontend" / "src"
ATRIBUTO = '[data-interfaz="nebulosa"]'


def _sin_comentarios(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _partes_selector(prelude):
    """Selector compuesto partido por comas a profundidad cero de paréntesis.

    Un `:is(.a, .b)` no se parte por dentro: la coma interna no separa
    selectores independientes.
    """
    partes = []
    actual = []
    prof = 0
    for c in prelude:
        if c == "(":
            prof += 1
        elif c == ")":
            prof -= 1
        if c == "," and prof == 0:
            partes.append("".join(actual).strip())
            actual = []
        else:
            actual.append(c)
    partes.append("".join(actual).strip())
    return [p for p in partes if p]


def _selectores(texto):
    """Preludios de regla de la hoja, recursando en @media/@supports."""
    texto = _sin_comentarios(texto)
    i = 0
    n = len(texto)
    while i < n:
        while i < n and texto[i].isspace():
            i += 1
        if i >= n:
            break
        j = i
        prof = 0
        while j < n:
            c = texto[j]
            if c == "(":
                prof += 1
            elif c == ")":
                prof -= 1
            elif c == "{" and prof == 0:
                break
            j += 1
        prelude = texto[i:j].strip()
        k = j + 1
        prof = 1
        while k < n and prof:
            if texto[k] == "{":
                prof += 1
            elif texto[k] == "}":
                prof -= 1
            k += 1
        cuerpo = texto[j + 1 : k - 1]
        if prelude.startswith(("@media", "@supports")):
            yield from _selectores(cuerpo)
        elif not prelude.startswith("@"):
            yield prelude
        i = k


class PruebaHojaVariante(unittest.TestCase):
    def test_la_hoja_existe_y_todo_cuelga_del_atributo(self):
        """Ninguna regla de nebulosa.css puede alcanzar el DOM de la base:
        cada selector compuesto lleva el atributo de la variante."""
        hoja = SRC / "nebulosa.css"
        self.assertTrue(hoja.exists(), "falta la hoja de la variante")
        for prelude in _selectores(hoja.read_text(encoding="utf-8")):
            for parte in _partes_selector(prelude):
                self.assertIn(
                    ATRIBUTO,
                    parte,
                    f"regla sin atributo de variante: {parte!r}",
                )

    def test_la_base_importa_la_hoja(self):
        estilos = (SRC / "styles.css").read_text(encoding="utf-8")
        self.assertIn('@import "./nebulosa.css";', estilos)

    def test_los_paneles_se_disuelven_sin_filete_ni_vidrio(self):
        """La piel no dibuja cajas: ni filete de 1 px ni `backdrop-filter` (el
        vidrio dejaba un rectángulo visible aunque el fondo se apagara). El
        suelo de los paneles se enmascara hasta alfa cero fuera del borde: un
        desvanecido que no llega a cero deja la arista visible."""
        css = _sin_comentarios(
            (SRC / "nebulosa.css").read_text(encoding="utf-8")
        )
        self.assertNotIn("border: 1px", css)
        self.assertNotIn("backdrop-filter:", css)
        self.assertIn("inset: -30px", css)
        self.assertIn("transparent 62%", css)
        # El suelo tiene que morir DENTRO de su propia caja: con semieje 100% el
        # borde quedaba a distancia 0.5 (zona opaca) y la losa mostraba arista.
        self.assertIn("50% 50% at 50% 50%, #000 55%", css)

    def test_el_hover_y_las_etiquetas_hablan_la_lengua_del_gas(self):
        """Sobre la imagen disuelta no puede quedar un rectángulo teñido ni una
        caja negra: el velo del hover muere con la misma máscara que la imagen
        y las etiquetas (índice, «ver opciones») llevan suelo difuminado."""
        css = _sin_comentarios(
            (SRC / "nebulosa.css").read_text(encoding="utf-8")
        )
        self.assertIn(".dark-result-card .h-56 > div", css)
        self.assertIn(".dark-result-card .h-56 > span::before", css)


class PruebaRegistro(unittest.TestCase):
    def test_la_variante_esta_registrada_con_piel(self):
        registro = (SRC / "lib" / "interfaces" / "registry.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('id: "nebulosa"', registro)
        self.assertIn("skin: SKIN_NEBULOSA", registro)
        tipos = (SRC / "types" / "interfaces.ts").read_text(encoding="utf-8")
        self.assertIn("skin?: string", tipos)

    def test_la_interfaz_base_no_lleva_piel(self):
        """Guarda del lado contrario: el tesseract de HEAD no lleva skin y
        tampoco puede llevarla después; la piel es solo de la variante."""
        registro = (SRC / "lib" / "interfaces" / "registry.ts").read_text(
            encoding="utf-8"
        )
        bloque = re.search(
            r"export const TesseractInterface[^=]*=\s*\{(.*?)\n\};",
            registro,
            re.S,
        )
        self.assertIsNotNone(bloque)
        self.assertNotIn("skin", bloque.group(1))


class PruebaLenguajeBase(unittest.TestCase):
    def test_la_base_conserva_chaflan_y_nucleo_redondo(self):
        """Guarda del lado contrario: la silueta chaflanada y el escenario
        redondo de la base siguen estando; la variante los apaga solo bajo
        su atributo, no los borra de la hoja base."""
        estilos = (SRC / "styles.css").read_text(encoding="utf-8")
        recorte = re.search(r"\.dark-recorte\s*\{([^}]*)\}", estilos)
        self.assertIsNotNone(recorte)
        self.assertIn("clip-path: polygon(", recorte.group(1))
        shell = re.search(r"\.dark-core-shell\s*\{([^}]*)\}", estilos)
        self.assertIsNotNone(shell)
        self.assertIn("border-radius: 50%", shell.group(1))

    def test_el_anillo_no_pisa_el_absolute_de_las_cartas(self):
        """Guarda del centrado: la hoja base no puede declarar `position` en
        `.dark-carrusel-card` sin capa, porque pisaría al utility `absolute` del
        componente y volvería las cartas ítems flex en fila (solape + descentrado).
        El componente es quien posiciona; la base solo aporta el aislamiento."""
        estilos = (SRC / "styles.css").read_text(encoding="utf-8")
        bloque = re.search(r"\.dark-carrusel-card\s*\{([^}]*)\}", estilos)
        self.assertIsNotNone(bloque)
        self.assertNotIn("position:", bloque.group(1))
        componente = (
            SRC / "components" / "InterfaceRingCarousel.tsx"
        ).read_text(encoding="utf-8")
        self.assertIn("absolute w-[280px]", componente)


if __name__ == "__main__":
    unittest.main()