"""
Servidor de Módulos: conecta Dark Núcleo con los módulos del entorno.

Soporta múltiples tipos de módulo (phone, tv, watch, headphone…).
Cada módulo declara su tipo y capacidades en el handshake (hello).

- Primera conexión: ID permanente + nombre según tipo ("Teléfono 1", "TV 1"…).
  El número es por tipo y nunca se reutiliza. Todo se guarda en modulos.json.
- Núcleo manda órdenes con ModuloHub.send(...).
- El módulo puede pedirle cosas al Núcleo con {"type": "core_request", ...}.
  El Hub responde enseguida {"type": "core_ack", "id": ...} (la petición quedó
  en cola) y manda el resultado real por {"type": "core_response", "id": ...}
  cuando el turno termina. El módulo debe esperar la response sin reintentar:
  el acuse ya le dice que no pierda el pedido.
- Diagnóstico: con verbose=True imprime cada evento; hub.diagnostico() y hub.ping_all()
  dan el estado y prueban la conexión de ida y vuelta.

Requiere:  pip install websockets
Prueba:    python modulo_server.py
"""
import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import socket
import threading
import time
import unicodedata
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import websockets
from websockets.exceptions import ConnectionClosed

log = logging.getLogger("modulos")

# El registro y el token viven siempre junto a este archivo, se lance desde donde se lance.
# Ajustar para que el token viva en la carpeta config/ del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

# Cuanto deja el Hub vivir una core_request antes de tirar la toalla. El
# nucleo ya acota el turno por su cuenta (dark_presupuesto.
# RESPUESTA_MODULO_SEGUNDOS = 95s); este es solo el salvavidas por si el
# callback se cuelga y no devuelve nunca, asi que tiene que ser mayor que 95
# y menor que los 120s que espera el telefono. Si no cuadra, el Hub declara
# timeout mientras el nucleo todavia estaba trabajando.
CORE_TIMEOUT_SEGUNDOS = 100.0

# ---------------------------------------------------------------------------
# Tipos de módulo y capacidades por defecto
# ---------------------------------------------------------------------------
TYPE_LABELS = {
    "phone": "Teléfono",
    "tv": "TV",
    "watch": "Reloj",
    "headphone": "Audífonos",
}

DEFAULT_CAPABILITIES = {
    "phone": [
        "say", "ask", "torch", "call", "open_app",
        "status", "ping", "disconnect", "reconnect",
    ],
    "tv": [
        "power", "volume", "brightness", "channel",
        "open_app", "search", "play", "media_control",
        "status", "ping",
    ],
    "watch": [
        "say", "ask", "status", "ping", "notify",
    ],
    "headphone": [
        "play", "media_control", "volume", "status", "ping",
    ],
}

KNOWN_TYPES = set(TYPE_LABELS.keys())


def _label_for(module_type):
    return TYPE_LABELS.get(module_type, "Módulo")


def _default_caps(module_type):
    return list(DEFAULT_CAPABILITIES.get(module_type, ["ping", "status"]))


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(text):
    t = unicodedata.normalize("NFD", str(text).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip()


def _valid_id(value):
    return bool(re.fullmatch(r"[0-9a-f]{32}", value or ""))


def local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class Registry:
    """Módulos conocidos. Se guarda en disco tras cada cambio.

    Formato de modulos.json (v2):
    {
      "next_numbers": {"phone": 2, "tv": 1, ...},
      "modules": {
        "<id>": {
          "id": "...", "number": 1, "name": "Teléfono 1",
          "module_type": "phone", "capabilities": [...],
          "device_key": "...", "device": "...",
          "first_seen": "...", "last_seen": "..."
        }
      }
    }
    """

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data = {"next_numbers": {}, "modules": {}}
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._data = self._migrate(raw)
            except Exception as e:
                backup = self.path.with_suffix(".corrupto.json")
                log.error("No pude leer %s (%s). Lo guardo como %s y empiezo vacío.", self.path, e, backup)
                os.replace(self.path, backup)

    def _migrate(self, raw):
        """Migración desde formato v1 (solo next_number + nombre 'Módulo N')."""
        if "next_numbers" in raw:
            return raw
        # v1 → v2
        next_numbers = {}
        modules = {}
        old_next = int(raw.get("next_number") or 1)
        for mid, m in (raw.get("modules") or {}).items():
            mtype = m.get("module_type") or "phone"
            if "module_type" not in m:
                m["module_type"] = mtype
            if "capabilities" not in m:
                m["capabilities"] = _default_caps(mtype)
            # Reconstruir nombre si aún es el genérico
            num = m.get("number") or 1
            label = _label_for(mtype)
            if not m.get("name") or str(m.get("name", "")).startswith("Módulo "):
                m["name"] = f"{label} {num}"
            modules[mid] = m
            next_numbers[mtype] = max(next_numbers.get(mtype, 1), num + 1)
        # Si no había módulos, preservar el contador global como phone
        if not next_numbers and old_next > 1:
            next_numbers["phone"] = old_next
        return {"next_numbers": next_numbers, "modules": modules}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    def _next_number(self, module_type):
        nn = self._data.setdefault("next_numbers", {})
        n = int(nn.get(module_type) or 1)
        nn[module_type] = n + 1
        return n

    def resolve(self, module_id, device_key, device, module_type=None, capabilities=None):
        """Devuelve (registro, es_nuevo).

        Busca por id, luego por huella del dispositivo; si no, registra uno nuevo.
        module_type y capabilities se actualizan en cada hello si el módulo los envía.
        """
        with self._lock:
            mods = self._data["modules"]
            rec = mods.get(module_id) if module_id else None
            if rec is None and device_key:
                rec = next((m for m in mods.values() if m.get("device_key") == device_key), None)
            is_new = rec is None

            # Normalizar tipo
            mtype = (module_type or "").strip().lower() if module_type else None
            if mtype and mtype not in KNOWN_TYPES:
                log.warning("module_type desconocido %r; se acepta igual", mtype)
            if not mtype:
                mtype = (rec or {}).get("module_type") or "phone"

            if is_new:
                number = self._next_number(mtype)
                new_id = module_id if _valid_id(module_id) else uuid.uuid4().hex
                caps = list(capabilities) if capabilities else _default_caps(mtype)
                rec = {
                    "id": new_id,
                    "number": number,
                    "name": f"{_label_for(mtype)} {number}",
                    "module_type": mtype,
                    "capabilities": caps,
                    "first_seen": _now(),
                }
                mods[new_id] = rec
            else:
                # Actualizar tipo/nombre/capabilities si el módulo los declara
                if module_type and rec.get("module_type") != mtype:
                    # Cambio de tipo: reasignar número dentro del nuevo tipo
                    old_type = rec.get("module_type") or "phone"
                    number = self._next_number(mtype)
                    rec["module_type"] = mtype
                    rec["number"] = number
                    rec["name"] = f"{_label_for(mtype)} {number}"
                    log.info("Módulo %s cambió de tipo %s → %s (ahora %s)",
                             rec["id"][:8], old_type, mtype, rec["name"])
                if capabilities is not None:
                    rec["capabilities"] = list(capabilities)
                elif "capabilities" not in rec:
                    rec["capabilities"] = _default_caps(rec.get("module_type") or "phone")
                if "module_type" not in rec:
                    rec["module_type"] = mtype
                # Asegurar nombre coherente con tipo
                label = _label_for(rec.get("module_type") or "phone")
                if not rec.get("name") or str(rec.get("name", "")).startswith("Módulo "):
                    rec["name"] = f"{label} {rec.get('number', 1)}"

            rec["device_key"] = device_key or rec.get("device_key")
            rec["device"] = device or rec.get("device")
            rec["last_seen"] = _now()
            self._save()
            return dict(rec), is_new

    def touch(self, module_id):
        with self._lock:
            rec = self._data["modules"].get(module_id)
            if rec:
                rec["last_seen"] = _now()
                self._save()

    def all(self):
        with self._lock:
            # Ordenar por tipo y luego por número
            return sorted(
                (dict(m) for m in self._data["modules"].values()),
                key=lambda m: (m.get("module_type") or "phone", m.get("number") or 0),
            )


class _Conn:
    def __init__(self, module_id, ws):
        self.module_id = module_id
        self.ws = ws
        self.pending = set()


class ModuloHub:
    def __init__(self, host="0.0.0.0", port=8766, registry_path=None,
                 token_path=None, on_event=None, on_core_request=None, verbose=True):
        self.host = host
        self.port = port
        self.verbose = verbose  # imprime cada evento en la consola
        self.registry = Registry(registry_path or CONFIG_DIR / "modulos.json")
        self.token = self._load_token(Path(token_path) if token_path else CONFIG_DIR / "modulo_token.txt")
        self.on_event = on_event  # función(kind, registro): "connected" | "disconnected"
        # Callback que Dark conecta para que el módulo pida cosas al Núcleo:
        # función(module_id, texto) -> {"ok": bool, "text": str, "error": str}
        self.on_core_request = on_core_request
        self._conns = {}
        self._pending = {}
        self._events = deque(maxlen=50)
        self._loop = None
        self._thread = None
        self._stop = None
        self._error = None
        self._ready = threading.Event()
        # Núcleo remoto (role=core): cuando el Hub corre como Coordinador independiente
        self._core_ws = None
        self._core_pending = {}  # id -> Future para respuestas del core remoto
        self._core_lock = threading.Lock()

    # ------------------------------------------------------------ diagnóstico

    def _say(self, msg):
        """Guarda el evento (para diagnostico()) y, si verbose, lo imprime."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self._events.append((stamp, msg))
        log.info(msg)
        if self.verbose:
            try:
                print(f"[Módulos {stamp}] {msg}", flush=True)
            except Exception:
                pass  # una consola con otra codificación no debe tumbar el servidor

    def diagnostico(self):
        """Resumen legible del estado del servidor y de los módulos."""
        alive = bool(self._thread and self._thread.is_alive() and self._ready.is_set() and not self._error)
        mods = self.list_modules()
        online = [m for m in mods if m["online"]]
        core = "conectado" if self._core_ws is not None else "ausente"
        modo = "embebido" if self.on_core_request is not None else "coordinador"
        lines = [
            f"Servidor: {'ACTIVO' if alive else 'DETENIDO'} en ws://{local_ip()}:{self.port}",
            f"Modo: {modo}  |  Núcleo (core): {core}",
            f"Módulos registrados: {len(mods)}  (en línea: {len(online)})",
        ]
        for m in mods:
            estado = "EN LÍNEA" if m["online"] else "desconectado"
            tipo = m.get("module_type") or "?"
            caps = ",".join(m.get("capabilities") or []) or "-"
            lines.append(
                f"  {m['name']}  [{tipo}]  id={m['id'][:8]}…  {estado}  {m.get('device', '?')}"
                f"  último contacto: {m.get('last_seen', '?')}"
            )
            lines.append(f"      capabilities: {caps}")
        lines.append("Últimos eventos:")
        for stamp, msg in list(self._events)[-10:]:
            lines.append(f"  [{stamp}] {msg}")
        return "\n".join(lines)

    def ping_all(self):
        """Prueba de ida y vuelta con cada módulo en línea. Devuelve la lista de resultados."""
        return [self.send(m["id"], "ping", timeout=5) for m in self.list_modules() if m["online"]]

    # ------------------------------------------------------------ arranque

    @staticmethod
    def _load_token(path):
        if path.exists():
            token = path.read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_urlsafe(24)
        path.write_text(token, encoding="utf-8")
        return token

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._error = None
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="modulo-hub", daemon=True)
        self._thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("El servidor de módulos no arrancó a tiempo")
        if self._error:
            raise RuntimeError(f"No pude abrir el puerto {self.port}: {self._error}")
        self._say(f"Servidor activo en ws://{local_ip()}:{self.port}")

    def stop(self):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        except Exception:
            log.exception("El servidor de módulos se detuvo por un error")
        finally:
            self._ready.set()

    async def _serve(self):
        self._stop = asyncio.Event()
        try:
            async with websockets.serve(self._handler, self.host, self.port):
                self._ready.set()
                await self._stop.wait()
        except OSError as e:
            self._error = e
            self._ready.set()

    # ------------------------------------------------------------ conexiones

    def _emit(self, kind, record):
        if self.on_event:
            try:
                self.on_event(kind, record)
            except Exception:
                log.exception("Error en on_event")

    async def _handler(self, ws):
        peer = getattr(ws, "remote_address", None)
        ip = peer[0] if peer else "?"
        self._say(f"Conexión entrante desde {ip}")

        # 1) El primer mensaje debe ser un "hello" válido, en menos de 10 s.
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
        except Exception:
            self._say(f"{ip}: no envió una identificación válida en 10 s; cierro la conexión")
            await ws.close(4001, "hello requerido")
            return

        supplied = str(hello.get("token", "")).encode("utf-8")
        if hello.get("type") != "hello" or not hmac.compare_digest(supplied, self.token.encode("utf-8")):
            self._say(f"{ip}: RECHAZADO - el token no coincide con el de modulo_token.txt")
            try:
                await ws.send(json.dumps({"type": "error", "reason": "token inválido"}))
            except ConnectionClosed:
                pass
            await ws.close(4003, "token inválido")
            return

        # 1b) Núcleo remoto (Coordinador independiente)
        role = (hello.get("role") or "module").strip().lower()
        if role == "core":
            await self._handler_core(ws, ip, hello)
            return

        # 2) Identidad: id permanente + nombre según tipo ("Teléfono 1", "TV 1"…).
        caps = hello.get("capabilities")
        if caps is not None and not isinstance(caps, list):
            caps = None
        record, is_new = self.registry.resolve(
            hello.get("module_id"),
            hello.get("device_key"),
            hello.get("device"),
            module_type=hello.get("module_type"),
            capabilities=caps,
        )
        conn = _Conn(record["id"], ws)

        old = self._conns.get(record["id"])
        if old is not None:
            self._say(f"{record['name']}: reemplaza su conexión anterior")
            try:
                await old.ws.close(4000, "reemplazada")
            except Exception:
                pass
        self._conns[record["id"]] = conn

        try:
            await ws.send(json.dumps({
                "type": "welcome",
                "module_id": record["id"],
                "name": record["name"],
                "number": record["number"],
                "module_type": record.get("module_type", "phone"),
                "capabilities": record.get("capabilities") or [],
                "new": is_new,
                "role": "module",
            }, ensure_ascii=False))
            tipo = record.get("module_type", "?")
            self._say(
                f"{record['name']} [{tipo}] CONECTADO desde {ip} ({record.get('device', '?')}) - "
                f"{'REGISTRADO AHORA' if is_new else 'ya conocido'} - id {record['id']}"
            )
            self._emit("connected", record)

            # 3) Resultados de las órdenes y peticiones del módulo al Núcleo.
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue

                mtype = msg.get("type")

                if mtype == "result":
                    fut = self._pending.get(msg.get("id"))
                    if fut and not fut.done():
                        fut.set_result({
                            "ok": bool(msg.get("ok")),
                            "text": msg.get("text"),
                            "error": msg.get("error"),
                        })

                elif mtype == "core_request":
                    # El módulo pide al Núcleo que haga algo (chat, tarea,
                    # abrir/cerrar apps del PC, etc.). Lo atendemos en
                    # paralelo para no bloquear el bucle de mensajes.
                    asyncio.create_task(self._handle_core_request(
                        conn,
                        msg.get("id") or uuid.uuid4().hex,
                        record,
                        msg.get("text", ""),
                    ))
        except ConnectionClosed:
            pass
        finally:
            if self._conns.get(record["id"]) is conn:
                del self._conns[record["id"]]
            for cmd_id in list(conn.pending):
                fut = self._pending.get(cmd_id)
                if fut and not fut.done():
                    fut.set_result({"ok": False, "error": "desconectado"})
            self.registry.touch(record["id"])
            self._say(f"{record['name']} desconectado")
            self._emit("disconnected", record)

    async def _handler_core(self, ws, ip, hello):
        """Sesión del Núcleo cuando el Hub es Coordinador independiente."""
        old = self._core_ws
        if old is not None:
            self._say("Núcleo: reemplaza su conexión anterior")
            try:
                await old.close(4000, "reemplazada")
            except Exception:
                pass
        self._core_ws = ws
        try:
            await ws.send(json.dumps({
                "type": "welcome",
                "role": "core",
                "server": "modulo-coordinator",
                "modules": len(self.registry.all()),
            }, ensure_ascii=False))
            self._say(f"NÚCLEO (core) CONECTADO desde {ip}")
            # Los módulos (p. ej. teléfono) pueden vaciar colas pendientes
            await self._broadcast_hub_event("core_online")

            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                mtype = msg.get("type")

                # Respuesta a un core_request reenviado
                if mtype == "core_response":
                    fut = self._core_pending.get(msg.get("id"))
                    if fut and not fut.done():
                        fut.set_result({
                            "ok": bool(msg.get("ok")),
                            "text": msg.get("text"),
                            "error": msg.get("error"),
                        })

                # El Núcleo manda órdenes a módulos a través del Coordinador
                elif mtype == "hub_command":
                    asyncio.create_task(self._hub_command_from_core(ws, msg))

                elif mtype == "hub_list":
                    mods = self.list_modules()
                    await ws.send(json.dumps({
                        "type": "hub_list_result",
                        "id": msg.get("id"),
                        "modules": mods,
                    }, ensure_ascii=False))

                elif mtype == "hub_diag":
                    await ws.send(json.dumps({
                        "type": "hub_diag_result",
                        "id": msg.get("id"),
                        "text": self.diagnostico(),
                    }, ensure_ascii=False))
        except ConnectionClosed:
            pass
        finally:
            if self._core_ws is ws:
                self._core_ws = None
            for fut in list(self._core_pending.values()):
                if not fut.done():
                    fut.set_result({"ok": False, "error": "Núcleo desconectado"})
            self._core_pending.clear()
            self._say("NÚCLEO (core) desconectado")
            # Fire-and-forget: el loop puede estar cerrando el core, pero
            # los módulos siguen vivos y deben saber que el core se fue.
            try:
                await self._broadcast_hub_event("core_offline")
            except Exception:
                pass

    async def _broadcast_hub_event(self, event: str, extra: dict | None = None):
        """Avisa a todos los módulos conectados (p. ej. core_online / core_offline)."""
        payload = {"type": "hub_event", "event": event}
        if extra:
            payload.update(extra)
        raw = json.dumps(payload, ensure_ascii=False)
        dead = []
        for mid, conn in list(self._conns.items()):
            try:
                await conn.ws.send(raw)
            except Exception:
                dead.append(mid)
        for mid in dead:
            self._conns.pop(mid, None)
        self._say(f"hub_event → {event} ({len(self._conns)} módulos)")

    async def _hub_command_from_core(self, ws, msg):
        cmd_id = msg.get("id") or uuid.uuid4().hex
        target = msg.get("target")
        action = msg.get("action") or ""
        params = msg.get("params") or {}
        timeout = float(msg.get("timeout") or 15)
        # send() es síncrono y bloqueante: ejecutar en executor
        result = await self._loop.run_in_executor(
            None, lambda: self.send(target, action, params, timeout=timeout),
        )
        try:
            await ws.send(json.dumps({
                "type": "hub_command_result",
                "id": cmd_id,
                **result,
            }, ensure_ascii=False))
        except ConnectionClosed:
            pass

    # ------------------------------------------------------------ API para Núcleo

    def list_modules(self):
        online = set(list(self._conns))
        return [{**m, "online": m["id"] in online} for m in self.registry.all()]

    def find(self, target, module_type=None):
        """target puede ser el id, el número (1) o el nombre ('Teléfono 1', 'TV 1').

        Si se indica module_type, el número se resuelve solo dentro de ese tipo
        (así '1' + type=tv encuentra 'TV 1' aunque exista 'Teléfono 1').
        """
        mods = self.registry.all()
        if module_type:
            mods = [m for m in mods if m.get("module_type") == module_type]
        if isinstance(target, int) or str(target).strip().isdigit():
            n = int(target)
            return next((m for m in mods if m.get("number") == n), None)
        t = _norm(target)
        return next(
            (m for m in mods if m["id"] == str(target) or _norm(m.get("name", "")) == t),
            None,
        )

    def send(self, target, action, params=None, timeout=15.0):
        """Manda una orden y espera la respuesta del teléfono. Nunca lanza excepciones:
        devuelve {"ok": bool, "module": nombre, "text": ..., "error": ..., "ms": latencia}."""
        rec = self.find(target)
        if rec is None:
            return {"ok": False, "error": f"No existe el módulo '{target}'"}
        if not (self._loop and self._thread and self._thread.is_alive()):
            return {"ok": False, "module": rec["name"], "error": "el servidor de módulos no está activo"}

        detalle = f" {params}" if params else ""
        self._say(f"-> {rec['name']}: {action}{detalle}")
        t0 = time.monotonic()
        fut = asyncio.run_coroutine_threadsafe(
            self._send(rec, action, params or {}, timeout), self._loop
        )
        try:
            result = fut.result(timeout + 5)
        except Exception as e:
            result = {"ok": False, "module": rec["name"], "error": f"{type(e).__name__}: {e}"}
        result["ms"] = round((time.monotonic() - t0) * 1000)
        estado = "OK" if result.get("ok") else "FALLO"
        self._say(f"<- {rec['name']}: {estado} {result.get('text') or result.get('error')} ({result['ms']} ms)")
        return result

    async def _send(self, rec, action, params, timeout):
        conn = self._conns.get(rec["id"])
        if conn is None:
            return {"ok": False, "module": rec["name"], "error": "desconectado"}
        cmd_id = uuid.uuid4().hex
        fut = self._loop.create_future()
        self._pending[cmd_id] = fut
        conn.pending.add(cmd_id)
        try:
            await conn.ws.send(json.dumps(
                {"type": "command", "id": cmd_id, "action": action, "params": params},
                ensure_ascii=False,
            ))
            result = await asyncio.wait_for(fut, timeout)
            return {**result, "module": rec["name"]}
        except asyncio.TimeoutError:
            return {"ok": False, "module": rec["name"], "error": "sin respuesta a tiempo"}
        except ConnectionClosed:
            return {"ok": False, "module": rec["name"], "error": "desconectado"}
        finally:
            self._pending.pop(cmd_id, None)
            conn.pending.discard(cmd_id)

    # ------------------------------------------------------------ peticiones módulo -> Núcleo

    async def _handle_core_request(self, conn, req_id, record, texto):
        """El módulo pidió algo al Núcleo. Acusamos recibo en el acto
        (core_ack) y resolvemos el turno en un hilo del executor; la
        respuesta real sale por core_response con el mismo id al terminar.

        Sin el acuse el teléfono cortaba la conexión, reencolaba el mismo
        texto y el Núcleo terminaba con varios turnos duplicados a la vez."""
        texto = (texto or "").strip()
        if not texto:
            await self._send_core_response(
                conn, req_id, {"ok": False, "error": "texto vacío"}
            )
            return

        # Modo embebido: callback local del proceso del Núcleo
        if self.on_core_request is not None:
            self._say(f"{record['name']} -> Núcleo (local): {texto[:100]!r}")
            await self._send_core_ack(conn, req_id)
            try:
                resp = await asyncio.wait_for(
                    self._loop.run_in_executor(
                        None, self.on_core_request, record["id"], texto
                    ),
                    timeout=CORE_TIMEOUT_SEGUNDOS,
                )
            except asyncio.TimeoutError:
                resp = {"ok": False, "error": f"El Núcleo tardó demasiado ({CORE_TIMEOUT_SEGUNDOS:.0f}s)."}
                self._say(f"{record['name']} <- Núcleo: TIMEOUT ({CORE_TIMEOUT_SEGUNDOS:.0f}s)")
            except Exception as e:
                resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            await self._send_core_response(conn, req_id, resp or {})
            resumen = (resp or {}).get("text") or (resp or {}).get("error") or "?"
            self._say(f"{record['name']} <- Núcleo: {str(resumen)[:100]!r}")
            return

        # Modo Coordinador: reenviar al Núcleo remoto (role=core)
        core_ws = self._core_ws
        if core_ws is None:
            self._say(f"{record['name']} pidió al Núcleo pero no hay core conectado: {texto[:60]!r}")
            await self._send_core_response(
                conn, req_id,
                {"ok": False, "error": "El Núcleo no está conectado al Coordinador"},
            )
            return

        self._say(f"{record['name']} -> Núcleo (remoto): {texto[:100]!r}")
        fut = self._loop.create_future()
        self._core_pending[req_id] = fut
        try:
            await core_ws.send(json.dumps({
                "type": "core_request",
                "id": req_id,
                "module_id": record["id"],
                "module_name": record.get("name"),
                "text": texto,
            }, ensure_ascii=False))
            resp = await asyncio.wait_for(fut, timeout=CORE_TIMEOUT_SEGUNDOS)
        except asyncio.TimeoutError:
            resp = {"ok": False, "error": f"El Núcleo tardó demasiado ({CORE_TIMEOUT_SEGUNDOS:.0f}s)."}
            self._say(f"{record['name']} <- Núcleo remoto: TIMEOUT ({CORE_TIMEOUT_SEGUNDOS:.0f}s)")
        except Exception as e:
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        finally:
            self._core_pending.pop(req_id, None)

        await self._send_core_response(conn, req_id, resp or {})
        resumen = (resp or {}).get("text") or (resp or {}).get("error") or "?"
        self._say(f"{record['name']} <- Núcleo remoto: {str(resumen)[:100]!r}")

    async def _send_core_ack(self, conn, req_id):
        try:
            await conn.ws.send(json.dumps(
                {"type": "core_ack", "id": req_id}, ensure_ascii=False))
        except ConnectionClosed:
            pass

    async def _send_core_response(self, conn, req_id, resp):
        payload = {
            "type": "core_response",
            "id": req_id,
            "ok": bool(resp.get("ok")),
            "text": resp.get("text") or "",
            "error": resp.get("error"),
        }
        try:
            await conn.ws.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            pass


# ---------------------------------------------------------------- consola de pruebas

_TYPE_ALIASES = {
    "phone": "phone", "telefono": "phone", "teléfono": "phone",
    "celular": "phone", "movil": "phone", "móvil": "phone",
    "tv": "tv", "tele": "tv", "televisor": "tv", "television": "tv",
    "televisión": "tv",
    "watch": "watch", "reloj": "watch",
    "headphone": "headphone", "audifonos": "headphone", "audífonos": "headphone",
}


def _parse_cli_target(parts):
    """Parsea el objetivo del CLI.

    Formatos aceptados:
      1 power on              → número (ambiguo si hay phone 1 y tv 1)
      tv 1 power on           → tipo + número
      tele 1 volume up
      "TV 1" power on         → nombre completo (con comillas no hace falta si no hay espacios raros)
      TV 1 power on           → nombre de dos tokens
    Devuelve (target, module_type|None, action, rest, parts_consumed_error|None)
    """
    if not parts:
        return None, None, None, "", "vacío"

    # tipo + número: tv 1 power on
    if len(parts) >= 3 and parts[0].lower() in _TYPE_ALIASES and (
        parts[1].isdigit() or parts[1].lower() in ("uno", "dos", "tres", "cuatro", "cinco")
    ):
        mtype = _TYPE_ALIASES[parts[0].lower()]
        num = parts[1]
        action = parts[2].lower()
        rest = " ".join(parts[3:]) if len(parts) > 3 else ""
        return num, mtype, action, rest, None

    # nombre compuesto tipo "TV 1" / "Teléfono 1"
    if len(parts) >= 3 and parts[1].isdigit() and parts[0].lower() in (
        "tv", "tele", "teléfono", "telefono", "módulo", "modulo", "reloj", "audífonos", "audifonos"
    ):
        name = f"{parts[0]} {parts[1]}"
        action = parts[2].lower()
        rest = " ".join(parts[3:]) if len(parts) > 3 else ""
        # Inferir tipo del nombre
        mtype = _TYPE_ALIASES.get(parts[0].lower())
        return name, mtype, action, rest, None

    # número o id + acción
    if len(parts) >= 2:
        target = parts[0]
        action = parts[1].lower()
        rest = " ".join(parts[2:]) if len(parts) > 2 else ""
        return target, None, action, rest, None

    return None, None, None, "", "Uso: [tipo] <número|nombre> <acción> [args]"


def _cli_params(action, rest):
    """Construye params según la acción (teléfono + TV)."""
    r = (rest or "").strip()
    rl = r.lower()
    if action == "say":
        return {"text": r}
    if action == "ask":
        return {"text": r}
    if action == "torch":
        return {"state": r or "toggle"}
    if action == "call":
        return {"who": r}
    if action == "open_app":
        return {"app": r}
    if action == "status":
        return {"what": r or "general"}
    if action == "power":
        return {"state": r or "toggle"}
    if action == "volume":
        if rl.isdigit():
            return {"level": int(rl)}
        if rl in ("up", "sube", "+", "mas", "más"):
            return {"direction": "up"}
        if rl in ("down", "baja", "-", "menos"):
            return {"direction": "down"}
        if rl in ("mute", "silencio"):
            return {"direction": "mute"}
        return {"direction": r} if r else {}
    if action == "source":
        return {"source": r}
    if action == "media_control":
        return {"action": r or "play"}
    if action == "channel":
        if rl.isdigit():
            return {"number": rl}
        if rl in ("up", "down", "siguiente", "anterior", "+", "-"):
            return {"direction": "up" if rl in ("up", "siguiente", "+") else "down"}
        return {"direction": r} if r else {}
    if action in ("key", "send_key"):
        return {"key": r}
    if action == "play":
        return {"title": r} if r else {}
    if action == "search":
        return {"query": r}
    # fallback: meter el resto como texto genérico
    return {"text": r} if r else {}


def _cli(hub):
    print("\nComandos:  lista | diag | ping | salir")
    print("Objetivo:  <número> | <tipo> <número> | <nombre>")
    print("  tipos:   phone/telefono | tv/tele | watch/reloj")
    print("Ejemplos teléfono:")
    print("  1 torch on | phone 1 torch off | 1 open_app whatsapp | 1 ping")
    print("Ejemplos TV:")
    print("  tv 1 power on | tv 1 volume up | tv 1 volume 20 | tv 1 open_app netflix")
    print("  tv 1 source hdmi1 | tv 1 media_control pause | tv 1 status | tv 1 ping\n")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("salir", "exit", "q"):
            break
        if line in ("lista", "list"):
            for m in hub.list_modules():
                estado = "EN LÍNEA" if m["online"] else "desconectado"
                tipo = m.get("module_type") or "?"
                print(f"  {m['name']}  [{tipo}]  #{m.get('number')}  "
                      f"id={m['id'][:8]}…  {estado}  ({m.get('device', '?')})")
            continue
        if line == "diag":
            print(hub.diagnostico())
            continue
        if line == "ping":
            results = hub.ping_all()
            if not results:
                print("No hay módulos en línea.")
            continue

        parts = line.split()
        target, mtype, action, rest, err = _parse_cli_target(parts)
        if err or not action:
            print(err or "Uso: [tipo] <número|nombre> <acción> [args]")
            print("  ej: tv 1 power on  |  phone 1 torch on  |  1 ping")
            continue

        params = _cli_params(action, rest)

        # Resolver con tipo si se indicó
        if mtype:
            rec = hub.find(target, module_type=mtype)
            if rec is None:
                print(f"No existe {mtype} #{target}")
                continue
            result = hub.send(rec["id"], action, params)
        else:
            # Número solo: si hay varios con ese número, avisar
            if str(target).isdigit():
                n = int(target)
                matches = [m for m in hub.list_modules() if m.get("number") == n]
                if len(matches) > 1:
                    nombres = ", ".join(f"{m['name']} [{m.get('module_type')}]" for m in matches)
                    print(f"Ambiguo #{n}: {nombres}")
                    print("  Usa: tv 1 …  o  phone 1 …")
                    continue
            result = hub.send(target, action, params)

        if result and not result.get("ok"):
            print(f"  → {result.get('error') or 'fallo'}")
        elif result and result.get("text"):
            print(f"  → {result.get('text')}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(name)s: %(message)s")
    hub = ModuloHub(verbose=True)
    hub.start()
    print(f"\nURL para el teléfono:  ws://{local_ip()}:{hub.port}")
    print(f"Token para el teléfono: {hub.token}")
    _cli(hub)
    hub.stop()
