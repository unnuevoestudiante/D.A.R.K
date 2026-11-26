"""Servicio de capacidades: las calcula en un hilo de fondo y avisa solo si cambian.

Calcularlas implica preguntar a Ollama por HTTP y abrir un par de sockets: poco
(décimas de segundo), pero nunca debe ocurrir dentro de un turno ni bloquear el
arranque. Por eso viven en un hilo propio que refresca cada cierto tiempo y llama
a `al_cambiar` únicamente cuando la carga que viaja a la interfaz es distinta,
para no despertar al WebSocket con el mismo mensaje.
"""
from __future__ import annotations

import threading
from typing import Callable

from . import registro
from .sondas import SondasReales


class ServicioCapacidades:
    def __init__(
        self,
        al_cambiar: Callable[[dict], None],
        sondas=None,
        intervalo_seg: float = 30.0,
    ) -> None:
        self._al_cambiar = al_cambiar
        self._sondas = sondas if sondas is not None else SondasReales()
        self._intervalo = intervalo_seg
        self._ultima: dict | None = None
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._despertar = threading.Event()

    # --------------------------------------------------------------------- API
    def actuales(self) -> dict | None:
        """La última carga calculada, o None si todavía no hay ninguna."""
        with self._lock:
            return self._ultima

    def refrescar(self) -> dict:
        """Recalcula ya (síncrono) y notifica si hubo cambio. Devuelve la carga."""
        carga = registro.para_interfaz(registro.calcular(self._sondas))
        with self._lock:
            cambio = carga != self._ultima
            self._ultima = carga
        if cambio:
            try:
                self._al_cambiar(carga)
            except Exception as error:  # un fallo de la interfaz no debe matar el hilo
                print(f"[capacidades] no se pudo publicar: {type(error).__name__}: {error}")
        return carga

    def iniciar(self) -> None:
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._parar.clear()
        self._hilo = threading.Thread(target=self._bucle, name="capacidades", daemon=True)
        self._hilo.start()

    def pedir_refresco(self) -> None:
        """Despierta al hilo para que recalcule sin esperar al intervalo."""
        self._despertar.set()

    def detener(self) -> None:
        self._parar.set()
        self._despertar.set()

    # ------------------------------------------------------------------- hilo
    def _bucle(self) -> None:
        while not self._parar.is_set():
            try:
                self.refrescar()
            except Exception as error:
                print(f"[capacidades] fallo al calcular: {type(error).__name__}: {error}")
            self._despertar.wait(self._intervalo)
            self._despertar.clear()
