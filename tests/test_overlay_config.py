"""Fase B de la normalización del overlay: la config manda y la fábrica es la
única puerta al motor (rama R1). No abre sockets: la fábrica se prueba
con un doble inyectado en sys.modules.
"""
import ast
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from overlay import config, crear_bridge  # noqa: E402

_CLAVES_BRIDGE = ("host", "port", "http_port", "escritorio_vigilia_seg")
_CLAVES_FACHADA = ("pensamiento_timeout_seg", "reposo_diferido_seg",
                   "escucha_timeout_seg")


class FakeBridge:
    """Bridge inerte: registra cómo lo construyeron, no escucha en ningún puerto."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _modulo_fake():
    modulo = types.ModuleType("modulos.dark_overlay_bridge")
    modulo.OverlayBridge = FakeBridge
    return modulo


class PruebaConfig(unittest.TestCase):
    def test_los_defectos_son_los_de_siempre(self):
        self.assertEqual(config.PORT, 8765)
        self.assertEqual(config.HTTP_PORT, 8767)
        self.assertEqual(config.HOST, "0.0.0.0")

    def test_el_entorno_pisa_con_el_tipo_correcto(self):
        env = {"OVERLAY_PORT": "9001", "OVERLAY_HTTP_PORT": "9002",
               "OVERLAY_HOST": "127.0.0.1"}
        with patch.dict("os.environ", env, clear=False):
            self.assertEqual(config._env("PORT", 8765), 9001)
            self.assertEqual(config._env("HTTP_PORT", 8767), 9002)
            self.assertEqual(config._env("HOST", "0.0.0.0"), "127.0.0.1")

    def test_un_value_se_devuelve_el_defecto(self):
        with patch.dict("os.environ", {"OVERLAY_PORT": "no-es-numero"}):
            self.assertEqual(config._env("PORT", 8765), 8765)

    def test_configuracion_dumpa_bridge_y_politica(self):
        self.assertEqual(
            set(config.configuracion()),
            set(_CLAVES_BRIDGE) | set(_CLAVES_FACHADA),
        )

    def test_las_claves_del_bridge_salen_iguales_que_en_config(self):
        volcado = config.configuracion()
        for clave in _CLAVES_BRIDGE:
            self.assertEqual(volcado[clave], getattr(config, clave.upper()))


class PruebaFabrica(unittest.TestCase):
    def test_sin_ajustes_usa_la_config(self):
        with patch.dict(sys.modules, {"modulos.dark_overlay_bridge": _modulo_fake()}):
            bridge = crear_bridge()
        self.assertEqual(bridge.kwargs["host"], config.HOST)
        self.assertEqual(bridge.kwargs["port"], config.PORT)
        self.assertEqual(bridge.kwargs["http_port"], config.HTTP_PORT)

    def test_los_ajustes_pisan_sin_tocar_globales(self):
        with patch.dict(sys.modules, {"modulos.dark_overlay_bridge": _modulo_fake()}):
            bridge = crear_bridge(port=9101, http_port=9102)
        self.assertEqual(bridge.kwargs["port"], 9101)
        self.assertEqual(bridge.kwargs["http_port"], 9102)
        self.assertEqual(config.PORT, 8765)

    def test_el_estado_inicial_y_el_callback_llegan(self):
        def al_mensaje(_texto):
            return None

        with patch.dict(sys.modules, {"modulos.dark_overlay_bridge": _modulo_fake()}):
            bridge = crear_bridge(on_message=al_mensaje, initial_state="lock")
        self.assertEqual(bridge.kwargs["initial_state"], "lock")
        self.assertIs(bridge.kwargs["on_message"], al_mensaje)

    def test_un_ajuste_desconocido_es_error(self):
        with patch.dict(sys.modules, {"modulos.dark_overlay_bridge": _modulo_fake()}):
            with self.assertRaises(ValueError) as ctx:
                crear_bridge(puerto=9101)
        self.assertIn("puerto", str(ctx.exception))

    def test_la_fabrica_devuelve_un_objeto_del_puerto(self):
        from contratos.overlay import PuertoOverlay

        with patch.dict(sys.modules, {"modulos.dark_overlay_bridge": _modulo_fake()}):
            bridge = crear_bridge()
        self.assertFalse(isinstance(bridge, PuertoOverlay))
        self.assertIsInstance(bridge, FakeBridge)


class PruebaBarrera(unittest.TestCase):
    """Nadie fuera de la fábrica importa el motor del overlay."""

    def imports(self, archivo):
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
        salientes = set()
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.ImportFrom) and nodo.module:
                salientes.add(nodo.module)
            elif isinstance(nodo, ast.Import):
                salientes.update(a.name for a in nodo.names)
        return salientes

    def test_el_nucleo_no_importa_el_bridge_concreto(self):
        nucle = self.imports(DARK_PYTHON / "nucleo" / "dark_nucleo.py")
        self.assertNotIn("modulos.dark_overlay_bridge", nucle)
        self.assertIn("overlay", nucle)

    def test_la_fabrica_es_el_unico_importador_del_motor(self):
        MOTOR = "modulos.dark_overlay_bridge"
        importadores = [
            py.name for py in DARK_PYTHON.rglob("*.py")
            if "__pycache__" not in py.parts
            and py.name != "dark_overlay_bridge.py"
            and MOTOR in self.imports(py)
        ]
        self.assertEqual(importadores, ["fabrica.py"])


if __name__ == "__main__":
    unittest.main()
