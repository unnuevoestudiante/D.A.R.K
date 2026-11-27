"""Fachada del overlay: la política de pintado y los temporales de apagado.

El núcleo decide QUÉ estado toca; aquí vive CÓMO se pinta:

  * Los guardas que impedían pintar cuando el acceso está bloqueado o cuando
    el PC está en silencio porque habló un módulo (antes, dentro de
    `_set_overlay`, repetidos por cada camino de pintado).
  * El camino silencioso: con la interfaz oculta el estado se sigue guardando
    (`actualizar_sin_emitir`) para que al volver todo quede coherente, pero no
    se emite nada al WebSocket.
  * Los temporales que devuelven el overlay a idle si algo se colgó:
    "thinking" (por defecto 60 s), el reposo diferido tras hablar (4 s) y el
    "listening" abandonado, que sigue apagado por defecto (el núcleo llamaba
    al armado sin segundos y nunca llegaba a armarse).

Las decisiones que son del núcleo llegan como callables, no como referencia al
núcleo: así la fachada se prueba con dobles y no importa `nucleo`.

`set()` se delega crudo: hay caminos de arranque y de cierre que pintan sin
política a propósito. Lo normal es `pintar()`.
"""
from __future__ import annotations

import threading
from typing import Callable

from . import config


class FachadaOverlay:
    """Puerto de overlay + política. Implementa `contratos.overlay.PuertoOverlay`
    por delegación en el bridge que se le pasa (construido en overlay/fabrica.py)."""

    def __init__(
        self,
        bridge,
        *,
        puede_pintar: Callable[[str], bool] | None = None,
        al_cambiar_estado: Callable[[str, str], None] | None = None,
        escucha_seg: float | None = None,
        pensamiento_seg: float | None = None,
        reposo_seg: float | None = None,
    ) -> None:
        self.bridge = bridge
        self._puede_pintar = puede_pintar if puede_pintar is not None else _siempre
        self._al_cambiar_estado = (
            al_cambiar_estado if al_cambiar_estado is not None else _nada
        )
        self.escucha_seg = (
            config.ESCUCHA_TIMEOUT_SEG if escucha_seg is None else escucha_seg
        )
        self.pensamiento_seg = (
            config.PENSAMIENTO_TIMEOUT_SEG
            if pensamiento_seg is None else pensamiento_seg
        )
        self.reposo_seg = (
            config.REPOSO_DIFERIDO_SEG if reposo_seg is None else reposo_seg
        )
        self._oculto = False
        self._timer_escucha: threading.Timer | None = None
        self._timer_pensamiento: threading.Timer | None = None
        self._timer_reposo: threading.Timer | None = None

    # ---------- política ----------

    @property
    def oculto(self) -> bool:
        """La interfaz está oculta: se guarda estado, no se emite."""
        return self._oculto

    def pintar(
        self,
        state: str,
        text: str | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
    ) -> None:
        """Pinta respetando guardas, timers y el camino silencioso."""
        if not self._puede_pintar(state):
            return
        anterior = self.bridge.estado()
        self._armar_por_estado(state)
        if self._oculto:
            self.bridge.actualizar_sin_emitir(
                state, text=text, menu_data=menu_data, results_data=results_data
            )
        else:
            self.bridge.set(
                state, text=text, menu_data=menu_data, results_data=results_data
            )
        self._al_cambiar_estado(anterior, state)

    def ocultar(self) -> None:
        """Esconde la interfaz: el bridge deja de emitir y aquí se guarda estado."""
        self._oculto = True
        self.bridge.silenciar()

    def mostrar(self) -> None:
        """Vuelve a emitir y arranca en listening (no habla: eso lo decide el núcleo)."""
        self._oculto = False
        self.bridge.reactivar()
        self.bridge.set("listening")

    # ---------- temporales ----------

    def _armar_por_estado(self, state: str) -> None:
        if state == "listening":
            self._armar_escucha()
        else:
            self._cancelar("_timer_escucha")
        if state == "thinking":
            self._armar_pensamiento()
        else:
            self._cancelar("_timer_pensamiento")

    def _armar_escucha(self, segundos: float | None = None) -> None:
        self._cancelar("_timer_escucha")
        segundos = self.escucha_seg if segundos is None else segundos
        if not segundos or segundos <= 0:
            return
        self._timer_escucha = self._correr(segundos, self._expira_escucha)

    def _expira_escucha(self) -> None:
        # Un timer que revienta no puede tumbar el proceso: el hilo ya no tiene
        # llamador encima, así que el error se traga aquí y no en el núcleo.
        try:
            if (
                self.bridge.estado() == "listening"
                and not self.bridge.tiene_resultados()
            ):
                self.pintar("idle")
        except Exception:
            pass

    def _armar_pensamiento(self, segundos: float | None = None) -> None:
        self._cancelar("_timer_pensamiento")
        segundos = self.pensamiento_seg if segundos is None else segundos
        self._timer_pensamiento = self._correr(segundos, self._expira_pensamiento)

    def _expira_pensamiento(self) -> None:
        try:
            if self.bridge.estado() == "thinking":
                self.pintar("idle")
        except Exception:
            pass

    def armar_reposo(self, segundos: float | None = None) -> None:
        """Devuelve el overlay a idle si nadie pinta nada antes de `segundos`."""
        self._cancelar("_timer_reposo")
        segundos = self.reposo_seg if segundos is None else segundos
        self._timer_reposo = self._correr(segundos, lambda: self.pintar("idle"))

    def cancelar_reposo(self) -> None:
        self._cancelar("_timer_reposo")

    def cancelar_timers(self) -> None:
        """Apaga los tres temporales (re-bloqueo y cierre del núcleo)."""
        for nombre in ("_timer_escucha", "_timer_pensamiento", "_timer_reposo"):
            self._cancelar(nombre)

    def _cancelar(self, nombre: str) -> None:
        timer = getattr(self, nombre, None)
        if timer is not None:
            timer.cancel()
            setattr(self, nombre, None)

    @staticmethod
    def _correr(segundos: float, accion) -> threading.Timer:
        timer = threading.Timer(segundos, accion)
        timer.daemon = True
        timer.start()
        return timer

    # ---------- delegación cruda en el puente ----------

    def set(
        self,
        state: str,
        text: str | None = None,
        level: float | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
        progress: dict | None = None,
    ) -> None:
        self.bridge.set(
            state,
            text=text,
            level=level,
            menu_data=menu_data,
            results_data=results_data,
            progress=progress,
        )

    def level(self, value: float) -> None:
        self.bridge.level(value)

    def progress(self, step: int, total: int, label: str) -> None:
        self.bridge.progress(step, total, label)

    def intencion(self, titulo: str, detalle: str | None = None) -> None:
        """Con la misma política que `pintar`: oculto o con la guarda del
        núcleo cerrada, no se anuncia nada."""
        if self._oculto or not self._puede_pintar(self.bridge.estado()):
            return
        self.bridge.intencion(titulo, detalle)

    def silenciar(self) -> None:
        self.bridge.silenciar()

    def reactivar(self) -> None:
        self.bridge.reactivar()

    def set_lock_input_ready(self, ready: bool) -> None:
        self.bridge.set_lock_input_ready(ready)

    def set_cambio_contrasena(self, activo: bool) -> None:
        self.bridge.set_cambio_contrasena(activo)

    def set_error_contrasena(self, mensaje: str | None) -> None:
        self.bridge.set_error_contrasena(mensaje)

    def set_capacidades(self, carga: dict | None) -> None:
        self.bridge.set_capacidades(carga)

    def set_especialista_enfocado(self, especialista: str | None) -> None:
        self.bridge.set_especialista_enfocado(especialista)

    def set_centinela(self, carga: dict | None) -> None:
        self.bridge.set_centinela(carga)

    def set_arranque(self, piezas: list | None) -> None:
        self.bridge.set_arranque(piezas)

    def velo(self, bajado: bool) -> None:
        """Baja (o sube) la oscuridad del fondo del overlay para ver lo que hay
        detrás. No es un estado de pintado: es una orden del usuario, así que
        sobrevive a `silenciar` y a `ocultar` hasta que otra orden la cambie."""
        self.bridge.set_veil_bajado(bajado)

    def iniciar_senal_tv(self, motivo: str = "") -> None:
        self.bridge.iniciar_senal_tv(motivo=motivo)

    def fin_senal_tv(self) -> None:
        self.bridge.fin_senal_tv()

    def senal_tv_activa(self) -> bool:
        return self.bridge.senal_tv_activa()

    def destino_ui(self) -> str:
        return self.bridge.destino_ui()

    def modo_televisor(self, activo: bool = True) -> None:
        self.bridge.modo_televisor(activo)

    def modo_computador(self) -> None:
        self.bridge.modo_computador()

    def publish_audio(
        self,
        pcm: bytes,
        rate: int = 22050,
        width: int = 2,
        channels: int = 1,
        text: str | None = None,
    ) -> int:
        return self.bridge.publish_audio(
            pcm, rate=rate, width=width, channels=channels, text=text
        )

    def estado(self) -> str:
        return self.bridge.estado()

    def tiene_resultados(self) -> bool:
        return self.bridge.tiene_resultados()

    def actualizar_sin_emitir(
        self,
        state: str,
        text: str | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
    ) -> None:
        self.bridge.actualizar_sin_emitir(
            state, text=text, menu_data=menu_data, results_data=results_data
        )

    def marcar_tv_cerrar_al_hablar(self) -> None:
        self.bridge.marcar_tv_cerrar_al_hablar()

    def consumir_tv_cerrar_al_hablar(self) -> bool:
        return self.bridge.consumir_tv_cerrar_al_hablar()


def _siempre(state: str) -> bool:
    return True


def _nada(anterior: str, nuevo: str) -> None:
    return None
