"""Regresión para mover estado persistente junto al paquete propietario."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DARK_PYTHON = ROOT / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from utils.rutas_estado import resolver_ruta_estado  # noqa: E402


class PruebasRutasEstado(unittest.TestCase):
    def test_migra_estado_del_paquete_anterior_a_nucleo(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            viejo = raiz / "memoria" / "dark_temas.json"
            viejo.parent.mkdir()
            viejo.write_text('{"turno": 18}', encoding="utf-8")

            nueva = Path(resolver_ruta_estado(
                "nucleo/memoria", "dark_temas.json",
                "memoria/dark_temas.json", raiz=raiz))

            self.assertEqual(
                nueva.read_text(encoding="utf-8"), '{"turno": 18}')
            self.assertFalse(viejo.exists())

    def test_migra_el_archivo_legacy_sin_perder_contenido(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            viejo = raiz / "dark_temas.json"
            viejo.write_text('{"turno": 12}', encoding="utf-8")

            nueva = Path(resolver_ruta_estado(
                "memoria", "dark_temas.json", "dark_temas.json", raiz=raiz))

            self.assertEqual(nueva.read_text(encoding="utf-8"), '{"turno": 12}')
            self.assertFalse(viejo.exists())

    def test_no_sobrescribe_estado_ya_migrado(self):
        with tempfile.TemporaryDirectory() as temporal:
            raiz = Path(temporal)
            viejo = raiz / "dark_memoria.json"
            viejo.write_text('{"origen": "viejo"}', encoding="utf-8")
            nueva = raiz / "memoria" / "dark_memoria.json"
            nueva.parent.mkdir()
            nueva.write_text('{"origen": "nuevo"}', encoding="utf-8")

            resuelta = Path(resolver_ruta_estado(
                "memoria", "dark_memoria.json", "dark_memoria.json", raiz=raiz))

            self.assertEqual(resuelta.read_text(encoding="utf-8"), '{"origen": "nuevo"}')
            self.assertTrue(viejo.exists())


if __name__ == "__main__":
    unittest.main()
