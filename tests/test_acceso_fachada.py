"""Fase D del plan de acceso: la fachada aplica la política sin tocar el núcleo.

Ref: docs/plan-acceso-v2.md §8. El FakeGate implementa PuertoAcceso de
mentirillas; nada aquí necesita cámara ni modelos.
"""
import pathlib
import sys
import threading
import time
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

from acceso import FachadaAcceso  # noqa: E402
from contratos import PuertoAcceso  # noqa: E402


class FakeGate:
    def __init__(self, on_granted=None, on_locked=None):
        self.acceso_concedido = threading.Event()
        self.estado = "IDLE"
        self._on_granted = on_granted
        self._on_locked = on_locked
        self.iniciado = False

    def iniciar(self):
        self.iniciado = True

    def esperar_acceso(self, timeout=None):
        return self.acceso_concedido.wait(timeout)

    def bloquear(self, motivo):
        self.acceso_concedido.clear()
        self.estado = "LOCKED"
        if self._on_locked:
            self._on_locked(motivo)

    def desbloquear(self):
        self.acceso_concedido.set()
        self.estado = "GRANTED"
        if self._on_granted:
            self._on_granted("password")

    def detener(self, timeout=5.0):
        pass


class TestPuertoFake(unittest.TestCase):
    def test_fake_cumple_el_contrato(self):
        self.assertIsInstance(FakeGate(), PuertoAcceso)


class TestPoliticaPassword(unittest.TestCase):
    def test_password_abre_solo_la_primera_vez(self):
        fachada = FachadaAcceso()
        gate = FakeGate()
        fachada.gate = gate

        self.assertTrue(fachada.desbloquear_por_password())
        self.assertTrue(gate.acceso_concedido.is_set())

        gate.bloquear("ausencia")
        self.assertFalse(gate.acceso_concedido.is_set())
        self.assertFalse(fachada.desbloquear_por_password())
        self.assertFalse(gate.acceso_concedido.is_set(),
                         "el gate no debía recibir el segundo intento")

    def test_sin_gate_la_fachada_igualmente_debe_negar_la_segunda(self):
        fachada = FachadaAcceso()
        self.assertTrue(fachada.desbloquear_por_password())
        self.assertFalse(fachada.desbloquear_por_password())

    def test_rearmar_password_devuelve_el_primer_uso(self):
        """El cambio de contraseña por voz rearma la política: la contraseña
        nueva abre una sola vez, igual que la original."""
        fachada = FachadaAcceso()
        gate = FakeGate()
        fachada.gate = gate

        self.assertTrue(fachada.desbloquear_por_password())
        gate.bloquear("cambio de contraseña")
        self.assertFalse(fachada.desbloquear_por_password())

        fachada.rearmar_password()
        self.assertTrue(fachada.puede_abrir_password)
        self.assertTrue(fachada.desbloquear_por_password())
        self.assertTrue(gate.acceso_concedido.is_set())

        gate.bloquear("ausencia")
        self.assertFalse(fachada.desbloquear_por_password(),
                         "el rearme no debía regalar más de un uso")


class TestEnrutamientoEventos(unittest.TestCase):
    def test_concesion_y_retiro_del_gate_llegan_al_nucleo(self):
        vistos = []
        fachada = FachadaAcceso()
        fachada.registrar(
            al_conceder=lambda nombre: vistos.append(("conceder", nombre)),
            al_retirar=lambda motivo: vistos.append(("retirar", motivo)),
            al_entrar_limitado=lambda motivo: vistos.append(("limitado", motivo)),
        )
        gate = FakeGate(on_granted=fachada._notificar_concesion,
                        on_locked=fachada._notificar_retiro)
        fachada.gate = gate
        gate.desbloquear()
        gate.bloquear("ausencia")
        self.assertEqual(vistos, [("conceder", "password"), ("retirar", "ausencia")])

    def test_verificar_en_background_aplica_timeout_y_reemite_concesion(self):
        ready = threading.Event()
        ready.set()
        vistos = []
        fachada = FachadaAcceso()
        fachada.registrar(
            al_conceder=lambda nombre: vistos.append(("conceder", nombre)),
            al_retirar=lambda motivo: vistos.append(("retirar", motivo)),
            al_entrar_limitado=lambda motivo: vistos.append(("limitado", motivo)),
        )
        gates = []

        def crear(on_granted, on_locked):
            gate = FakeGate(on_granted, on_locked)
            gates.append(gate)
            return gate

        hilo = threading.Thread(
            target=fachada.verificar_en_background,
            args=(crear, ready, 0.2),
            daemon=True,
        )
        hilo.start()
        self.assertTrue(
            _esperar(lambda: ("limitado", "sin verificación tras 0 segundos") in vistos),
            f"no entró en modo limitado: {vistos}",
        )
        self.assertTrue(gates[0].iniciado)
        gates[0].desbloquear()  # la re-verificación en background concede tarde
        self.assertTrue(_esperar(lambda: ("conceder", "password") in vistos),
                        f"no re-emitió la concesión: {vistos}")
        hilo.join(timeout=5)
        self.assertFalse(hilo.is_alive())


def _esperar(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


if __name__ == "__main__":
    unittest.main()
