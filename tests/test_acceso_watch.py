"""Fase C del plan de acceso: WATCH, retiro por ausencia y re-concesión.

Ref: docs/plan-acceso-v2.md §7. No usa cámara ni modelos: sustituye
carga de modelos, base facial y detector de parpadeo por dobles inertes.
"""
import contextlib
import pathlib
import sys
import time
import unittest
from unittest.mock import patch

import numpy as np

RAIZ = pathlib.Path(__file__).resolve().parents[1]
DARK_PYTHON = RAIZ / "dark_python"
if str(DARK_PYTHON) not in sys.path:
    sys.path.insert(0, str(DARK_PYTHON))

try:
    from herramientas import dark_acceso
except ImportError as _error:  # requirements-access.txt no instalado
    _SIN_MOTORES = _error
else:
    _SIN_MOTORES = None

_EMB = np.ones(8, dtype=np.float32)
_EMB /= np.linalg.norm(_EMB)


class _Punto:
    def __init__(self, x, y):
        self.x = x
        self.y = y


def _cara_completa() -> list[_Punto]:
    # _landmarks_5 y _eye_ratio indexan hasta el punto 385 del FaceMesh.
    # Coordenadas variadas a propósito: con puntos degenerados
    # estimateAffinePartial2D devuelve None y VERIFY no progresa.
    return [
        _Punto(0.2 + (i % 37) / 60.0, 0.2 + (i % 29) / 58.0)
        for i in range(468)
    ]


class _Resultado:
    def __init__(self, cara):
        self.face_landmarks = [_cara_completa()] if cara else []


class FakeLandmarker:
    def __init__(self):
        self.cara = True

    def detect(self, imagen):
        return _Resultado(self.cara)

    def close(self):
        pass


class FakeRec:
    def get_feat(self, aligned):
        return _EMB.reshape(1, -1)


class FakeCamera:
    def __init__(self):
        self.abierta = True

    def isOpened(self):
        return self.abierta

    def set(self, *args):
        return True

    def get(self, prop):
        # `VisionService._fijar_modo` lee el modo devuelto para registrarlo.
        return 0.0

    def grab(self):
        return True

    def retrieve(self):
        return True, np.zeros((4, 4, 3), dtype=np.uint8)

    def read(self):
        return self.retrieve()

    def release(self):
        self.abierta = False


class FakeBlink:
    """Doble del reto de parpadeo: supera siempre y deja constancia de
    cuántas veces se recorrió LIVENESS."""
    instancias = 0

    def __init__(self):
        FakeBlink.instancias += 1
        self.blinks = 0

    def update(self, landmarks, width, height):
        self.blinks = 2
        return self.blinks


@contextlib.contextmanager
def gate_facial(fake_face: FakeLandmarker):
    with patch.object(dark_acceso, "_load_database",
                      return_value={"samuel": _EMB}), \
         patch.object(dark_acceso, "_load_models",
                      return_value=(fake_face, FakeRec())), \
         patch.object(dark_acceso.cv2, "VideoCapture",
                      side_effect=lambda _i: FakeCamera()), \
         patch.object(dark_acceso, "_BlinkDetector", FakeBlink):
        yield


# Tiempos cortos inyectados como argumentos: antes havia que pisar los
# globales del módulo, ahora el gate recibe su config por el constructor.
TIEMPOS = {"ausencia_seg": 0.8, "watch_arm_seg": 0.5}


def esperar(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


class _CuadroFalso:
    def __init__(self, imagen):
        self.imagen = imagen


class _SuscriptorFalso:
    """Suscriptor de juguete: da cuadros mientras el servicio esté `viva`.

    Apagada, se duerme el `timeout` y devuelve `None` igual que el servicio real
    cuando no hay nada que entregar; sin ese sueño el hilo del gate giraría al
    máximo y el umbral de cámara no sería observable.
    """

    def __init__(self, servicio):
        self.servicio = servicio
        self.cerrado = False

    def fijar_fps(self, fps):
        self.servicio.fps = fps

    def siguiente(self, timeout=0.5):
        if not self.servicio.viva:
            time.sleep(timeout)
            return None
        time.sleep(0.01)
        return _CuadroFalso(np.zeros((4, 4, 3), dtype=np.uint8))

    def cerrar(self):
        self.cerrado = True


class _ServicioFalso:
    """`VisionService` inyectable con un interruptor de cámara."""

    def __init__(self):
        self.viva = True
        self.fps = None
        self.suscritos = 0
        self.iniciado = False
        self.detenido = False

    def iniciar(self):
        self.iniciado = True

    def detener(self, timeout=5.0):
        self.detenido = True

    def suscribir(self, nombre):
        self.suscritos += 1
        return _SuscriptorFalso(self)


@unittest.skipIf(_SIN_MOTORES, f"motores de visión no instalados: {_SIN_MOTORES}")
class TestCicloWatch(unittest.TestCase):
    def test_concesion_ausencia_rebloqueo_y_reconexion(self):
        fake_face = FakeLandmarker()
        bloqueos: list[str] = []
        concedidos: list[str] = []
        with gate_facial(fake_face):
            FakeBlink.instancias = 0
            gate = dark_acceso.AccessGate(
                on_granted=concedidos.append,
                on_locked=bloqueos.append,
                **TIEMPOS,
            )
            try:
                gate.iniciar()

                # 1) IDLE → VERIFY → LIVENESS → GRANTED (parpadeo fake).
                self.assertTrue(
                    esperar(gate.acceso_concedido.is_set),
                    "no llegó la concesión inicial",
                )
                self.assertEqual(concedidos, ["samuel"])

                # 2) WATCH activo: presencia continua no produce ningún retiro.
                time.sleep(2.0)
                self.assertTrue(gate.acceso_concedido.is_set())
                self.assertEqual(bloqueos, [])

                # 3) Ausencia ≥ AUSENCIA_SEG (tras el armado de WATCH_ARM_SEG)
                #    retira el acceso y arma la re-verificación.
                fake_face.cara = False
                self.assertTrue(
                    esperar(lambda: not gate.acceso_concedido.is_set()),
                    "la ausencia no retiró el acceso",
                )
                self.assertEqual(bloqueos, ["ausencia"])
                self.assertEqual(gate.estado, dark_acceso.LOCKED)

                # 4) La cara vuelve: VERIFY re-concede DIRECTO, sin repetir
                #    el reto de parpadeo (el challenge solo es la primera vez).
                fake_face.cara = True
                self.assertTrue(
                    esperar(gate.acceso_concedido.is_set),
                    "no re-concedió al regresar la cara",
                )
                self.assertEqual(concedidos, ["samuel", "samuel"])
                self.assertEqual(FakeBlink.instancias, 1)
                self.assertNotEqual(gate.estado, dark_acceso.LIVENESS)
            finally:
                gate.detener(timeout=10.0)

    def test_desbloqueo_externo_por_password_tambien_es_vigilado(self):
        fake_face = FakeLandmarker()
        bloqueos: list[str] = []
        with gate_facial(fake_face):
            fake_face.cara = False  # nunca hay cara: sin concesión natural.
            gate = dark_acceso.AccessGate(on_locked=bloqueos.append, **TIEMPOS)
            try:
                gate.iniciar()
                gate.desbloquear()
                self.assertTrue(gate.acceso_concedido.is_set())
                # Sin cara, tras el armado el watcher debe retirar el acceso.
                self.assertTrue(
                    esperar(lambda: not gate.acceso_concedido.is_set(), 10.0),
                    "el watcher no vigiló el desbloqueo por contraseña",
                )
                self.assertEqual(bloqueos, ["ausencia"])
            finally:
                gate.detener(timeout=10.0)

    def test_el_desbloqueo_por_contraseña_notifica_la_concesion(self):
        """El núcleo solo enciende la voz cuando el gate llama a on_granted:
        su Event `_acceso_concedido` no lo setea nadie más. Un desbloqueo
        externo que no notifica deja la contraseña correcta sin efecto."""
        fake_face = FakeLandmarker()
        concedidos: list[str] = []
        with gate_facial(fake_face):
            fake_face.cara = False  # sin cara: la concesión solo puede ser externa
            gate = dark_acceso.AccessGate(
                on_granted=concedidos.append, **TIEMPOS
            )
            try:
                gate.iniciar()
                gate.desbloquear()
                self.assertTrue(gate.acceso_concedido.is_set())
                self.assertTrue(
                    esperar(lambda: bool(concedidos), 5.0),
                    "desbloquear() no notificó on_granted",
                )
                self.assertFalse(
                    gate._rostro_validado,
                    "la contraseña no supera el reto de parpadeo: no debe dar "
                    "el rostro por validado",
                )
            finally:
                gate.detener(timeout=10.0)


@unittest.skipIf(_SIN_MOTORES, f"motores de visión no instalados: {_SIN_MOTORES}")
class TestCamaraMuerta(unittest.TestCase):
    """Falla cerrado: una cámara que deja de entregar cuadros retira el acceso.

    El doble es un `VisionService` inyectado, no `FakeCamera`: lo que se prueba es
    la decisión del gate ante `siguiente() -> None`, y con el servicio real eso
    dependría del ritmo de reabertura de OpenCV. La salida de emergencia se prueba
    aparte: un desbloqueo por contraseña con la cámara ya rota nunca vio cuadros y
    NO puede retirarse, o la contraseña dejaría de servir justo cuando no hay cámara.
    """

    def setUp(self):
        self.servicio = _ServicioFalso()

    def _gate(self, bloqueos):
        return dark_acceso.AccessGate(
            on_locked=bloqueos.append,
            servicio=self.servicio,
            idle_fps=30.0,
            sin_camara_seg=0.5,
            **TIEMPOS,
        )

    def test_la_camara_que_se_apaga_durante_el_acceso_retira_el_acceso(self):
        fake_face = FakeLandmarker()
        bloqueos: list[str] = []
        with gate_facial(fake_face):
            gate = self._gate(bloqueos)
            try:
                gate.iniciar()
                gate.desbloquear()
                self.assertTrue(
                    esperar(lambda: gate.estado == dark_acceso.WATCH, 5.0),
                    "el acceso externo no llegó a vigilarse",
                )
                self.servicio.viva = False       # desconectan la cámara a mitad de sesión
                self.assertTrue(
                    esperar(lambda: not gate.acceso_concedido.is_set(), 10.0),
                    "con la cámara muerta el acceso nunca se retiró",
                )
                self.assertEqual(bloqueos, ["camara"])
                self.assertEqual(gate.estado, dark_acceso.LOCKED)
            finally:
                gate.detener(timeout=10.0)

    def test_la_contraseña_sin_camara_no_bloquea_por_camara_muerta(self):
        fake_face = FakeLandmarker()
        bloqueos: list[str] = []
        with gate_facial(fake_face):
            self.servicio.viva = False           # nunca llega un cuadro
            gate = self._gate(bloqueos)
            try:
                gate.iniciar()
                gate.desbloquear()
                time.sleep(2.0)                  # cuatro veces el umbral de cámara
                self.assertTrue(gate.acceso_concedido.is_set())
                self.assertEqual(bloqueos, [])
            finally:
                gate.detener(timeout=10.0)


if __name__ == "__main__":
    unittest.main()
