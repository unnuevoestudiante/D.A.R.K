"""Pruebas de validación para la Zona y Menú de Especialistas (Core Hub)."""

import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
SRC = RAIZ / "dark_frontend" / "src"


class PruebaSpecialistsHub(unittest.TestCase):
    def test_componente_specialists_hub_existe(self):
        hub_path = SRC / "components" / "interfaces" / "SpecialistsHub.tsx"
        self.assertTrue(hub_path.exists(), "falta SpecialistsHub.tsx")
        contenido = hub_path.read_text(encoding="utf-8")

        # Verifica la presencia de los 3 especialistas y su identidad visual.
        self.assertIn('id: "coder",\n    name: "Coder"', contenido)
        self.assertIn('id: "tareas",\n    name: "Tareas"', contenido)
        self.assertIn('id: "conversacional",\n    name: "Conversacional"', contenido)
        self.assertIn("specialist-filter-coder", contenido)
        self.assertIn("specialist-filter-tareas", contenido)
        self.assertIn("specialist-filter-conversacional", contenido)

    def test_overlay_soporta_activacion_gestual_y_oculta_titulo(self):
        overlay = (SRC / "components" / "DarkOverlay.tsx").read_text(
            encoding="utf-8"
        )
        # Soporta estado de hub activo y selección de especialista
        self.assertIn("specialistsHubActive", overlay)
        self.assertIn("activeSpecialist", overlay)

        # Oculta el título D.A.R.K. al activar el menú y durante su apertura.
        self.assertIn(
            '{!specialistsHubActive && transicion?.tipo !== "abriendo-hub" && (',
            overlay,
        )

        # Pasa el especialista a EntityComponent
        self.assertIn("specialist={activeSpecialist ?? undefined}", overlay)

        # Contrato de renderizado de SpecialistsHub
        self.assertIn("<SpecialistsHub", overlay)

    def test_contrato_interfaces_soporta_prop_specialist(self):
        tipos = (SRC / "types" / "interfaces.ts").read_text(encoding="utf-8")
        self.assertIn('specialist?: "coder" | "tareas" | "conversacional";', tipos)

    def test_filtros_css_en_styles(self):
        estilos = (SRC / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".specialist-filter-coder", estilos)
        self.assertIn(".specialist-filter-tareas", estilos)
        self.assertIn(".specialist-filter-conversacional", estilos)


if __name__ == "__main__":
    unittest.main()
