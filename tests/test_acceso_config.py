"""Fase E del plan de acceso: la config manda sin editar código.

Ref: docs/plan-acceso-v2.md §9. Solo stdlib — no abre cámara ni carga
modelos, así que corre también en el python sin requirements-access.txt.
"""
import os
import pathlib
import sys
import threading
import types
import unittest
from unittest.mock import patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from acceso import config, crear_gate  # noqa: E402
from acceso.fachada import FachadaAcceso  # noqa: E402

_CLAVES_GATE = ("camera_index", "threshold", "idle_fps",
                "ausencia_seg", "watch_arm_seg")


class FakeGate:
    """Gate inerte: registra cómo lo construyeron y concede al instante."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.acceso_concedido = threading.Event()
        self.iniciado = False

    def iniciar(self):
        self.iniciado = True

    def esperar_acceso(self, timeout=None):
        self.acceso_concedido.set()
        return True

    def desbloquear(self):
        self.acceso_concedido.set()

    def bloquear(self, motivo):
        self.acceso_concedido.clear()


class TestConfigDesdeEntorno(unittest.TestCase):
    def test_lee_float_y_int_con_prefijo_acceso(self):
        con_entorno = {"ACCESO_AUSENCIA_SEG": "12", "ACCESO_CAMERA_INDEX": "2"}
        with patch.dict(os.environ, con_entorno, clear=False):
            self.assertEqual(config._env("AUSENCIA_SEG", 7.0), 12.0)
            self.assertEqual(config._env("CAMERA_INDEX", 0), 2)

    def test_valor_invalido_vuelve_al_defecto(self):
        with patch.dict(os.environ, {"ACCESO_IDLE_FPS": "rapido"}, clear=False):
            self.assertEqual(config._env("IDLE_FPS", 2.0), 2.0)

    def test_texto_sin_valor_por_defecto_es_devuelto_igual(self):
        with patch.dict(os.environ, {"ACCESO_MOTOR": "gestual"}, clear=False):
            self.assertEqual(config._env("MOTOR", "facial"), "gestual")

    def test_configuracion_tiene_toda_la_superficie_tuneable(self):
        valores = config.configuracion()
        self.assertEqual(
            valores,
            {
                "motor": config.MOTOR,
                "boot_timeout": config.BOOT_TIMEOUT,
                **{c: getattr(config, c.upper()) for c in _CLAVES_GATE},
            },
        )


class TestFabricaAplicaConfig(unittest.TestCase):
    def _crear_con_gate_falso(self, **ajustes):
        modulo = types.ModuleType("herramientas.dark_acceso")
        guardado: dict = {}

        class _Gate:
            def __init__(self, **kwargs):
                guardado["kwargs"] = kwargs

        modulo.AccessGate = _Gate
        with patch.dict(sys.modules, {"herramientas.dark_acceso": modulo}):
            crear_gate(**ajustes)
        return guardado["kwargs"]

    def test_sin_ajustes_usa_los_valores_de_config(self):
        kwargs = self._crear_con_gate_falso()
        for clave in _CLAVES_GATE:
            self.assertEqual(kwargs[clave], getattr(config, clave.upper()), clave)

    def test_los_ajustes_pisan_la_config(self):
        kwargs = self._crear_con_gate_falso(ausencia_seg=1.5, watch_arm_seg=0.25)
        self.assertEqual(kwargs["ausencia_seg"], 1.5)
        self.assertEqual(kwargs["watch_arm_seg"], 0.25)

    def test_el_dict_completo_de_config_es_pasable_tal_cual(self):
        kwargs = self._crear_con_gate_falso(**config.configuracion())
        for clave in _CLAVES_GATE:
            self.assertEqual(kwargs[clave], getattr(config, clave.upper()), clave)

    def test_motor_desconocido_dice_las_opciones(self):
        with self.assertRaises(ValueError) as contexto:
            crear_gate(motor="gestual")
        self.assertIn("facial", str(contexto.exception))

    def test_ajuste_inventado_no_sube_silencioso_al_gate(self):
        with self.assertRaises(ValueError) as contexto:
            crear_gate(ausencias=3)
        self.assertIn("ausencias", str(contexto.exception))


_LISTO = threading.Event()
_LISTO.set()


class TestFachadaLeeConfig(unittest.TestCase):
    def test_sin_boot_timeout_manda_el_de_config(self):
        """`verificar_en_background` ya no recibe el timeout del núcleo: lo
        toma de la config, y el timeout sigue siendo acotable por pruebas."""
        fachada = FachadaAcceso()
        esperados: list = []

        class _Gate(FakeGate):
            def esperar_acceso(self, timeout=None):
                esperados.append(timeout)
                return True

        with patch.object(config, "BOOT_TIMEOUT", 3.3):
            fachada.verificar_en_background(
                crear_gate=lambda **kw: _Gate(),
                overlay_ready=_LISTO,
            )
        self.assertEqual(esperados, [3.3])

    def test_boot_timeout_explicito_gana_a_la_config(self):
        fachada = FachadaAcceso()
        esperados: list = []

        class _Gate(FakeGate):
            def esperar_acceso(self, timeout=None):
                esperados.append(timeout)
                return True

        fachada.verificar_en_background(
            crear_gate=lambda **kw: _Gate(),
            overlay_ready=_LISTO,
            boot_timeout=0.1,
        )
        self.assertEqual(esperados, [0.1])


class TestGateValidaSuConfig(unittest.TestCase):
    """Los umbraes de `AccessGate.__init__` solo se ejercitan offline: la
    firma y las validaciones no dependen de los motores."""

    def setUp(self):
        try:
            from herramientas import dark_acceso
        except ImportError as error:
            self.skipTest(f"motores de visión no instalados: {error}")
        self.dark_acceso = dark_acceso

    def _gate(self, **ajustes):
        return self.dark_acceso.AccessGate(**ajustes)

    def test_tiempos_malos_se_rechazan(self):
        for ajustes in ({"ausencia_seg": 0}, {"ausencia_seg": -1},
                        {"watch_arm_seg": -0.5}):
            with self.assertRaises(ValueError, msg=str(ajustes)):
                self._gate(**ajustes)

    def test_config_del_gate_termina_en_attributos(self):
        gate = self._gate(ausencia_seg=9.5, watch_arm_seg=2.5, idle_fps=1.0,
                          threshold=0.6, camera_index=3)
        self.assertEqual((gate.ausencia_seg, gate.watch_arm_seg), (9.5, 2.5))
        self.assertEqual((gate.idle_fps, gate.threshold, gate.camera_index),
                         (1.0, 0.6, 3))


if __name__ == "__main__":
    unittest.main()
