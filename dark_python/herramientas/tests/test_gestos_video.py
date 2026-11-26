"""Pruebas del vídeo de calibración: el cuadro que ve el motor, reenviado a la interfaz.

Tres capas, cada una con su falso mínimo:
  * ``_codificar_cuadro`` / ``_emitir_cuadro``: funciones puras del hilo, probadas solas.
  * el worker real, con cámara y detector falsos, para ver que ``fijar_video`` manda y deja de mandar.
  * el canal, para ver que el mensaje ``video`` llega al motor y que ``cuadro`` se funde.
"""
from __future__ import annotations

import asyncio
import base64
import importlib
import importlib.util
import json
import socket
import sys
import types
from pathlib import Path

import numpy as np
import pytest
import websockets

try:
    from herramientas import dark_gestos_canal as c
except ImportError:  # pruebas sueltas junto al módulo
    import dark_gestos_canal as c

_CANDIDATOS = ("herramientas.gestos",)


def _cargar_gestos():
    for nombre in _CANDIDATOS:
        try:
            return importlib.import_module(nombre)
        except ImportError:
            continue

    def falso(nombre: str, **atributos) -> types.ModuleType:
        modulo = types.ModuleType(nombre)
        modulo.__dict__.update(atributos)
        sys.modules[nombre] = modulo
        return modulo

    falso("cv2")
    falso("psutil")
    vision_mp = falso("mediapipe.tasks.python.vision")
    python_mp = falso("mediapipe.tasks.python", vision=vision_mp)
    tasks_mp = falso("mediapipe.tasks", python=python_mp)
    falso("mediapipe", tasks=tasks_mp)
    paquete = sys.modules.get("herramientas") or falso("herramientas")
    paquete.__path__ = getattr(paquete, "__path__", [])
    falso("herramientas.vision", FPS_CONTINUO=30.0, VisionService=object, _to_mp=lambda x: x)

    ruta = next(
        r for r in (Path(__file__).resolve().parent.parent / "gestos.py", Path(__file__).with_name("gestos.py"))
        if r.exists()
    )
    spec = importlib.util.spec_from_file_location("gestos_bajo_prueba_video", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["gestos_bajo_prueba_video"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


g = _cargar_gestos()
hace_falta_cv2 = hasattr(g.cv2, "imencode")
Cuadro = getattr(g, "Cuadro", None)


def cuadro_fake(ts: float, alto: int = 480, ancho: int = 640):
    imagen = np.zeros((alto, ancho, 3), dtype=np.uint8)
    imagen[100:300, 100:300] = (200, 30, 30)
    if Cuadro is not None:
        try:
            return Cuadro(ts=ts, imagen=imagen)
        except TypeError:
            pass
    return types.SimpleNamespace(ts=ts, imagen=imagen)


class CamaraFalsa:
    """Suicida: cuando se acaba la película se mata al worker ella misma."""

    def __init__(self, motor, n_cuadros: int, paso: float = 0.05) -> None:
        self._motor, self._n, self._paso = motor, n_cuadros, paso
        self._i = 0
        self.fps = None

    def suscribir(self, nombre: str) -> "CamaraFalsa":
        return self

    def iniciar(self) -> None:
        pass

    def fijar_fps(self, fps: float) -> None:
        self.fps = fps

    def siguiente(self, timeout: float):
        if self._i >= self._n:
            self._motor._stop.set()
            return None
        self._i += 1
        return cuadro_fake(100.0 + self._i * self._paso)

    def cerrar(self) -> None:
        pass


class DetectorFalso:
    """Sin manos: aquí solo interesa el reenvío del cuadro, no la detección."""

    def detectar(self, espejo, ts_ms):
        return [], []

    def cerrar(self) -> None:
        pass


def _correr_worker(monkeypatch, n_cuadros: int, video: bool) -> list[dict]:
    """Ejecuta el hilo de verdad con cámara y detector falsos y devuelve lo emitido."""
    monkeypatch.setattr(g, "_DetectorManos", DetectorFalso)
    eventos: list[dict] = []
    motor = g.GestureEngine(servicio=None, on_evento=eventos.append)
    motor._servicio = CamaraFalsa(motor, n_cuadros)
    motor.fijar_video(video)
    motor.iniciar()
    motor._thread.join(10.0)
    assert motor.error is None, motor.error
    assert not motor._thread.is_alive()
    return eventos


@pytest.mark.skipif(not hace_falta_cv2, reason="hace falta un cv2 real para codificar")
def test_el_cuadro_es_un_jpeg_de_ancho_reducido():
    motor = g.GestureEngine(servicio=None)
    codificado, ancho, alto = motor._codificar_cuadro(cuadro_fake(0.0).imagen)
    assert codificado.startswith("data:image/jpeg;base64,")
    assert ancho == g.VIDEO_ANCHO
    assert alto == pytest.approx(480 * g.VIDEO_ANCHO / 640, abs=2)
    crudo = base64.b64decode(codificado.split(",", 1)[1])
    decodificado = g.cv2.imdecode(np.frombuffer(crudo, np.uint8), g.cv2.IMREAD_COLOR)
    assert decodificado is not None and decodificado.shape[:2] == (alto, ancho)


@pytest.mark.skipif(not hace_falta_cv2, reason="hace falta un cv2 real para codificar")
def test_la_emitida_respeta_el_tope_de_cuadros_por_segundo():
    eventos: list[dict] = []
    motor = g.GestureEngine(servicio=None, on_evento=eventos.append)
    imagen = cuadro_fake(0.0).imagen
    t = 0.0
    for _ in range(60):                 # 2 s a 30 fps
        t += 1 / 30
        motor._emitir_cuadro(imagen, t)
    enviados = [e for e in eventos if e["evento"] == "cuadro"]
    assert 20 <= len(enviados) <= 26     # ~12 fps durante ~2 s
    assert all(e["imagen"].startswith("data:image/jpeg;base64,") for e in enviados)
    assert motor.contadores["cuadros_enviados"] == len(enviados)


@pytest.mark.skipif(not hace_falta_cv2, reason="hace falta un cv2 real para codificar")
def test_el_worker_manda_cuadros_mientras_el_video_esta_encendido(monkeypatch):
    eventos = _correr_worker(monkeypatch, n_cuadros=40, video=True)   # 40 x 0,05 s = 2 s
    assert [e for e in eventos if e["evento"] == "cuadro"], "el worker no reenvió ningún cuadro"


@pytest.mark.skipif(not hace_falta_cv2, reason="hace falta un cv2 real para codificar")
def test_apagado_el_video_no_manda_nada(monkeypatch):
    eventos = _correr_worker(monkeypatch, n_cuadros=40, video=False)
    assert not [e for e in eventos if e["evento"] == "cuadro"]


# --- el canal: el mensaje entra y el cuadro sale -----------------------------
class MotorDoble:
    def __init__(self) -> None:
        self.on_evento = None
        self.video: list[bool] = []

    def fijar_sostiene(self, valor: bool) -> None:
        pass

    def fijar_video(self, valor: bool) -> None:
        self.video.append(valor)


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


def test_el_mensaje_video_llama_a_fijar_video(canal):
    motor = MotorDoble()
    canal.conectar_motor(motor)

    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            await ws.recv()                                  # "hola"
            await ws.send(json.dumps({"tipo": "video", "valor": True}))
            await ws.send(json.dumps({"tipo": "video", "valor": False}))
            for _ in range(150):
                if len(motor.video) == 2:
                    break
                await asyncio.sleep(0.02)
        assert motor.video == [True, False]

    asyncio.run(prueba())


def test_cuadro_se_funde_como_evento_continuo(canal):
    """Un cliente que no alcanza a leer pierde cuadros; no se le acumulan megas de base64."""
    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            await ws.recv()                                  # "hola"
            for i in range(20):
                canal.emitir({"evento": "cuadro", "imagen": f"x{i}"})
            recibidos = []
            while True:
                try:
                    recibidos.append(json.loads(await asyncio.wait_for(ws.recv(), 0.5)))
                except asyncio.TimeoutError:
                    break
            return [m for m in recibidos if m.get("evento") == "cuadro"]

    cuadros = asyncio.run(prueba())
    # El bomba va en su propio hilo, así que escapa alguno; lo que se prueba es
    # que NO llegan los 20 y que el que sale al final es el último cuadro.
    assert len(cuadros) < 20
    assert cuadros[-1]["imagen"] == "x19"
