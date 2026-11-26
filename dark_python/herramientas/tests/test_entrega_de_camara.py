"""Pruebas del registro de entrega real de la cámara.

El número que decide si el techo de los gestos lo pone el aparato o MediaPipe es
cuántos cuadros por segundo *entrega* `VisionService`, contados, no pedidos:
DirectShow contesta `-1` a `CAP_PROP_FPS` y el valor que "dice" el driver es un
deseo. Aquí se prueba las dos mitades del camino: que el servicio guarda lo que
devolvió el driver y lo que contó la ventana, y que el motor gestual los lee para
escribirlos en su línea de rendimiento.
"""
from __future__ import annotations

import time

import numpy as np
import pytest

import herramientas.vision as vision
from herramientas.gestos import GestureEngine

ANCHO = vision.cv2.CAP_PROP_FRAME_WIDTH
ALTO = vision.cv2.CAP_PROP_FRAME_HEIGHT
FPS = vision.cv2.CAP_PROP_FPS


class CamaraQueEntrega:
    """Cámara falsa que da cuadros sin parar, como el camino continuo del bucle."""

    def __init__(self, devuelto=(1280, 720, 30.0)):
        self._valores = {ANCHO: devuelto[0], ALTO: devuelto[1], FPS: devuelto[2]}
        self._cuadro = np.zeros((8, 8, 3), dtype=np.uint8)
        self.abierta = True
        self.libera = 0

    def isOpened(self):
        return self.abierta

    def set(self, _prop, _valor):
        return True

    def get(self, prop):
        return float(self._valores.get(int(prop), 0.0))

    def read(self):
        return True, self._cuadro

    def grab(self):
        return True

    def retrieve(self):
        return True, self._cuadro

    def release(self):
        self.libera += 1
        self.abierta = False


def esperar(predicate, timeout=4.0):
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# --- el servicio: qué guarda --------------------------------------------------

def test_el_modo_efectivo_es_lo_que_devuelve_el_driver_no_lo_que_se_pidio():
    """Pedido 60, devuelto 30: lo que se registra es el 30."""
    servicio = vision.VisionService(0, ancho=1280, alto=720, fps=60.0, codificador="mjpg")
    servicio._fijar_modo(CamaraQueEntrega())
    assert servicio.modo_efectivo == (1280, 720, 30.0)


def test_sin_pedir_nada_tambien_se_registra_el_modo_del_driver():
    """El default del driver es un dato, no la ausencia de dato."""
    servicio = vision.VisionService(0)
    servicio._fijar_modo(CamaraQueEntrega(devuelto=(640, 480, 30.0)))
    assert servicio.modo_efectivo == (640, 480, 30.0)


def test_si_leer_el_modo_explota_queda_sin_medida_y_no_sin_cero():
    """`None` es "no lo sé"; un `(0, 0, 0.0)` se leería como un modo real."""
    class CamaraQueFalla(CamaraQueEntrega):
        def get(self, _prop):
            raise OSError("el driver no contesta")

    servicio = vision.VisionService(0, ancho=1280)
    servicio._fijar_modo(CamaraQueFalla())
    assert servicio.modo_efectivo is None


def test_al_nacer_no_hay_entrega_registrada():
    assert vision.VisionService(0).fps_entregados == 0.0


# --- el servicio: el bucle cuenta de verdad ----------------------------------

def test_ventana_continua_publica_la_entrega_contada(monkeypatch):
    """La ventana corta se puede acortar porque es una constante de módulo."""
    camara = CamaraQueEntrega()
    monkeypatch.setattr(vision.cv2, "VideoCapture", lambda _i: camara)
    monkeypatch.setattr(vision, "FPS_VENTANA_SEG", 0.05)

    servicio = vision.VisionService(0, ancho=1280, alto=720, fps=60.0, codificador="mjpg")
    sub = servicio.suscribir("motor")
    sub.fijar_fps(30.0)          # por debajo de UMBRAL_LECTURA_CONTINUA no se cuenta
    servicio.iniciar()
    try:
        assert esperar(lambda: servicio.fps_entregados > 0.0), (
            "el bucle nunca registró una ventana de entrega"
        )
        assert servicio.modo_efectivo == (1280, 720, 30.0)

        # Sin consumidores la cámara se libera y el contador no puede seguir
        # presumiendo de vivo.
        sub.cerrar()
        assert esperar(lambda: servicio.fps_entregados == 0.0), (
            "la entrega vieja sobrevivió a la liberación de la cámara"
        )
        assert camara.libera == 1
    finally:
        servicio.detener()


# --- el motor: los lee y los escribe ----------------------------------------

class ServicioConMedida:
    fps_entregados = 24.0
    modo_efectivo = (1280, 720, 30.0)


class ServicioSinMedida:
    """Los dobles de prueba de siempre: no saben de estos dos números."""


@pytest.mark.parametrize(
    "servicio, esperado",
    [
        (ServicioConMedida(), (24.0, "1280x720@30.0")),
        (ServicioSinMedida(), (0.0, "sin medida")),
        (None, (0.0, "sin cámara")),
    ],
)
def test_el_motor_informa_de_lo_que_llega_sin_romperse_si_no_llega(servicio, esperado):
    assert GestureEngine(servicio=servicio)._entrega_de_camara() == esperado
