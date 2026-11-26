"""Fase A del plan de acceso: el contrato debe existir, ser puro y cumplirse.

Ref: docs/plan-acceso-v2.md §5 (contratos/acceso.py) y §10 (pruebas).
"""
import ast
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos import Estados, PuertoAcceso  # noqa: E402
from contratos import acceso as modulo_acceso  # noqa: E402

PROHIBIDOS = {"cv2", "numpy", "mediapipe", "insightface", "onnxruntime", "psutil"}


class TestPurezaContratos(unittest.TestCase):
    def test_paquete_contratos_no_importa_motores(self):
        for archivo in sorted((DARK_PYTHON / "contratos").glob("*.py")):
            arbol = ast.parse(archivo.read_text(encoding="utf-8"))
            importados = set()
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    importados |= {a.name.split(".")[0] for a in nodo.names}
                elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
                    importados.add(nodo.module.split(".")[0])
            with self.subTest(archivo=archivo.name):
                self.assertFalse(importados & PROHIBIDOS,
                                 f"{archivo.name} importa motores: {importados & PROHIBIDOS}")


class TestEstados(unittest.TestCase):
    def test_orden_y_literales_compatibles_con_el_gate(self):
        esperados = ["IDLE", "VERIFY", "LIVENESS", "GRANTED", "DENIED", "LOCKED", "WATCH"]
        self.assertEqual([e.value for e in Estados], esperados)

    def test_valores_cadenas_siguen_iguales_que_dark_acceso(self):
        for nombre in ["IDLE", "VERIFY", "LIVENESS", "GRANTED", "DENIED", "LOCKED"]:
            self.assertEqual(getattr(Estados, nombre).value, nombre)


class TestPuerto(unittest.TestCase):
    def test_protocolo_es_runtime_checkable(self):
        self.assertTrue(getattr(PuertoAcceso, "_is_runtime_protocol", False))

    def test_gate_facial_actual_cumple_el_puerto(self):
        try:
            from herramientas.dark_acceso import AccessGate
        except ImportError as error:  # dependencias de requirements-access.txt
            self.skipTest(f"motores de visión no instalados: {error}")
        self.assertIsInstance(AccessGate(), PuertoAcceso)

    def test_firma_de_esperar_acceso_acepta_timeout_nulo(self):
        import inspect
        firma = inspect.signature(PuertoAcceso.esperar_acceso)
        self.assertIsNone(firma.parameters["timeout"].default)


if __name__ == "__main__":
    unittest.main()
