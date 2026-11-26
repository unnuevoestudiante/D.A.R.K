"""
modulos/prueba_core_ack.py — mide el contrato core_request → core_ack → core_response.

Levanta un cliente WebSocket contra el Hub del Núcleo (puerto 8766) y responde
las tres preguntas que el log del 2026-10-17 no dejaba ver:

  - ¿cuánto tarda el acuse?
  - ¿cuánto tarda la respuesta real?
  - ¿dos pedidos simultáneos del mismo texto abren un solo turno (dedupe)?

Uso, con el Núcleo ya corriendo:

    python -m modulos.prueba_core_ack
    python -m modulos.prueba_core_ack "hola" "hola"        # prueba de dedupe
    python -m modulos.prueba_core_ack "¿qué hora es?"

Se registra como module_type "test" para no pisar el nombre del teléfono real.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time
import uuid

import websockets

from modulos.hive.servidor import CONFIG_DIR

PUERTO = 8766
ESPERA_MAX_SEGUNDOS = 120


async def main(textos):
    token = (CONFIG_DIR / "modulo_token.txt").read_text(encoding="utf-8").strip()
    async with websockets.connect(f"ws://127.0.0.1:{PUERTO}") as ws:
        await ws.send(json.dumps({
            "type": "hello",
            "token": token,
            "module_type": "test",
            "device": "prueba-latencia",
        }, ensure_ascii=False))
        bienvenida = json.loads(await ws.recv())
        if bienvenida.get("type") != "welcome":
            print(f"No hubo welcome: {bienvenida}")
            return
        print(f"Registrado como {bienvenida.get('name')} "
              f"(id {str(bienvenida.get('module_id'))[:8]})")

        enviados = {}
        for texto in textos:
            req_id = uuid.uuid4().hex
            await ws.send(json.dumps(
                {"type": "core_request", "id": req_id, "text": texto},
                ensure_ascii=False))
            enviados[req_id] = {"texto": texto, "t0": time.perf_counter(),
                                "ack": None, "fin": None}
            print(f"→ {req_id[:8]} {texto!r}")

        fin_buscado = time.perf_counter() + ESPERA_MAX_SEGUNDOS
        while any(v["fin"] is None for v in enviados.values()):
            restante = fin_buscado - time.perf_counter()
            if restante <= 0:
                break
            try:
                crudo = await asyncio.wait_for(ws.recv(), timeout=restante)
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                break
            msg = json.loads(crudo)
            if msg.get("type") not in ("core_ack", "core_response"):
                continue
            registro = enviados.get(msg.get("id"))
            if registro is None:
                print(f"? {msg.get('type')} de un id que no mandé: {msg}")
                continue
            ahora = time.perf_counter() - registro["t0"]
            if msg["type"] == "core_ack":
                registro["ack"] = ahora
                print(f"   acuse de {msg['id'][:8]} en {ahora * 1000:.0f} ms")
            else:
                registro["fin"] = ahora
                detalle = msg.get("text") or msg.get("error") or ""
                print(f"   respuesta de {msg['id'][:8]} en {ahora:.1f} s "
                      f"(ok={msg.get('ok')}): {detalle[:400]!r}")
                # Para comparar calidad entre modelos hace falta el texto
                # completo; lo que va a stdout se corta por legibilidad.
                ruta = os.environ.get("DARK_GUARDA_RESPUESTA")
                if ruta:
                    with io.open(ruta, "a", encoding="utf-8") as f:
                        f.write(f"{ahora:.1f}s ok={msg.get('ok')} :: {detalle}\n")

    print("\n=== resumen ===")
    for registro in enviados.values():
        ack = "sin acuse" if registro["ack"] is None else f"{registro['ack'] * 1000:.0f} ms"
        fin = ("sin respuesta" if registro["fin"] is None
               else f"{registro['fin']:.1f} s")
        print(f"  {registro['texto'][:42]!r:<46} acuse {ack:>10}   respuesta {fin}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["hola, quién eres"]))
