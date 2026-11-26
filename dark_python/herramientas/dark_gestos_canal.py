"""Canal de gestos de D.A.R.K: del motor gestual al overlay, por WebSocket local.

Por qué un canal aparte y no ``dark_overlay_bridge``
----------------------------------------------------
El puente del overlay (puerto 8765) difunde su ESTADO completo y el frontend
trata cada mensaje como un estado nuevo: un evento de gesto ahí lo pisaría. Además
escucha en la red local y los gestos (posiciones de tus manos) no tienen por qué
salir del PC. Este canal:

* escucha SOLO en 127.0.0.1 (puerto 8768 por defecto),
* no bloquea nunca al motor (``emitir`` solo encola),
* descarta lo obsoleto: ``manos``, ``transformacion`` y ``cierre_progreso`` se
  funden en el último valor mientras el cliente no los haya leído,
* conserva el orden de los eventos discretos (``agarre_inicio``, ``agarre_fin``...)
  y no deja que un valor continuo viejo adelante a uno discreto posterior,
* no acumula nada si no hay ningún overlay conectado,
* un cliente lento se expulsa en vez de frenar a los demás.

Protocolo (JSON, un objeto por mensaje)
---------------------------------------
Motor -> overlay: la carga del motor tal cual (``{"evento": ..., ...}``) más
``seq`` (entero creciente). Al conectarse, el cliente recibe primero::

    {"evento": "hola", "canal": "gestos", "version": 1, "estado": <último gestos_on/off o null>}

Overlay -> motor::

    {"tipo": "sostiene", "valor": true|false}   # el agarre vigente sujeta un objeto
    {"tipo": "video",    "valor": true|false}   # reenviar el cuadro que ve el motor (calibración)
    {"tipo": "lectura",  "valor": true|false}   # línea de 1 Hz del log en caliente (config.LECTURA la decide al arrancar)
    {"tipo": "coger",    "manos": [id,...]}      # permanencia dentro de un objeto: AGARRE sin puño ([] suelta)

Uso
---
    canal = GestosCanal()
    canal.conectar_motor(motor)     # on_evento del motor -> canal; sostiene -> motor
    canal.iniciar()                 # nada se abre al importar ni al construir
    ...
    canal.detener()

Requiere ``pip install websockets`` (se importa al iniciar, no al importar).
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8768
VERSION = 1
# Eventos que se funden en el último valor si el cliente no alcanza a leerlos.
# `cuadro` está aquí porque es píxel, no estado: un cliente lento debe perder
# cuadros, no acumular megas de base64 hasta quedarse atrás.
CONTINUOS = frozenset({"manos", "transformacion", "cierre_progreso", "cuadro"})
COLA_MAX = 256              # tope de mensajes pendientes (los discretos son pocos)
TIMEOUT_ENVIO = 0.5         # s; un cliente que no acepta un mensaje en este tiempo se expulsa
ARRANQUE_TIMEOUT = 5.0
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


class GestosCanal:
    def __init__(
        self,
        host: str = HOST,
        port: int = PORT,
        on_mensaje: Callable[[dict], None] | None = None,
        permitir_red: bool = False,
    ) -> None:
        if host not in _LOOPBACK and not permitir_red:
            raise ValueError(
                f"host {host!r} no es local: los gestos no deben salir del PC "
                "(usa permitir_red=True solo si sabes lo que haces)"
            )
        self.host = host
        self.port = port
        self.on_mensaje = on_mensaje

        self._lock = threading.Lock()
        self._cola: deque[dict] = deque(maxlen=COLA_MAX)
        self._pendiente_cont: dict[str, dict] = {}
        self._seq = 0
        self._estado: dict | None = None   # último gestos_on / gestos_off
        self._n_clientes = 0

        self._clientes: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._despertar: asyncio.Event | None = None
        self._servidor = None
        self._thread: threading.Thread | None = None
        self._listo = threading.Event()
        self._error: Exception | None = None
        self._stop_lock = threading.Lock()
        self._stop_requested = False
        self._stop_scheduled = False
        self._run_forever_started = False
        self.descartados = 0               # mensajes continuos fundidos (diagnóstico)

    # --- API pública -------------------------------------------------------
    def conectar_motor(self, motor: Any) -> None:
        """Une un ``GestureEngine`` (sin importarlo): eventos hacia el canal, ``sostiene``, ``video``, ``lectura`` y ``coger`` de vuelta."""
        motor.on_evento = self.emitir
        previo = self.on_mensaje

        def hacia_motor(mensaje: dict) -> None:
            tipo = mensaje.get("tipo")
            if tipo == "sostiene":
                motor.fijar_sostiene(bool(mensaje.get("valor")))
            elif tipo == "video":
                motor.fijar_video(bool(mensaje.get("valor")))
            elif tipo == "lectura":
                motor.fijar_lectura(bool(mensaje.get("valor")))
            elif tipo == "coger":
                # Es texto que llega del navegador: se filtran los ids que no son
                # número aquí, en la frontera, antes de que el motor los convierta.
                pedido = mensaje.get("manos")
                if isinstance(pedido, list):
                    ids = [int(i) for i in pedido if isinstance(i, (int, float)) and not isinstance(i, bool)]
                    motor.fijar_agarre(ids[:2])
            elif previo is not None:
                previo(mensaje)

        self.on_mensaje = hacia_motor

    def emitir(self, carga: dict) -> None:
        """Encola un evento del motor. No bloquea y se puede llamar desde cualquier hilo."""
        evento = carga.get("evento")
        if not isinstance(evento, str):
            return
        with self._lock:
            self._seq += 1
            mensaje = {**carga, "seq": self._seq}
            if evento in ("gestos_on", "gestos_off"):
                self._estado = mensaje
            if self._n_clientes == 0:
                return  # nadie escucha: solo se recuerda el estado para el próximo cliente
            if evento in CONTINUOS:
                previo = self._pendiente_cont.get(evento)
                if previo is not None:
                    previo.clear()
                    previo.update(mensaje)   # se funde en el pendiente (mantiene su sitio en la cola)
                    self.descartados += 1
                    return
                self._pendiente_cont[evento] = mensaje
            else:
                # Barrera: los continuos posteriores van detrás de este discreto.
                self._pendiente_cont.clear()
            self._cola.append(mensaje)
        self._despertar_pump()

    def iniciar(self) -> None:
        """Abre el servidor en un hilo propio. Lanza RuntimeError si no puede (p. ej. puerto ocupado)."""
        if self._thread is not None and self._thread.is_alive():
            return
        try:
            import websockets  # noqa: F401  (se comprueba aquí: importar el módulo no la exige)
        except ImportError as exc:
            raise RuntimeError("Falta la dependencia: pip install websockets") from exc
        self._error = None
        self._listo.clear()
        with self._stop_lock:
            self._stop_requested = False
            self._stop_scheduled = False
            self._run_forever_started = False
        self._thread = threading.Thread(target=self._run, name="dark-gestos-canal", daemon=True)
        self._thread.start()
        if not self._listo.wait(ARRANQUE_TIMEOUT):
            raise RuntimeError("El canal de gestos no arrancó a tiempo")
        if self._error is not None:
            raise RuntimeError(f"El canal de gestos no pudo abrir {self.host}:{self.port}: {self._error}") from self._error

    def detener(self, timeout: float = 5.0) -> None:
        loop, thread = self._loop, self._thread
        with self._stop_lock:
            self._stop_requested = True
            programar_parada = (
                loop is not None
                and self._run_forever_started
                and not self._stop_scheduled
            )
            if programar_parada:
                self._stop_scheduled = True
        if programar_parada and loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self._parar)
            except RuntimeError:
                if not loop.is_closed():
                    raise
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        with self._lock:
            self._cola.clear()
            self._pendiente_cont.clear()
            self._n_clientes = 0

    @property
    def clientes(self) -> int:
        return self._n_clientes

    # --- hilo del servidor -------------------------------------------------
    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._servir())
        except Exception as exc:  # puerto ocupado, etc.
            self._error = exc
            loop.close()
            self._listo.set()
            return
        with self._stop_lock:
            if self._stop_requested and not self._stop_scheduled:
                self._stop_scheduled = True
                loop.call_soon(self._parar)
            self._run_forever_started = True
        try:
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _servir(self) -> None:
        import websockets

        self._despertar = asyncio.Event()
        self._servidor = await websockets.serve(
            self._atender, self.host, self.port,
            max_size=4096, ping_interval=20, ping_timeout=20,
        )
        self._tarea_pump = asyncio.ensure_future(self._pump())
        LOGGER.info("Canal de gestos escuchando en ws://%s:%s", self.host, self.port)
        self._listo.set()

    def _parar(self) -> None:
        async def cerrar() -> None:
            self._tarea_pump.cancel()
            if self._servidor is not None:
                self._servidor.close()
                try:
                    await asyncio.wait_for(self._servidor.wait_closed(), 2.0)
                except Exception:
                    pass
            asyncio.get_running_loop().stop()

        asyncio.ensure_future(cerrar())

    def _despertar_pump(self) -> None:
        loop, evento = self._loop, self._despertar
        if loop is not None and evento is not None and loop.is_running():
            loop.call_soon_threadsafe(evento.set)

    async def _atender(self, websocket) -> None:
        self._clientes.add(websocket)
        with self._lock:
            self._n_clientes = len(self._clientes)
            estado = dict(self._estado) if self._estado is not None else None
        try:
            hola = {"evento": "hola", "canal": "gestos", "version": VERSION, "estado": estado}
            await asyncio.wait_for(websocket.send(json.dumps(hola)), TIMEOUT_ENVIO)
            async for crudo in websocket:
                try:
                    mensaje = json.loads(crudo)
                except (TypeError, ValueError):
                    continue
                if isinstance(mensaje, dict) and self.on_mensaje is not None:
                    try:
                        self.on_mensaje(mensaje)
                    except Exception:
                        LOGGER.exception("Falló on_mensaje del canal de gestos")
        except Exception as exc:
            if "ConnectionClosed" not in type(exc).__name__:
                LOGGER.debug("Cliente del canal de gestos: %r", exc)
        finally:
            self._clientes.discard(websocket)
            with self._lock:
                self._n_clientes = len(self._clientes)
                if self._n_clientes == 0:
                    self._cola.clear()
                    self._pendiente_cont.clear()

    async def _pump(self) -> None:
        assert self._despertar is not None
        while True:
            await self._despertar.wait()
            self._despertar.clear()
            while True:
                with self._lock:
                    if not self._cola:
                        break
                    mensaje = self._cola.popleft()
                    if self._pendiente_cont.get(mensaje.get("evento")) is mensaje:
                        del self._pendiente_cont[mensaje["evento"]]
                    datos = json.dumps(mensaje)
                await self._difundir(datos)

    async def _difundir(self, datos: str) -> None:
        clientes = list(self._clientes)
        if not clientes:
            return
        resultados = await asyncio.gather(
            *(self._enviar_a(c, datos) for c in clientes), return_exceptions=True
        )
        for cliente, ok in zip(clientes, resultados):
            if ok is not True:
                self._clientes.discard(cliente)
                try:
                    await cliente.close()
                except Exception:
                    pass
        with self._lock:
            self._n_clientes = len(self._clientes)

    @staticmethod
    async def _enviar_a(cliente, datos: str) -> bool:
        try:
            await asyncio.wait_for(cliente.send(datos), TIMEOUT_ENVIO)
            return True
        except Exception:
            return False