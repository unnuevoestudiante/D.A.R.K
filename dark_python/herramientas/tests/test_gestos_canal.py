"""Pruebas del canal de gestos con un cliente WebSocket real en loopback."""
from __future__ import annotations

import asyncio
import json
import socket
import time

import pytest
import websockets

try:
    from herramientas import dark_gestos_canal as c
except ImportError:  # pruebas sueltas junto al módulo
    import dark_gestos_canal as c


def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def canal():
    recibidos: list[dict] = []
    ch = c.GestosCanal(port=puerto_libre(), on_mensaje=recibidos.append)
    ch.recibidos = recibidos
    ch.iniciar()
    yield ch
    ch.detener()


async def _leer(ws, n: int, timeout: float = 3.0) -> list[dict]:
    salida = []
    for _ in range(n):
        salida.append(json.loads(await asyncio.wait_for(ws.recv(), timeout)))
    return salida


async def _esperar_clientes(ch, n: int) -> None:
    for _ in range(100):
        if ch.clientes == n:
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"clientes={ch.clientes}, esperaba {n}")


def test_rechaza_hosts_no_locales():
    with pytest.raises(ValueError):
        c.GestosCanal(host="0.0.0.0")
    c.GestosCanal(host="0.0.0.0", permitir_red=True)


def test_hola_orden_y_seq(canal):
    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            hola = (await _leer(ws, 1))[0]
            assert hola["evento"] == "hola" and hola["canal"] == "gestos" and hola["estado"] is None
            await _esperar_clientes(canal, 1)
            canal.emitir({"evento": "gestos_on", "motivo": "palma", "aspecto": 1.3333})
            canal.emitir({"evento": "agarre_inicio", "manos": [1], "n": 1, "ancla": [0.4, 0.5]})
            canal.emitir({"evento": "agarre_fin"})
            msgs = await _leer(ws, 3)
            assert [m["evento"] for m in msgs] == ["gestos_on", "agarre_inicio", "agarre_fin"]
            assert [m["seq"] for m in msgs] == sorted(m["seq"] for m in msgs)
            assert msgs[1]["ancla"] == [0.4, 0.5]
    asyncio.run(prueba())


def test_cliente_nuevo_recibe_el_ultimo_estado(canal):
    canal.emitir({"evento": "gestos_on", "motivo": "palma", "aspecto": 1.3333})   # sin clientes: solo se recuerda
    assert len(canal._cola) == 0

    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            hola = (await _leer(ws, 1))[0]
            assert hola["estado"]["evento"] == "gestos_on"
    asyncio.run(prueba())


def test_los_continuos_se_funden_y_el_orden_se_respeta(canal):
    canal._n_clientes = 1          # simula un cliente conectado, sin arrancar el envío
    canal._loop = None
    for i in range(1000):
        canal.emitir({"evento": "manos", "manos": [], "i": i})
        canal.emitir({"evento": "transformacion", "n": 1, "dx": i, "dy": 0, "escala": 1, "giro": 0})
    assert [m["evento"] for m in canal._cola] == ["manos", "transformacion"]
    assert canal._cola[0]["i"] == 999 and canal._cola[1]["dx"] == 999
    canal.emitir({"evento": "agarre_cambio", "manos": [1, 2], "n": 2, "ancla": [0.5, 0.5]})
    canal.emitir({"evento": "manos", "manos": [], "i": 1000})
    canal.emitir({"evento": "transformacion", "n": 2, "dx": 5, "dy": 0, "escala": 1, "giro": 0})
    eventos = [m["evento"] for m in canal._cola]
    # lo posterior al cambio de agarre NUNCA va delante de él
    assert eventos == ["manos", "transformacion", "agarre_cambio", "manos", "transformacion"]
    assert canal._cola[-1]["dx"] == 5 and canal.descartados >= 1998
    canal._n_clientes = 0


def test_sin_clientes_no_se_acumula_nada(canal):
    for i in range(500):
        canal.emitir({"evento": "manos", "manos": []})
        canal.emitir({"evento": "agarre_inicio", "manos": [1], "n": 1, "ancla": [0, 0]})
    assert len(canal._cola) == 0


def test_mensaje_sostiene_llega_al_motor(canal):
    class Motor:
        on_evento = None
        valores: list = []

        def fijar_sostiene(self, v):
            self.valores.append(v)

    m = Motor()
    canal.conectar_motor(m)
    assert m.on_evento == canal.emitir

    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            await _leer(ws, 1)
            await ws.send(json.dumps({"tipo": "sostiene", "valor": True}))
            await ws.send("no es json")
            await ws.send(json.dumps([1, 2]))
            await ws.send(json.dumps({"tipo": "sostiene", "valor": False}))
            for _ in range(100):
                if len(m.valores) == 2:
                    break
                await asyncio.sleep(0.02)
    asyncio.run(prueba())
    assert m.valores == [True, False]


def test_mensaje_coger_llega_al_motor_y_se_filtra(canal):
    """`coger` reclama el agarre por permanencia; lo que no es id de mano no pasa."""

    class Motor:
        on_evento = None
        agarres: list = []

        def fijar_agarre(self, ids):
            self.agarres.append(ids)

    m = Motor()
    canal.conectar_motor(m)

    async def prueba():
        async with websockets.connect(f"ws://127.0.0.1:{canal.port}") as ws:
            await _leer(ws, 1)
            await ws.send(json.dumps({"tipo": "coger", "manos": [3, 4]}))
            await ws.send(json.dumps({"tipo": "coger", "manos": [1, "dos", None, 2.0, 5]}))
            await ws.send(json.dumps({"tipo": "coger", "manos": "3"}))
            for _ in range(100):
                if len(m.agarres) == 2:
                    break
                await asyncio.sleep(0.02)
    asyncio.run(prueba())
    assert m.agarres[0] == [3, 4]
    # el texto y el None se tiran, el 2.0 pasa por id y el quinto se queda fuera:
    # dos manos es el máximo del motor, y la lista que no es lista no llega.
    assert m.agarres[1] == [1, 2]


def test_un_cliente_lento_no_frena_a_los_demas(canal):
    class Colgado:

        async def send(self, _):
            await asyncio.sleep(60)

        async def close(self):
            pass

    class Bueno:
        def __init__(self):
            self.recibido = []

        async def send(self, datos):
            self.recibido.append(datos)

        async def close(self):
            pass

    async def prueba():
        colgado, bueno = Colgado(), Bueno()
        canal._clientes = {colgado, bueno}
        t0 = time.monotonic()
        await canal._difundir("x")
        assert time.monotonic() - t0 < c.TIMEOUT_ENVIO + 0.5
        assert bueno.recibido == ["x"]
        assert canal._clientes == {bueno}          # el colgado se expulsó
    asyncio.run(prueba())
    canal._clientes = set()


def test_puerto_ocupado_lanza_error_claro():
    with socket.socket() as ocupado:
        ocupado.bind(("127.0.0.1", 0))
        ocupado.listen()
        ch = c.GestosCanal(port=ocupado.getsockname()[1])
        with pytest.raises(RuntimeError):
            ch.iniciar()


def test_detener_libera_el_puerto():
    ch = c.GestosCanal(port=0)
    ch.iniciar()
    puerto_asignado = ch._servidor.sockets[0].getsockname()[1]
    assert puerto_asignado > 0
    ch.detener()
    with socket.socket() as cliente:
        cliente.settimeout(0.2)
        with pytest.raises(OSError):
            cliente.connect(("127.0.0.1", puerto_asignado))


def test_detener_rapido_cierra_el_puerto_en_500_ciclos():
    for ciclo in range(500):
        ch = c.GestosCanal(port=0)
        ch.iniciar()
        puerto_asignado = ch._servidor.sockets[0].getsockname()[1]
        hilo = ch._thread
        inicio = time.monotonic()
        try:
            ch.detener()
            transcurrido = time.monotonic() - inicio

            assert transcurrido <= 1, (
                f"ciclo {ciclo}: detener tardó {transcurrido:.3f}s")
            assert hilo is not None and not hilo.is_alive(), (
                f"ciclo {ciclo}: el hilo de gestos sigue vivo")
            with socket.socket() as cliente:
                cliente.settimeout(0.2)
                with pytest.raises(OSError):
                    cliente.connect(("127.0.0.1", puerto_asignado))
        finally:
            if hilo is not None and hilo.is_alive():
                ch.detener(timeout=1)
