"""Pruebas del modo de captura de `VisionService` y de cómo lo pide la fábrica.

Nada de esto toca una cámara real: `CamaraFalsa` registra los `set()` en orden y
devuelve lo que le pongamos en los `get()`. Lo que se prueba es el contrato
delgado pero delicado entre el código y un driver de Windows: qué se pide, en qué
orden, y que sin pedir nada el comportamiento es exactamente el de siempre.
"""
from __future__ import annotations

import logging

import cv2
import pytest

from herramientas.vision import VisionService

ANCHO = cv2.CAP_PROP_FRAME_WIDTH
ALTO = cv2.CAP_PROP_FRAME_HEIGHT
FPS = cv2.CAP_PROP_FPS
FOURCC = cv2.CAP_PROP_FOURCC
BUFFER = cv2.CAP_PROP_BUFFERSIZE


class CamaraFalsa:
    def __init__(self, devuelto=(1280, 720, 30.0)):
        self.sets: list[tuple[int, float]] = []
        self._valores = {ANCHO: devuelto[0], ALTO: devuelto[1], FPS: devuelto[2]}

    def set(self, prop, valor):
        self.sets.append((int(prop), valor))
        return True

    def get(self, prop):
        return float(self._valores.get(int(prop), 0.0))


def test_pedir_modo_fija_el_codificador_antes_del_tamano():
    """Con el fourcc después del tamaño, varios drivers se quedan en YUY2."""
    camara = CamaraFalsa()
    servicio = VisionService(0, ancho=1280, alto=720, fps=60.0, codificador="mjpg")
    servicio._fijar_modo(camara)
    orden = [p for p, _ in camara.sets]
    assert orden == [FOURCC, ANCHO, ALTO, FPS]
    assert camara.sets[0][1] == cv2.VideoWriter_fourcc(*"MJPG")
    assert camara.sets[3] == (FPS, 60.0)


def test_sin_pedido_no_se_toca_nada_del_driver():
    """Los llamadores viejos (`VisionService(indice)`) siguen con el default."""
    camara = CamaraFalsa()
    VisionService(0)._fijar_modo(camara)
    assert camara.sets == []


def test_cada_knob_se_pide_por_separado():
    camara = CamaraFalsa()
    VisionService(0, ancho=640)._fijar_modo(camara)
    assert camara.sets == [(ANCHO, 640)]

    camara = CamaraFalsa()
    VisionService(0, fps=30.0)._fijar_modo(camara)
    assert camara.sets == [(FPS, 30.0)]


def test_el_log_registra_lo_devuelto_no_lo_pedido(caplog):
    """El driver pidió 60 y devolvió 30: eso es lo que tiene que decir el log."""
    camara = CamaraFalsa(devuelto=(1280, 720, 30.0))
    servicio = VisionService(0, ancho=1920, alto=1080, fps=60.0, codificador="MJPG")
    with caplog.at_level(logging.INFO, logger="herramientas.vision"):
        servicio._fijar_modo(camara)
    mensaje = " ".join(r.message for r in caplog.records)
    assert "pedido MJPG 1920x1080@60" in mensaje
    assert "1280x720@30.0" in mensaje


def test_la_fabrica_pasa_la_config_completa(monkeypatch):
    from acceso import config, fabrica

    monkeypatch.setattr(config, "CAMARA_ANCHO", 800, raising=False)
    monkeypatch.setattr(config, "CAMARA_ALTO", 600, raising=False)
    monkeypatch.setattr(config, "CAMARA_FPS", 24.0, raising=False)
    monkeypatch.setattr(config, "CAMARA_CODIFICADOR", "YUY2", raising=False)
    servicio = fabrica.crear_servicio_camara()
    assert (servicio.ancho, servicio.alto, servicio.fps, servicio.codificador) == (
        800,
        600,
        24.0,
        "YUY2",
    )


def test_los_kwargs_pisan_la_config():
    from acceso import fabrica

    servicio = fabrica.crear_servicio_camara(ancho=320, codificador="")
    assert servicio.ancho == 320
    assert servicio.codificador == ""


@pytest.mark.parametrize("texto", ["mjpg", "MJPG", " mjpg "])
def test_el_codificador_se_normaliza(texto):
    assert VisionService(0, codificador=texto).codificador == "MJPG"


class CamaraQueFalla:
    """Un driver que no contesta a `set`/`get`: no tiene por qué tumbar la cámara."""

    def set(self, *args):
        raise OSError("driver ocupado")

    def get(self, prop):
        raise OSError("driver ocupado")


def test_un_driver_que_no_contesta_no_rompe_el_servicio(caplog):
    with caplog.at_level(logging.WARNING, logger="herramientas.vision"):
        VisionService(0, ancho=1280, alto=720, fps=60.0, codificador="MJPG")._fijar_modo(
            CamaraQueFalla()
        )
    assert "se usa el que trae el driver por defecto" in " ".join(
        r.message for r in caplog.records
    )
