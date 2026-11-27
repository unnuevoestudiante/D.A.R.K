"""Contrato del subsistema de OVERLAY: puerto del puente con la interfaz.

Las firmas NO son inventadas: reproducen exactamente lo que los consumidores
usan hoy (audit del 24-oct-2026). Backend actual:
`dark_python/modulos/dark_overlay_bridge.py` (clase `OverlayBridge`, servidor
WebSocket :8765 + HTTP :8767 para la tele).

  Escritura de estado (única vía legítima para pintar):
      * dark_nucleo.py:4276,4717,7313,7339   set(state, text, level,
            menu_data, results_data, progress). El estado es literal de
            cadena: lock | idle | listening | thinking | speaking |
            transcribing | showing_results | acting.
      * dark_nucleo.py:3918                  publish_audio(pcm, rate, width,
            channels, text) → int (audioSeq); lo consume /tv por HTTP.
      * dark_nucleo.py:4506                  set_lock_input_ready(ready).
      * dark_nucleo.py (cambio de contraseña) set_cambio_contrasena(activo) /
            set_error_contrasena(mensaje): flags del bloqueo que el frontend
            lee del payload (passwordChange / passwordError).
      * dark_nucleo.py:4711,4716             silenciar() / reactivar().
            Mientras está silenciado, `set` ignora todo estado no-idle.
      * modulos/tv/modulo.py:433, netflix.py:241   progress(step, total, label).
      * dark_nucleo.py:1439,1463             modo_televisor(True) /
            modo_computador(): la conversación se va a la tele y el overlay
            del PC se oculta.

  Señal TV (qué pantalla es la destino de ESTE turno):
      * dark_nucleo.py:1500,1551             iniciar_senal_tv(motivo).
      * dark_nucleo.py:1506,1559,1543,3789   fin_senal_tv().
      * dark_nucleo.py:3915,3936             senal_tv_activa() / destino_ui().

  Lecturas de estado (Fase A de la normalización del overlay):
      Hasta hoy el núcleo leía el dict interno del bridge en 23 sitios
      (`overlay._state["state"]`) y escribía un flag que el bridge ni siquiera
      declaraba (`overlay._tv_cerrar_tras_speak`, creado por apaño desde
      dark_nucleo.py:1501). Esas cuatro sustituyen a los accesos privados:
      * estado()             → qué estado está visible ahora.
      * tiene_resultados()   → si hay tarjetas/carrusel en pantalla (los
            timeouts de listening/thinking no deben limpiarlas).
      * actualizar_sin_emitir(...) → coherencia interna cuando el overlay ya
            está oculto (`_overlay_oculto` en el núcleo).
      * marcar_tv_cerrar_al_hablar() / consumir_tv_cerrar_al_hablar() → el
            cierre diferido de la señal TV al terminar de hablar la frase.

No forma parte del puerto `estado_para_tv()`: lo llama solo el propio servidor
HTTP del bridge; es un detalle del adaptador.

Regla de la casa: un consumidor nunca importa el motor. `OverlayBridge` se
construye en la fábrica del paquete `overlay` (Fase B), no en el núcleo, y
ningún lector toca `bridge._state` ni ningún atributo con `_`.

Solo stdlib.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class PuertoOverlay(Protocol):
    """Puerto del puente entre el núcleo y la interfaz (overlay del PC,
    modal de archivos y pantalla de la tele).

    Un backend futuro (otra UI, otro transporte, sin tele) implementa esto y
    se enchufa en la fábrica sin tocar al núcleo.
    """

    def set(
        self,
        state: str,
        text: str | None = None,
        level: float | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
        progress: dict | None = None,
    ) -> None:
        """Pinta un estado en la interfaz y hace broadcast. `None` en
        `text`/`menu_data`/`results_data`/`progress` significa "no tocar ese
        campo"; `state == "idle"` sí los limpia —salvo un menú abierto: el reposo
        no cierra lo que el usuario pidió, cerrar es explícito—. Con el overlay
        silenciado solo se admite "idle"."""
        ...

    def level(self, value: float) -> None:
        """Nivel de audio 0.0-1.0 (se recorta por contrato)."""
        ...

    def progress(self, step: int, total: int, label: str) -> None:
        """Atajo de acción larga: equivale a set("acting", text=label) con
        progreso {step, total, label}."""
        ...

    def intencion(self, titulo: str, detalle: str | None = None) -> None:
        """Anuncia lo que D.A.R.K. está haciendo («Abriendo aplicación» ·
        «Discord») sin cambiar de estado. Solo en thinking/acting; fuera de eso
        se ignora. Viaja en el payload como `intent: {titulo, detalle}` y se
        limpia al cambiar de estado. Ver overlay/intencion.py."""
        ...

    def silenciar(self) -> None:
        """Oculta la interfaz por completo y fuerza idle. Los `set` no-idle
        se ignoran hasta reactivar()."""
        ...

    def reactivar(self) -> None:
        """Deja de silenciar. No pinta nada: el llamador hace el `set` que
        corresponda."""
        ...

    def set_lock_input_ready(self, ready: bool) -> None:
        """Señala si el campo seguro de contraseña está listo en el bloqueo."""
        ...

    def set_cambio_contrasena(self, activo: bool) -> None:
        """Con True, el bloqueo que viene pinta la pantalla de CREAR
        contraseña (cambio por voz en curso) en vez de la de verificarla.
        El núcleo la limpia al conceder el acceso."""
        ...

    def set_error_contrasena(self, mensaje: str | None) -> None:
        """Motivo de un rechazo de acceso que la pantalla de bloqueo muestra
        (p. ej. la política de un solo uso de la contraseña). `None` limpia."""
        ...

    def set_capacidades(self, carga: dict | None) -> None:
        """Publica el registro de capacidades (`{resumen, items}`) que la
        insignia y el panel de estado leen. `None` lo limpia."""
        ...

    def set_especialista_enfocado(self, especialista: str | None) -> None:
        """Publica el especialista al que se dirige el texto libre del overlay."""
        ...

    def set_centinela(self, carga: dict | None) -> None:
        """Publica el estado del centinela: los avisos pendientes
        (`{cantidad, urgente, items}`) y si D.A.R.K. está hablando desde él
        (`hablando`, `texto`). Mientras habla desde el centinela la interfaz
        grande no se levanta. Con guarda de cambio."""
        ...

    def set_arranque(self, piezas: list | None) -> None:
        """Publica el estado de la infraestructura para el log de la ignición
        (`[{id, nombre, estado}]`, ver nucleo/arranque_log.py). Con guarda de
        cambio; `None` lo limpia."""
        ...

    def iniciar_senal_tv(self, motivo: str = "") -> None:
        """Hay una orden dirigida al televisor; /tv puede reaccionar."""
        ...

    def fin_senal_tv(self) -> None:
        """Terminó la orden puntual. No-op en modo televisor (allí toda la
        conversación es señal)."""
        ...

    def senal_tv_activa(self) -> bool:
        """True en modo televisor o con una orden TV en curso."""
        ...

    def destino_ui(self) -> str:
        """"pc" | "tv": a qué pantalla va la conversación actual."""
        ...

    def modo_televisor(self, activo: bool = True) -> None:
        """Conversación en la tele; oculta el overlay del PC."""
        ...

    def modo_computador(self) -> None:
        """Vuelve la conversación al PC (equivale a modo_televisor(False))."""
        ...

    def publish_audio(
        self,
        pcm: bytes,
        rate: int = 22050,
        width: int = 2,
        channels: int = 1,
        text: str | None = None,
    ) -> int:
        """Empaqueta PCM en WAV, avanza audioSeq y devuelve ese número de
        secuencia para que la tele descargue la frase correcta."""
        ...

    def estado(self) -> str:
        """Estado visible ahora. Lectura puntual, no suscripción."""
        ...

    def tiene_resultados(self) -> bool:
        """Hay tarjetas o carrusel en pantalla."""
        ...

    def actualizar_sin_emitir(
        self,
        state: str,
        text: str | None = None,
        menu_data: dict | None = None,
        results_data: dict | list | None = None,
    ) -> None:
        """Escribe el estado interno sin broadcast (overlay ya oculto)."""
        ...

    def marcar_tv_cerrar_al_hablar(self) -> None:
        """Pide cerrar la señal TV cuando termine la frase en curso."""
        ...

    def consumir_tv_cerrar_al_hablar(self) -> bool:
        """True si había cierre pendiente, y lo limpia."""
        ...


__all__ = ["PuertoOverlay"]
