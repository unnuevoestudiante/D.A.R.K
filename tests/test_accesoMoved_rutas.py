"""Fase B del plan de acceso: el moved no debe mover ni una ruta ni una firma.

Ref: docs/plan-acceso-v2.md §6.4 (ancla de rutas de modelos/DB).
"""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

try:
    from herramientas import dark_acceso, vision  # noqa: F401
except ImportError as _error:  # requirements-access.txt no instalado
    _SIN_MOTORES = _error
else:
    _SIN_MOTORES = None


@unittest.skipIf(_SIN_MOTORES, f"motores de visión no instalados: {_SIN_MOTORES}")
class TestRutasAncla(unittest.TestCase):
    def test_modelo_y_db_viven_en_datos_del_usuario_no_en_la_app(self):
        # Decisión del titular (nov 2026): datos biométricos fuera de la carpeta
        # de la aplicación, en el directorio de datos del usuario.
        from acceso import biometria
        self.assertEqual(biometria.ruta_base().name, "faces_db.bin")
        self.assertEqual(biometria.ruta_modelo().name, "face_landmarker.task")
        self.assertNotIn("Reconocimiento Facial", str(biometria.ruta_base()))
        self.assertFalse(hasattr(dark_acceso, "_FACE_DB_PATH"))

    def test_constantes_de_comportamiento_intactas(self):
        for nombre, valor in {
            "THRESHOLD": 0.4, "IDLE_FPS": 2.0, "VERIFY_INTERVAL": 0.25,
            "VERIFY_TIMEOUT": 10.0, "LIVE_TIMEOUT": 8.0,
            "BOOT_ACCESS_TIMEOUT_SECONDS": 60.0, "DENIED_SECONDS": 3.0,
            "CAMERA_RETRY_SECONDS": 2.0, "FACE_LOST_SECONDS": 2.0,
            "WATCH_ARM_SEG": 5.0, "AUSENCIA_SEG": 7.0,
        }.items():
            self.assertEqual(getattr(dark_acceso, nombre), valor, nombre)

    def test_vision_y_gate_comparten_el_mismo_blink_detector(self):
        self.assertIs(dark_acceso._BlinkDetector, vision._BlinkDetector)

    def test_gate_instancia_y_cumple_puerto(self):
        from contratos import PuertoAcceso
        gate = dark_acceso.AccessGate()
        self.assertIsInstance(gate, PuertoAcceso)
        self.assertEqual(gate.estado, dark_acceso.IDLE)


if __name__ == "__main__":
    unittest.main()
