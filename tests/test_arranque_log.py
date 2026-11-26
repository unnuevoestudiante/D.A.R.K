"""El log de arranque de la ignición: el estado real de cada pieza."""
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from nucleo.arranque_log import piezas_de_arranque  # noqa: E402

CAPACIDADES = {"items": [
    {"id": "voz_entrada", "nivel": "atencion"},
    {"id": "voz_salida", "nivel": "ok"},
    {"id": "vision", "nivel": "error"},
]}


def estados(**kw):
    return {p["id"]: p["estado"] for p in piezas_de_arranque(**kw)}


class PruebaLog(unittest.TestCase):
    def test_orden_y_forma(self):
        piezas = piezas_de_arranque(manager_vivo=True, capacidades=CAPACIDADES,
                                    ollama_vivo=True, modelo_cargado=True)
        self.assertEqual([p["id"] for p in piezas], [
            "nucleo", "puente", "manager", "voz_entrada", "voz_salida",
            "modelo_local", "vision"])
        for p in piezas:
            self.assertEqual(set(p), {"id", "nombre", "estado"})

    def test_cada_pieza_dice_su_verdad(self):
        e = estados(manager_vivo=False, capacidades=CAPACIDADES,
                    ollama_vivo=True, modelo_cargado=False)
        self.assertEqual(e["manager"], "sin_respuesta")
        self.assertEqual(e["voz_entrada"], "en_espera")
        self.assertEqual(e["voz_salida"], "en_linea")
        self.assertEqual(e["vision"], "sin_respuesta")
        # Ollama vivo sin el modelo en memoria: en espera, no un fallo.
        self.assertEqual(e["modelo_local"], "en_espera")

    def test_lo_que_aun_no_se_sabe_esta_cargando(self):
        e = estados(manager_vivo=None, capacidades=None,
                    ollama_vivo=None, modelo_cargado=None)
        for ident in ("manager", "voz_entrada", "voz_salida", "modelo_local", "vision"):
            self.assertEqual(e[ident], "cargando", ident)
        self.assertEqual(e["nucleo"], "en_linea")

    def test_ollama_caido(self):
        self.assertEqual(estados(manager_vivo=True, capacidades=CAPACIDADES,
                                 ollama_vivo=False, modelo_cargado=None)["modelo_local"],
                         "sin_respuesta")


class PruebaPuente(unittest.TestCase):
    def test_publica_solo_al_cambiar_y_no_va_a_la_tele(self):
        from modulos.dark_overlay_bridge import OverlayBridge

        b = OverlayBridge.__new__(OverlayBridge)
        b._state = {"state": "lock"}
        b.emitidos = 0

        def _broadcast():
            b.emitidos += 1

        b._broadcast = _broadcast
        piezas = [{"id": "nucleo", "nombre": "Núcleo", "estado": "en_linea"}]
        b.set_arranque(piezas)
        b.set_arranque(list(piezas))
        self.assertEqual(b.emitidos, 1)
        fuente = pathlib.Path(sys.modules[OverlayBridge.__module__].__file__).read_text(encoding="utf-8")
        tramo = fuente[fuente.index("def estado_para_tv"):][:1600]
        self.assertIn('base.pop("arranque", None)', tramo)


if __name__ == "__main__":
    unittest.main()
