"""Pruebas de la LECTURA: lo que el motor ve de las manos, escrito a disco 1 vez por segundo.

El andamio de calibración tiene dos mitades y esta es la que no se veía. ``video``
manda el cuadro (píxel) y el panel del navegador pinta los números que llegan por
el cable; pero el cable solo publica las manos ya CONFIRMADAS, así que cuando la
sesión no enganchaba no había dónde mirar: ni la mano pendiente, ni el `quietud`
acumulado, ni por qué la máquina no decidía nada.

La lectura es esa otra mitad: una línea por `LECTURA_CADA` con todo lo que el
detector produjo en el cuadro. Banco sintético el de ``test_gestos_puno.py``.

Lo segundo que se vigila, porque es una promesa del docstring: la lectura MIRA y no
TOCA. Hay una prueba que corre la misma secuencia con y sin lectura y exige que los
eventos salgan idénticos.
"""
from __future__ import annotations

import asyncio
import json
import logging
import socket

import numpy as np
import pytest
import websockets

try:
    from herramientas import dark_gestos_canal as c
except ImportError:  # pruebas sueltas junto al módulo
    import dark_gestos_canal as c

try:
    from .test_gestos_puno import ABIERTA, DT, PUNO, Banco, g  # noqa: F401
except ImportError:
    from test_gestos_puno import ABIERTA, DT, PUNO, Banco, g  # noqa: F401

X, Y = 0.6, 0.5


def _det(x: float, y: float, apertura: float, *, pinza: float = -1.0,
         indice: float = -1.0, dedo_max: float = -1.0,
         giro: float = 0.0) -> "g._Deteccion":
    return g._Deteccion(
        ancla=np.array([x, y]), palma=0.12, apertura=apertura, vertical=True,
        etiqueta="Right", puntaje=0.95, pts=np.zeros((21, 2)), dedo_max=dedo_max,
        pinza=pinza, indice=apertura if indice < 0 else indice, giro=giro,
    )


@pytest.fixture
def banco() -> Banco:
    return Banco()


def _lineas(caplog) -> list[str]:
    """Las líneas de lectura capturadas, sin la palabra `lectura`."""
    return [
        r.getMessage()[len("lectura "):]
        for r in caplog.records if r.getMessage().startswith("lectura ")
    ]


def test_sin_lectura_no_escribe_nada(banco, caplog):
    """Apagada por defecto: una sesión normal no se llena de líneas de 1 Hz."""
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.armar(X, Y)
        banco.correr(3.0, (X, Y, ABIERTA))
    assert _lineas(caplog) == []


def test_una_linea_por_ventana_y_ni_una_mas(banco, caplog):
    """Tres segundos dan tres líneas, ni cuatro ni dos: el goteo es el pactado."""
    banco.armar(X, Y)
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.correr(3.0, (X, Y, ABIERTA))
    assert len(_lineas(caplog)) == 3, "la cadencia de lectura se fue de 1 Hz"


def test_apagada_deja_de_escribir_en_el_acto(banco, caplog):
    banco.armar(X, Y)
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.correr(1.0, (X, Y, ABIERTA))
        antes = len(_lineas(caplog))
        banco.motor.fijar_lectura(False)
        banco.correr(3.0, (X, Y, ABIERTA))
    assert antes == 1 and len(_lineas(caplog)) == antes


def test_la_linea_dice_cada_numero_que_el_detector_vio(banco, caplog):
    """Los umbrales se calibran leyendo el número, no adivinándolo.

    `ap` apertura, `mx` el dedo más abierto (los `DEDO_*`), `pz` el hueco de pinza
    (`PINZA_MAX`, `C_SPAN_MIN`), `gi` el giro del eje (`_giro_acum` sale de ahí),
    `v` velocidad (`VEL_QUIETUD`) y `q` quietud (`permanencia`, `T_QUIETUD_SUELTA`).
    """
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.t += DT
        banco.motor._procesar(banco.t, [_det(X, Y, 0.62, pinza=0.88,
                                             dedo_max=0.31, giro=12.0)])
    (linea,) = _lineas(caplog)
    assert "ap=0.62" in linea and "mx=0.31" in linea, linea
    assert "pz=0.88" in linea and "gi=12" in linea, linea
    assert " abierta " in linea, linea          # 0,88 < C_SPAN_MIN: no es una C
    assert " q=" in linea and " v=" in linea, linea


def test_sale_tambien_la_mano_pendiente_que_el_cable_no_publica(banco, caplog):
    """El motivo de «le enseño la mano y no pasa nada», visible por fin.

    Una mano nueva tarda `CONFIRMA_MANO_SEG` en contar; hasta entonces el evento
    `manos` la omite y el panel del navegador no puede mostrarla. En la lectura sale
    con `conf=0`: así se distingue «no la veo» de «la veo pero aún no vale».
    """
    banco.armar(X, Y)
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.t += DT
        # segunda mano en otro sitio: identidad nueva, todavía pendiente
        banco.motor._procesar(banco.t, [_det(X, Y, ABIERTA), _det(0.3, 0.5, ABIERTA)])
    (linea,) = _lineas(caplog)
    pendientes = [p for p in linea.split(" | ") if " conf=0" in p]
    assert len(pendientes) == 1, linea
    publicados = banco.de("manos")[-1][1]["manos"]
    assert len(publicados) == 1, "el cable publicó la mano pendiente"


def test_la_linea_dice_lo_que_la_maquina_decidio(banco, caplog):
    """Estado, grupo, regla de suelta vigente y la transformación que salió."""
    banco.armar(X, Y)
    banco.correr(0.3, (X, Y, ABIERTA))
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        # 2 s con el puño: el agarre se forma a los pocos cuadros (la forma y
        # `cerrada` son estados confirmados, no instantes) y sigue vigente.
        banco.correr(2.0, (X, Y, PUNO))
    linea = _lineas(caplog)[-1]
    assert "AGARRE" in linea, linea
    assert " GRUPO" in linea, linea                       # la mano sujeta
    assert "ext=0" in linea, linea                       # no lo reclamó la interfaz
    assert "transf n=1" in linea, linea
    assert "c=agarres:1" in linea, linea                 # los contadores que subieron


def test_el_histograma_de_lado_llega_al_c_de_la_linea(banco, caplog):
    """Los buckets del puntaje de lado salen solos en el `c=`: son el instrumento.

    Si no llegan a la línea, el histograma existe pero no se puede leer después de
    la sesión, que es justo el defecto que dejó el hallazgo 5 sin decidir.
    """
    banco.armar(X, Y)
    banco.correr(0.3, (X, Y, ABIERTA))
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.correr(1.2, (X, Y, ABIERTA))
    linea = _lineas(caplog)[-1]
    assert "lado_0.9:" in linea, linea            # _det() trae puntaje 0,95


def test_el_par_reclamado_desde_fuera_se_ve_como_par(banco, caplog):
    """`ext=1`, las dos manos marcadas y `espera_union` cuando falta la segunda."""
    banco.armar(X, Y)
    banco.correr(0.6, (X, Y, ABIERTA))
    mano = banco.de("manos")[-1][1]["manos"][0]["id"]
    banco.motor.fijar_agarre([mano])
    banco.t += DT
    banco.motor._procesar(banco.t, [_det(X, Y, ABIERTA)])
    banco.motor.fijar_lectura(True)
    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        banco.correr(1.0, (X, Y, ABIERTA))
    (linea,) = _lineas(caplog)
    assert "ext=1" in linea and " GRUPO" in linea, linea
    assert "suelta=quietud" in linea, linea
    assert "recorrido=0." in linea, linea


def test_lectura_no_cambia_ninguna_decision(banco, caplog):
    """La promesa del docstring, probada: mira y no toca.

    La misma secuencia, dos bancos, uno con lectura encendida: los eventos tienen
    que salir iguales hasta el último campo. Si algún día la lectura deja de ser
    inocua, esta prueba es la que lo cuenta.
    """
    def secuencia(lectura: bool) -> list[dict]:
        b = Banco()
        b.motor.fijar_lectura(lectura)
        b.armar(X, Y)
        b.correr(0.3, (X, Y, ABIERTA))
        b.correr(2.0, (X, Y, PUNO))
        b.correr(0.3, (X, Y, ABIERTA))
        return [ev for _, ev in b.eventos if ev["evento"] != "cuadro"]

    with caplog.at_level(logging.INFO, logger=g.LOGGER.name):
        sin = secuencia(False)
        con = secuencia(True)
    assert len(_lineas(caplog)) > 0, "la lectura no escribió: el test no prueba nada"
    assert con == sin


# --- el mensaje por el canal --------------------------------------------------
class MotorDoble:
    def __init__(self) -> None:
        self.on_evento = None
        self.lectura: list[bool] = []

    def fijar_sostiene(self, valor: bool) -> None:
        pass

    def fijar_video(self, valor: bool) -> None:
        pass

    def fijar_lectura(self, valor: bool) -> None:
        self.lectura.append(valor)


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def canal():
    ch = c.GestosCanal(port=_puerto_libre())
    ch.iniciar()
    yield ch
    ch.detener()


def test_el_mensaje_de_lectura_llama_a_fijar_lectura(canal):
    motor = MotorDoble()
    canal.conectar_motor(motor)

    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            await ws.recv()                                   # "hola"
            await ws.send(json.dumps({"tipo": "lectura", "valor": True}))
            await ws.send(json.dumps({"tipo": "lectura", "valor": False}))
            for _ in range(150):
                if len(motor.lectura) == 2:
                    break
                await asyncio.sleep(0.02)
        assert motor.lectura == [True, False]

    asyncio.run(prueba())


# --- los dos números que faltaban en el cable ---------------------------------
def test_el_evento_manos_lleva_dedo_y_vel(banco):
    """Sin `dedo` no se calibran `DEDO_*`; sin `vel`, `VEL_QUIETUD`.

    El panel del navegador pinta lo que llega por el cable: si aquí falta un campo,
    allá no existe, por mucho que el log lo nombre.
    """
    banco.armar(X, Y)
    banco.t += DT
    banco.motor._procesar(banco.t, [_det(X, Y, 0.62, dedo_max=0.31)])
    mano = banco.de("manos")[-1][1]["manos"][0]
    assert mano["dedo"] == pytest.approx(0.31), mano
    assert "vel" in mano, mano
