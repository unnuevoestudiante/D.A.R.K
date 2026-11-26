"""Fase C del overlay: la política de pintado y los temporales viven en la
fachada, no en el núcleo.

Solo stdlib: el bridge es un doble que registra lo que le piden, sin sockets.
Ref: dark_python/overlay/fachada.py, contratos/overlay.py.
"""
import pathlib
import sys
import time
import unittest
from unittest.mock import Mock

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from contratos.overlay import PuertoOverlay  # noqa: E402
from overlay import FachadaOverlay, config  # noqa: E402


class BridgeFalso:
    """Registra qué le emiten y guarda el estado como hace el puente real."""

    def __init__(self, estado="idle"):
        self.emitidos = []
        self.silenciosos = []
        self.silenciar_llamadas = 0
        self.reactivar_llamadas = 0
        self._estado = estado
        self._resultados = None

    def estado(self):
        return self._estado

    def tiene_resultados(self):
        return bool(self._resultados)

    def set(self, state, text=None, level=None, menu_data=None,
            results_data=None, progress=None):
        self.emitidos.append(state)
        self._estado = state
        if results_data is not None:
            self._resultados = results_data
        if state == "idle":
            self._resultados = None

    def actualizar_sin_emitir(self, state, text=None, menu_data=None,
                              results_data=None):
        self.silenciosos.append(state)
        self._estado = state
        if results_data is not None:
            self._resultados = results_data

    def silenciar(self):
        self.silenciar_llamadas += 1
        self._estado = "idle"

    def reactivar(self):
        self.reactivar_llamadas += 1

    def level(self, value):
        pass


def esperar(condicion, segundos=2.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return bool(condicion())


class PruebaGuardas(unittest.TestCase):
    def test_sin_permiso_no_se_pinta_nada(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, puede_pintar=lambda state: False)
        facha.pintar("thinking", text="pensando")
        self.assertEqual(bridge.emitidos, [])
        self.assertEqual(bridge.silenciosos, [])

    def test_el_bloqueo_deja_pasar_solo_lock(self):
        """Es la guarda que estaba escrita a mano en _set_overlay."""
        bridge = BridgeFalso()
        facha = FachadaOverlay(
            bridge, puede_pintar=lambda state: state == "lock"
        )
        facha.pintar("listening")
        facha.pintar("lock")
        self.assertEqual(bridge.emitidos, ["lock"])

    def test_en_oculto_se_guarda_estado_sin_emitir(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge)
        facha.ocultar()
        self.assertTrue(facha.oculto)
        self.assertEqual(bridge.silenciar_llamadas, 1)
        facha.pintar("thinking", text="por si vuelve")
        self.assertEqual(bridge.emitidos, [])
        self.assertEqual(bridge.silenciosos, ["thinking"])
        self.assertEqual(bridge.estado(), "thinking")

    def test_mostrar_reactiva_y_sale_de_oculto(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge)
        facha.ocultar()
        facha.mostrar()
        self.assertFalse(facha.oculto)
        self.assertEqual(bridge.reactivar_llamadas, 1)
        self.assertEqual(bridge.emitidos, ["listening"])

    def test_se_traza_aunque_este_oculto(self):
        vistos = []
        bridge = BridgeFalso(estado="idle")
        facha = FachadaOverlay(bridge, al_cambiar_estado=lambda a, n: vistos.append((a, n)))
        facha.ocultar()
        facha.pintar("speaking", text="hola")
        self.assertEqual(vistos, [("idle", "speaking")])


class PruebaTemporales(unittest.TestCase):
    def test_thinking_colgado_vuelve_a_idle(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, pensamiento_seg=0.05)
        facha.pintar("thinking")
        self.assertTrue(esperar(lambda: bridge.estado() == "idle"))

    def test_si_llega_la_respuesta_el_timer_se_cancela(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, pensamiento_seg=0.05)
        facha.pintar("thinking")
        facha.pintar("speaking", text="ya está")
        time.sleep(0.2)
        self.assertEqual(bridge.estado(), "speaking")

    def test_reposo_diferido_devuelve_a_idle(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, reposo_seg=0.05)
        facha.pintar("speaking")
        facha.armar_reposo()
        self.assertTrue(esperar(lambda: bridge.estado() == "idle"))

    def test_cancelar_reposo_evita_el_idle(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, reposo_seg=0.05)
        facha.pintar("speaking")
        facha.armar_reposo()
        facha.cancelar_reposo()
        time.sleep(0.2)
        self.assertEqual(bridge.estado(), "speaking")

    def test_escucha_por_defecto_no_se_arma(self):
        """El núcleo llamaba al armado sin segundos: el timer nunca existía."""
        self.assertIsNone(config.ESCUCHA_TIMEOUT_SEG)
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge)
        facha.pintar("listening")
        time.sleep(0.2)
        self.assertEqual(bridge.estado(), "listening")

    def test_escucha_armada_no_borra_los_resultados(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, escucha_seg=0.05)
        facha.pintar("listening", results_data={"items": [{"url": "x"}]})
        time.sleep(0.25)
        self.assertEqual(bridge.estado(), "listening")
        self.assertTrue(bridge.tiene_resultados())

    def test_cancelar_timers_apaga_todo(self):
        bridge = BridgeFalso()
        facha = FachadaOverlay(bridge, pensamiento_seg=0.05, reposo_seg=0.05)
        facha.pintar("thinking")
        facha.armar_reposo()
        facha.cancelar_timers()
        time.sleep(0.2)
        self.assertEqual(bridge.estado(), "thinking")
        self.assertIsNone(facha._timer_pensamiento)
        self.assertIsNone(facha._timer_reposo)
        self.assertIsNone(facha._timer_escucha)

    def test_los_tiempos_ven_de_la_config(self):
        facha = FachadaOverlay(BridgeFalso())
        self.assertEqual(facha.pensamiento_seg, config.PENSAMIENTO_TIMEOUT_SEG)
        self.assertEqual(facha.reposo_seg, config.REPOSO_DIFERIDO_SEG)
        self.assertEqual(facha.escucha_seg, config.ESCUCHA_TIMEOUT_SEG)


class PruebaDelegacion(unittest.TestCase):
    def test_la_fachada_es_tambien_el_puerto(self):
        self.assertIsInstance(FachadaOverlay(Mock()), PuertoOverlay)

    def test_las_ordenes_crudas_llegan_al_puente(self):
        bridge = Mock()
        facha = FachadaOverlay(bridge)
        facha.modo_televisor(True)
        bridge.modo_televisor.assert_called_once_with(True)
        facha.publish_audio(b"pcm", rate=16000, width=2, channels=1, text="di")
        bridge.publish_audio.assert_called_once_with(
            b"pcm", rate=16000, width=2, channels=1, text="di"
        )
        facha.set_lock_input_ready(True)
        bridge.set_lock_input_ready.assert_called_once_with(True)
        facha.marcar_tv_cerrar_al_hablar()
        bridge.marcar_tv_cerrar_al_hablar.assert_called_once_with()
        facha.consumir_tv_cerrar_al_hablar()
        bridge.consumir_tv_cerrar_al_hablar.assert_called_once_with()

    def test_set_crudo_no_pasa_por_las_guardas(self):
        """Arranque y cierre pintan a propósito sin política."""
        bridge = Mock()
        facha = FachadaOverlay(bridge, puede_pintar=lambda state: False)
        facha.set("lock")
        bridge.set.assert_called_once()
        self.assertEqual(bridge.estado.called, False)


if __name__ == "__main__":
    unittest.main()
