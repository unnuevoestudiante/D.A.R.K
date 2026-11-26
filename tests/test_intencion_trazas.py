"""Pruebas del registro estructurado de las rutas de intención."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.dark_nucleo import DarkNucleo  # noqa: E402
from nucleo.intenciones.gestor import (  # noqa: E402
    CAPACIDADES_NUCLEO,
    GestorIntenciones,
)


class PruebasTrazasIntencion(unittest.TestCase):
    def _registrar(self, texto, route):
        gestor = GestorIntenciones(CAPACIDADES_NUCLEO)
        resultado = gestor.interpretar(texto)
        nucleo = DarkNucleo.__new__(DarkNucleo)
        nucleo.intencion = gestor
        nucleo._actualizar_traza_intencion(resultado)
        with patch("builtins.print") as imprimir:
            nucleo._registrar_traza_intencion(route)
        return resultado, imprimir.call_args.args[0]

    def test_traza_de_intencion_v3_contiene_campos_sin_texto(self):
        resultado, traza = self._registrar(
            "reprodice música relajante", "intencion")

        self.assertEqual(resultado.action, "reproducir_musica")
        self.assertIn("action=reproducir_musica", traza)
        self.assertIn("score=", traza)
        self.assertIn("matcher=v3", traza)
        self.assertIn("confidence=", traza)
        self.assertIn("route=intencion", traza)
        self.assertNotIn("reprodice música relajante", traza)

    def test_traza_de_no_match_marca_la_ruta_chat(self):
        frase = "Me gusta escuchar música mientras programo"
        resultado, traza = self._registrar(frase, "chat")

        self.assertFalse(resultado.action)
        self.assertIn("action=-", traza)
        self.assertIn("score=", traza)
        self.assertIn("matcher=v3", traza)
        self.assertIn("confidence=", traza)
        self.assertIn("route=chat", traza)
        self.assertNotIn(frase, traza)


if __name__ == "__main__":
    unittest.main()
