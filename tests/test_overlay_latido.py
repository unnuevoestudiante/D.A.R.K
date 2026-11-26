"""El puente responde al latido de la interfaz sin pasarlo al Núcleo (así la interfaz sabe si sigue vivo)."""
import asyncio
import json
import socket
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dark_python"))

from modulos.dark_overlay_bridge import OverlayBridge  # noqa: E402


def puerto_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestLatido(unittest.TestCase):
    def test_responde_pong_y_no_reenvia_el_ping_al_nucleo(self):
        import websockets
        recibidos = []
        puerto, http = puerto_libre(), puerto_libre()
        puente = OverlayBridge(host="127.0.0.1", port=puerto, http_port=http, on_message=lambda m, o: recibidos.append(m),
                               escritorio_vigilia_seg=0)
        puente.iniciar() if hasattr(puente, "iniciar") else None
        time.sleep(1.0)

        async def cliente():
            async with websockets.connect(f"ws://127.0.0.1:{puerto}") as ws:
                inicial = json.loads(await asyncio.wait_for(ws.recv(), 5))
                await ws.send(json.dumps({"action": "ping"}))
                respuesta = json.loads(await asyncio.wait_for(ws.recv(), 5))
                await ws.send(json.dumps({"action": "config", "operacion": "abrir"}))
                await asyncio.sleep(0.3)
                return inicial, respuesta
        try:
            inicial, respuesta = asyncio.run(cliente())
        finally:
            for nombre in ("detener", "cerrar", "stop"):
                if hasattr(puente, nombre):
                    getattr(puente, nombre)()
                    break
        self.assertIn("state", inicial)
        self.assertEqual(respuesta, {"pong": True})
        self.assertFalse(any('"ping"' in m for m in recibidos))   # el latido no molesta al Núcleo
        self.assertTrue(any('"config"' in m for m in recibidos))  # lo demás sí le llega


if __name__ == "__main__":
    unittest.main()
