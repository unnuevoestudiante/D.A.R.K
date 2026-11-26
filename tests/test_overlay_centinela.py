"""El centinela de reposo: las dos señales del PC que lo gobiernan.

`fullscreenApp` lo esconde con un juego o un video a pantalla completa y
`pulso` alimenta su telemetría. Las dos son del PC: la tele no las ve.
"""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from overlay import escritorio  # noqa: E402


def bridge_inerte():
    from modulos.dark_overlay_bridge import OverlayBridge

    b = OverlayBridge.__new__(OverlayBridge)
    b._state = {"state": "idle", "fullscreenApp": False, "pulso": None,
                "desktopShown": False}
    b.emitidos = 0

    def _broadcast():
        b.emitidos += 1

    b._broadcast = _broadcast
    return b


class PruebaSenales(unittest.TestCase):
    def test_pantalla_completa_emite_solo_al_cambiar(self):
        b = bridge_inerte()
        b.set_pantalla_completa(False)
        self.assertEqual(b.emitidos, 0)
        b.set_pantalla_completa(True)
        b.set_pantalla_completa(True)
        self.assertEqual(b.emitidos, 1)
        self.assertTrue(b._state["fullscreenApp"])

    def test_pulso_emite_solo_al_cambiar(self):
        b = bridge_inerte()
        b.set_pulso({"cpu": 10, "ram": 50})
        b.set_pulso({"cpu": 10, "ram": 50})
        b.set_pulso({"cpu": 11, "ram": 50})
        self.assertEqual(b.emitidos, 2)

    def test_la_tele_no_recibe_las_senales_del_pc(self):
        from modulos.dark_overlay_bridge import OverlayBridge

        fuente = pathlib.Path(sys.modules[OverlayBridge.__module__].__file__)
        cuerpo = fuente.read_text(encoding="utf-8")
        inicio = cuerpo.index("def estado_para_tv")
        tramo = cuerpo[inicio:inicio + 1500]
        self.assertIn('base.pop("fullscreenApp", None)', tramo)
        self.assertIn('base.pop("pulso", None)', tramo)


class PruebaSondas(unittest.TestCase):
    def test_las_sondas_nunca_lanzan(self):
        self.assertIsInstance(escritorio.pantalla_completa(), bool)
        pulso = escritorio.pulso_del_equipo()
        if pulso is not None:
            self.assertEqual(set(pulso), {"cpu", "ram"})
            for v in pulso.values():
                self.assertTrue(0 <= v <= 100)


if __name__ == "__main__":
    unittest.main()
