"""
Cliente del Núcleo hacia el Coordinador de Módulos (role=core).

Cuando el Hub corre como proceso independiente, el Núcleo no lo embebe:
se conecta por WebSocket, recibe core_request de los módulos y puede
mandar hub_command / hub_list.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger("core_client")


class CoreClient:
    """Proxy del Hub remoto para el proceso del Núcleo."""

    def __init__(
        self,
        url: str,
        token: str,
        on_core_request: Callable[[str, str], dict],
    ):
        self.url = url
        self.token_value = token  # compat con hub.token
        self.on_core_request = on_core_request
        self._loop = None
        self._thread = None
        self._stop = threading.Event()
        self._ws = None
        self._pending = {}  # id -> concurrent result holder
        self._pending_lock = threading.Lock()
        self._connected = threading.Event()

    # ------------------------------------------------------------------ API tipo ModuloHub

    @property
    def token(self):
        return self.token_value

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="core-client", daemon=True)
        self._thread.start()
        if not self._connected.wait(12):
            log.warning("CoreClient: no conectó al Coordinador a tiempo (seguirá reintentando)")

    def stop(self):
        self._stop.set()
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(lambda: None)
            except Exception:
                pass

    def list_modules(self):
        result = self._rpc("hub_list", {}, timeout=8)
        if not result:
            return []
        return result.get("modules") or []

    def send(self, target, action, params=None, timeout=15.0):
        req_id = uuid.uuid4().hex
        result = self._rpc(
            "hub_command",
            {
                "id": req_id,
                "target": target,
                "action": action,
                "params": params or {},
                "timeout": timeout,
            },
            timeout=timeout + 5,
            result_type="hub_command_result",
            match_id=req_id,
        )
        if result is None:
            return {"ok": False, "error": "sin respuesta del Coordinador"}
        return result

    def diagnostico(self):
        result = self._rpc("hub_diag", {}, timeout=8, result_type="hub_diag_result")
        if not result:
            return "CoreClient: no conectado al Coordinador"
        return result.get("text") or ""

    def find(self, target, module_type=None):
        mods = self.list_modules()
        if module_type:
            mods = [m for m in mods if m.get("module_type") == module_type]
        if isinstance(target, int) or str(target).strip().isdigit():
            n = int(target)
            return next((m for m in mods if m.get("number") == n), None)
        t = str(target).lower().strip()
        return next(
            (m for m in mods if m.get("id") == str(target)
             or (m.get("name") or "").lower() == t),
            None,
        )

    # ------------------------------------------------------------------ interno

    def _rpc(self, msg_type, payload, timeout=10, result_type=None, match_id=None):
        if not self._loop or not self._connected.is_set():
            return None
        req_id = match_id or payload.get("id") or uuid.uuid4().hex
        payload = {**payload, "type": msg_type, "id": req_id}
        expect = result_type or (msg_type + "_result")
        holder = {"event": threading.Event(), "data": None}

        with self._pending_lock:
            self._pending[req_id] = (expect, holder)

        async def _send():
            if self._ws is None:
                return
            await self._ws.send(json.dumps(payload, ensure_ascii=False))

        try:
            asyncio.run_coroutine_threadsafe(_send(), self._loop).result(5)
        except Exception as e:
            log.warning("CoreClient RPC send falló: %s", e)
            with self._pending_lock:
                self._pending.pop(req_id, None)
            return None

        if not holder["event"].wait(timeout):
            with self._pending_lock:
                self._pending.pop(req_id, None)
            return None
        return holder["data"]

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._session())
        except Exception:
            log.exception("CoreClient session error")
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    async def _session(self):
        import websockets
        from websockets.exceptions import ConnectionClosed

        backoff = 1
        while not self._stop.is_set():
            try:
                log.info("CoreClient conectando a %s …", self.url)
                async with websockets.connect(
                    self.url, ping_interval=20, ping_timeout=20,
                ) as ws:
                    self._ws = ws
                    await ws.send(json.dumps({
                        "type": "hello",
                        "token": self.token_value,
                        "role": "core",
                        "device": "Dark Núcleo",
                    }))
                    raw = await asyncio.wait_for(ws.recv(), 10)
                    welcome = json.loads(raw)
                    if welcome.get("type") != "welcome":
                        raise RuntimeError(f"handshake fallido: {welcome}")
                    self._connected.set()
                    backoff = 1
                    log.info("CoreClient enlazado al Coordinador")

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except ValueError:
                            continue
                        await self._on_message(ws, msg)
            except ConnectionClosed:
                log.warning("CoreClient: conexión cerrada")
            except Exception as e:
                log.warning("CoreClient: %s", e)
            finally:
                self._ws = None
                self._connected.clear()

            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

    async def _on_message(self, ws, msg):
        mtype = msg.get("type")

        if mtype == "core_request":
            req_id = msg.get("id") or uuid.uuid4().hex
            module_id = msg.get("module_id") or ""
            texto = msg.get("text") or ""
            # Ejecutar en hilo: puede bloquear con LLM
            def _work():
                try:
                    return self.on_core_request(module_id, texto) or {}
                except Exception as e:
                    return {"ok": False, "error": f"{type(e).__name__}: {e}"}

            resp = await asyncio.get_event_loop().run_in_executor(None, _work)
            await ws.send(json.dumps({
                "type": "core_response",
                "id": req_id,
                "ok": bool(resp.get("ok")),
                "text": resp.get("text") or "",
                "error": resp.get("error"),
            }, ensure_ascii=False))
            return

        # Resultados de RPCs iniciados por el Núcleo
        with self._pending_lock:
            for rid, (expect, holder) in list(self._pending.items()):
                if msg.get("id") == rid and (expect is None or mtype == expect):
                    holder["data"] = msg
                    holder["event"].set()
                    self._pending.pop(rid, None)
                    return


def load_coordinator_config(config_dir: Path) -> dict:
    """Lee config/coordinator.json. Default: mode=embedded."""
    path = Path(config_dir) / "coordinator.json"
    if not path.exists():
        return {"mode": "embedded", "host": "127.0.0.1", "port": 8766}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("mode", "embedded")
        data.setdefault("host", "127.0.0.1")
        data.setdefault("port", 8766)
        return data
    except Exception as e:
        log.warning("No pude leer coordinator.json: %s", e)
        return {"mode": "embedded", "host": "127.0.0.1", "port": 8766}
