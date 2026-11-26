"""Pruebas de contrato y validación para la variante Nebulosa V2."""

import pathlib
import re
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "dark_frontend" / "src"
ATRIBUTO_V2 = '[data-interfaz="nebulosa-v2"]'


def _sin_comentarios(texto: str) -> str:
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _partes_selector(prelude: str) -> list[str]:
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


def _selectores(texto: str):
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


class PruebaHojaNebulosaV2(unittest.TestCase):
    def test_la_hoja_v2_existe_y_todo_cuelga_del_atributo(self):
        """Ninguna regla de nebulosav2.css puede alcanzar el DOM de la base:
        cada selector compuesto lleva [data-interfaz="nebulosa-v2"]."""
        hoja = SRC / "nebulosav2.css"
        self.assertTrue(hoja.exists(), "falta la hoja nebulosav2.css")
        for prelude in _selectores(hoja.read_text(encoding="utf-8")):
            for parte in _partes_selector(prelude):
                self.assertIn(
                    ATRIBUTO_V2,
                    parte,
                    f"regla sin atributo de variante v2: {parte!r}",
                )

    def test_la_base_importa_la_hoja_v2(self):
        estilos = (SRC / "styles.css").read_text(encoding="utf-8")
        self.assertIn('@import "./nebulosav2.css";', estilos)


class PruebaRegistroNebulosaV2(unittest.TestCase):
    def test_nebulosa_v2_esta_registrada_con_su_piel(self):
        registro = (SRC / "lib" / "interfaces" / "registry.ts").read_text(
            encoding="utf-8"
        )
        self.assertIn('id: "nebulosa-v2"', registro)
        self.assertIn("skin: SKIN_NEBULOSA_V2", registro)
        self.assertIn('"nebulosa-v2": NebulaV2Interface', registro)
        self.assertIn("NebulaV2Core", registro)


class PruebaComponentesNebulosaV2(unittest.TestCase):
    def test_componente_core_soporta_respiracion_y_ola(self):
        core = (SRC / "components" / "interfaces" / "NebulaV2Core.tsx").read_text(
            encoding="utf-8"
        )
        # Soporta ola de choque, dispersión y reconstrucción
        self.assertIn("ola_choque", core)
        self.assertIn("dispersion", core)
        self.assertIn("reconstruccion", core)
        self.assertIn("dispararOnda", core)

        # Soporta respiración orgánica y respuesta a voz
        self.assertIn("respiracionBase", core)
        self.assertIn("respiracionVoz", core)
        self.assertIn("envolventeHabla", core)

    def test_campo_fondo_v2_existe(self):
        campo = (SRC / "components" / "NebulaV2Field.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("NebulaV2Field", campo)
        self.assertIn("dark-nebulosa-v2-campo", campo)


if __name__ == "__main__":
    unittest.main()
