"""Conmutador de motores: API primero, local de respaldo, detras del mismo puerto.

Cuarta posicion del puerto `ChatProvider`. Compone dos proveedores y decide por
su cuenta, asi que los 13 sitios que llaman al puerto no enteran de que existen
dos motores: siguen viendo `stream()` y `complete()`.

La regla de conmutacion es la ventana de lectura medida en esta caja. Un modelo
local con el prefijo en frio prefiere a 36-50 s y el stream muere en los 35 s de
`LLM_STREAM_LECTURA_SEGUNDOS` antes del primer token, asi que un reintento
tarde no es un plan B: es un turno sin respuesta. Por eso solo se cae a local
mientras la API no haya dicho nada; en cuanto emite un evento, el turno es suyo
y un fallo a mitad sigue siendo lo que ya era ("Se me fue el hilo").

Coherencia: el turno que contesta el local despues de un fallo de API recibe el
mismo prompt, y el historial de la sesion ya trae las respuestas que escribio la
API, registradas como cualquier otro turno. No hay nada que traducir ni que
transvasar: el contexto compartido es `_history`, no este modulo.
"""
from __future__ import annotations

import os
import time
from typing import Any, Iterable, List, Optional

from proveedores.llm.contrato import ChatEvent, ChatRequest, ChatResult

# Techo del primer evento de la API. Por debajo del peor TTFT local en frio y
# con margen para que el turno siga teniendo aire despues del reintento. Se
# puede mover con DARK_API_TTFT_TOPE_SEGUNDOS.
TOPE_PRIMER_TOKEN_SEGUNDOS = 8.0


def _acotar(timeout: Any, tope: float) -> Any:
    """Timeout de la llamada remota: nunca mas alla del tope del primer token."""
    if timeout is None:
        return tope
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        conexion, lectura = timeout
        return (conexion, tope if lectura is None else min(float(lectura), tope))
    try:
        return min(float(timeout), tope)
    except (TypeError, ValueError):
        return tope


class FlujoReanudado:
    """Stream que ya consumio su primer evento: lo devuelve antes de seguir."""

    def __init__(self, primero: ChatEvent, eventos: Iterable[ChatEvent],
                 flujo, motor: str):
        self._primero = primero
        self._eventos = eventos
        self._flujo = flujo
        self.status_code = getattr(flujo, "status_code", 200)
        self.motor = motor

    def iter_events(self):
        yield self._primero
        for evento in self._eventos:
            yield evento

    def close(self):
        cerrar = getattr(self._eventos, "close", None)
        if cerrar:
            try:
                cerrar()
            except Exception:
                pass
        self._flujo.close()


class ProveedorConmutado:
    """`primario` responde mientras pueda; `respaldo` cubre todo lo demas.

    `health()` y `loaded_models()` delegan en el respaldo: el broker pregunta por
    modelos residentes para decidir cargas de RAM, y eso solo existe en el motor
    local. El atributo publico `respaldo` es lo que usa el precalentamiento, que
    calienta el KV cache de la maquina, no el de un proveedor ajeno.
    """

    def __init__(self, primario, respaldo, *, tope_primer_token: Optional[float] = None,
                 log=print):
        self.primario = primario
        self.respaldo = respaldo
        if tope_primer_token is not None:
            self.tope = float(tope_primer_token)
        else:
            # Se lee al construir, no al importar: la fabrica arma el conmutador
            # en cada arranque y la variable tiene que poder cambiarse entre
            # sesiones sin tocar el codigo.
            self.tope = float(os.environ.get(
                "DARK_API_TTFT_TOPE_SEGUNDOS", TOPE_PRIMER_TOKEN_SEGUNDOS))
        self._log = log

    # ------------------------------------------------------------------
    def _nombre_primario(self) -> str:
        try:
            return self.primario.nombre() or "remoto"
        except Exception:
            return "remoto"

    def _se_puede(self) -> bool:
        disponible = getattr(self.primario, "disponible", None)
        try:
            return bool(disponible()) if disponible else True
        except Exception:
            return False

    def _abandonar(self, flujo, eventos) -> None:
        """Cierra el stream remoto fallido sin propagar nada: el turno ya es local."""
        for objeto in (eventos, flujo):
            if objeto is None:
                continue
            cerrar = getattr(objeto, "close", None)
            if cerrar:
                try:
                    cerrar()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    def stream(self, request: ChatRequest, timeout: Any = None):
        if not self._se_puede():
            return self.respaldo.stream(request, timeout=timeout)
        flujo = None
        eventos = None
        inicio = time.perf_counter()
        try:
            flujo = self.primario.stream(request, timeout=_acotar(timeout, self.tope))
            eventos = iter(flujo.iter_events())
            # `next()` con default: un stream que se acaba sin emitir nada cae a
            # local en vez de dejar un turno vacío.
            primero = next(eventos, None)
            if primero is None:
                raise RuntimeError("el stream remoto no emite eventos")
            motor = self._nombre_primario()
            self._log(f"[motor] {motor} en {time.perf_counter() - inicio:.1f}s")
            return FlujoReanudado(primero, eventos, flujo, motor)
        except Exception as e:
            self._abandonar(flujo, eventos)
            self._log(f"[motor] local: el remoto fallo antes de hablar "
                      f"({type(e).__name__}: {e}; "
                      f"{time.perf_counter() - inicio:.1f}s)")
            return self.respaldo.stream(request, timeout=timeout)

    def complete(self, request: ChatRequest, timeout: Any = None) -> ChatResult:
        if not self._se_puede():
            return self.respaldo.complete(request, timeout=timeout)
        inicio = time.perf_counter()
        try:
            resultado = self.primario.complete(request,
                                                timeout=_acotar(timeout, self.tope))
            self._log(f"[motor] {self._nombre_primario()} (completo) en "
                      f"{time.perf_counter() - inicio:.1f}s")
            return resultado
        except Exception as e:
            self._log(f"[motor] local: el remoto fallo ({type(e).__name__}: {e}; "
                      f"{time.perf_counter() - inicio:.1f}s)")
            return self.respaldo.complete(request, timeout=timeout)

    # ------------------------------------------------------------------
    def health(self, timeout: Any = None) -> bool:
        return self.respaldo.health(timeout=timeout)

    def loaded_models(self, timeout: Any = None) -> List[str]:
        return list(self.respaldo.loaded_models(timeout=timeout))
