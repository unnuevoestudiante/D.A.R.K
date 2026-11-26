"""Contratos del subsistema de SESIÓN DE RESULTADOS: el almacén compartido.

Es el sitio físico donde vive lo que una capacidad escribe y la presentación o la
voz leen. Nació porque los mismos nueve datos estaban declarados por duplicado —en
el núcleo y en el dueño de capacidades (`herramientas/internas/ejecutor.py`) y, los de
imágenes, además copiados por asignación al especialista de comunicación—, y nada
obligaba a que fuera el mismo objeto.

  Los campos, y quién los consume:

    `resultados_visuales`        Las tarjetas de la última búsqueda de imágenes o
                                 de la última lista de resultados. Lo escribe
                                 `buscar_imagenes` y lo leen el overlay
                                 (`payload_resultados`), la detección de acción
                                 sobre pantalla y la descarga por índice.
                                 Arranca en None, no en `[]`: la presentación
                                 distingue «todavía no se buscó» de «se buscó y no
                                 salió nada».
    `imagenes_vistas`            El conjunto de URLs ya enseñadas, para que
                                 `ampliar_imagenes` no repita las mismas.
    `ultima_query_imagenes`      La frase con la que se llegó a esas tarjetas. La
                                 reusan «bájame la 2» y el modo «más como esta».
    `intencion_imagenes`         Qué se pretendía con esas imágenes: None, tarjetas
                                 normales, `"wallpaper"`, `"descargar"`. Es lo que
                                 hace que «aplícala» sea fondo y no descarga.
    `espera_wallpaper_pregunta`  La pregunta de temática que quedó abierta. La abre
                                 quien ejecuta el poner-fondo y la cierra la voz
                                 cuando el usuario contesta o expira la ventana.
    `espera_wallpaper_abierta_en`  El instante desde el que corre la ventana. Se
                                 reancla mientras Dark habla: la cuenta no empieza
                                 con la pregunta, empieza con el silencio.
    `sintesis_fallida`           Lo que deja `investigar` cuando el resumen no salió
                                 a tiempo. Solo lo lee la narración de la voz, para
                                 no prometer un resumen que no hay.
    `ultimos_resultados`         Las cinco fuentes de la última búsqueda web, en el
                                 formato de `ddgs` (`title`, `body`, `href`). Las
                                 guarda `investigar` y las consume la voz:
                                 «abre la segunda» se resuelve contra esta lista, y
                                 `_seleccionar_resultado` la deja vacía al bajar una.
    `timer_ocultar_resultados`   La cuenta que esconde el panel de resultados. Es el
                                 único objeto vivo del almacén y está aquí por lo
                                 mismo que los demás: el temporizador lo arma quien
                                 muestra (núcleo o capacidad) y lo cancela quien
                                 esconde, que no siempre es el mismo. Con dos
                                 manijas, el `cancel()` del núcleo cancelaba su
                                 propio `None` y la cuenta del ejecutor seguía
                                 corriendo sobre un panel que ya no era suyo.

  Métodos:

    * `limpiar_imagenes()`
          Deja los cuatro campos de tarjetas como al arrancar. NO toca la espera de
          temática: ocultar resultados y cerrar una pregunta son dos decisiones
          distintas y mezclarlas borraría la ventana de 35 s al esconder el panel.

  Lo que este puerto NO tiene: política. No decide si una tarjeta es descargable, ni
  si la espera sigue viva, ni cómo se narra. Son reglas del consumidor, y el almacén
  solo garantiza que lo que uno escribe es exactamente lo que el otro lee.

  Quién lo construye: `nucleo/sesion_resultados.py:crear_sesion_resultados()`. Dueño
  del ciclo de vida es el núcleo (`DarkNucleo.sesion`), que lo reparte: al dueño de
  capacidades por `Servicios(sesion=...)` y a comunicación por su constructor. Los
  tres conservan los nombres con los que siempre accedieron, como vistas sobre este
  objeto; ningún consumidor lo declara en su `__init__`, porque esa asignación pisaría
  lo que otro ya escribió.

  Vive en memoria y no se persiste: es la pantalla de ESTE turno, no un dato del
  usuario. Al reiniciar el proceso vuelve a estar vacía.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Set, runtime_checkable

__all__ = ["PuertoSesionResultados"]


@runtime_checkable
class PuertoSesionResultados(Protocol):
    """El almacén compartido de lo que una capacidad escribe y otro lee."""

    @property
    def resultados_visuales(self) -> Optional[List[Dict[str, Any]]]:
        """Las tarjetas en pantalla, o None si nadie buscó todavía."""
        ...

    @resultados_visuales.setter
    def resultados_visuales(self, valor: Optional[List[Dict[str, Any]]]) -> None:
        ...

    @property
    def imagenes_vistas(self) -> Set[str]:
        """URLs ya enseñadas, para no repetirlas al ampliar."""
        ...

    @imagenes_vistas.setter
    def imagenes_vistas(self, valor: Set[str]) -> None:
        ...

    @property
    def ultima_query_imagenes(self) -> Optional[str]:
        """La frase con la que llegaron las tarjetas actuales."""
        ...

    @ultima_query_imagenes.setter
    def ultima_query_imagenes(self, valor: Optional[str]) -> None:
        ...

    @property
    def intencion_imagenes(self) -> Optional[str]:
        """Qué se pretendía con las tarjetas: None, "wallpaper" o "descargar"."""
        ...

    @intencion_imagenes.setter
    def intencion_imagenes(self, valor: Optional[str]) -> None:
        ...

    @property
    def espera_wallpaper_pregunta(self) -> Optional[str]:
        """La pregunta de temática que sigue abierta, o None."""
        ...

    @espera_wallpaper_pregunta.setter
    def espera_wallpaper_pregunta(self, valor: Optional[str]) -> None:
        ...

    @property
    def espera_wallpaper_abierta_en(self) -> Optional[float]:
        """Desde cuándo corre la ventana. Se reancla mientras Dark habla."""
        ...

    @espera_wallpaper_abierta_en.setter
    def espera_wallpaper_abierta_en(self, valor: Optional[float]) -> None:
        ...

    @property
    def sintesis_fallida(self) -> bool:
        """True si la última investigación no pudo resumir a tiempo."""
        ...

    @sintesis_fallida.setter
    def sintesis_fallida(self, valor: bool) -> None:
        ...

    @property
    def ultimos_resultados(self) -> Optional[List[Dict[str, Any]]]:
        """Las fuentes de la última búsqueda web, o None si nadie buscó."""
        ...

    @ultimos_resultados.setter
    def ultimos_resultados(self, valor: Optional[List[Dict[str, Any]]]) -> None:
        ...

    @property
    def timer_ocultar_resultados(self) -> Optional[Any]:
        """El `threading.Timer` que esconde el panel, o None si no corre."""
        ...

    @timer_ocultar_resultados.setter
    def timer_ocultar_resultados(self, valor: Optional[Any]) -> None:
        ...

    def limpiar_imagenes(self) -> None:
        """Deja los cuatro campos de tarjetas en su estado inicial."""
        ...
