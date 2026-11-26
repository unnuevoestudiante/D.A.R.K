"""El almacén compartido de lo que una capacidad escribe y la voz o la pantalla leen.

Hasta ahora los nueve datos estaban declarados por duplicado: una copia en el
núcleo y otra en el dueño de capacidades (`herramientas/internas/ejecutor.py`) y,
en el caso de las imágenes, cuatro asignaciones que volcaban la del núcleo sobre
el especialista de comunicación justo antes de despachar. Nada obligaba a que
fueran el mismo objeto, así que el fallo era silencioso: la tarjeta seguía en
pantalla y la voz decía «no hay resultados», `investigar` dejaba la bandera de
síntesis en su lado y `_narrar_resultado` nunca la veía, y la lista web se
quedaba en el ejecutor mientras `_detectar_seleccion_resultado` miraba la suya
propia —vacía siempre—, con lo que «abre la segunda» no existía.

Aquí vive UNA vez. Los tres consumidores siguen accediendo con los nombres de
siempre (`self._resultados_visuales` en el núcleo, `resultados_visuales` en el
ejecutor), pero esos nombres son propiedades que leen y escriben este objeto, no
copias. Por eso ningún consumidor declara estos campos en su `__init__`: la
asignación pisaría lo que otro ya escribió.

El dueño del ciclo de vida es el núcleo (`DarkNucleo.sesion`); lo reparte al
ejecutor por `Servicios(sesion=...)` y a comunicación por su constructor. Quien
lo construye sin que se lo den —pruebas sueltas, fábricas aisladas— se crea el
suyo y sigue funcionando: es estado de este turno, no un dato que haya que
compartir con alguien que no existe.

El contrato, con el consumo medido de cada campo, está en
`contratos/sesion_resultados.py`. La política no vive aquí: si una tarjeta es
descargable, si la espera de temática sigue viva o cómo se narra lo decide cada
consumidor.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from contratos.sesion_resultados import PuertoSesionResultados

__all__ = ["SesionResultados", "crear_sesion_resultados"]


class SesionResultados:
    """Los nueve valores, con su estado de arranque."""

    def __init__(self) -> None:
        # None, y no `[]`: la presentación distingue «nadie buscó todavía» de
        # «se buscó y no salió nada».
        self._resultados_visuales: Optional[List[Dict[str, Any]]] = None
        self._imagenes_vistas: Set[str] = set()
        self._ultima_query_imagenes: Optional[str] = None
        self._intencion_imagenes: Optional[str] = None
        self._espera_wallpaper_pregunta: Optional[str] = None
        self._espera_wallpaper_abierta_en: Optional[float] = None
        self._sintesis_fallida: bool = False
        self._ultimos_resultados: Optional[List[Dict[str, Any]]] = None
        # Un `threading.Timer`, y es el único objeto vivo del almacén: está aquí
        # porque el panel es uno y quien lo esconde tiene que cancelar la cuenta
        # que armó quien lo mostró.
        self._timer_ocultar_resultados: Optional[Any] = None

    @property
    def resultados_visuales(self) -> Optional[List[Dict[str, Any]]]:
        return self._resultados_visuales

    @resultados_visuales.setter
    def resultados_visuales(self, valor: Optional[List[Dict[str, Any]]]) -> None:
        self._resultados_visuales = valor

    @property
    def imagenes_vistas(self) -> Set[str]:
        return self._imagenes_vistas

    @imagenes_vistas.setter
    def imagenes_vistas(self, valor: Set[str]) -> None:
        self._imagenes_vistas = valor

    @property
    def ultima_query_imagenes(self) -> Optional[str]:
        return self._ultima_query_imagenes

    @ultima_query_imagenes.setter
    def ultima_query_imagenes(self, valor: Optional[str]) -> None:
        self._ultima_query_imagenes = valor

    @property
    def intencion_imagenes(self) -> Optional[str]:
        return self._intencion_imagenes

    @intencion_imagenes.setter
    def intencion_imagenes(self, valor: Optional[str]) -> None:
        self._intencion_imagenes = valor

    @property
    def espera_wallpaper_pregunta(self) -> Optional[str]:
        return self._espera_wallpaper_pregunta

    @espera_wallpaper_pregunta.setter
    def espera_wallpaper_pregunta(self, valor: Optional[str]) -> None:
        self._espera_wallpaper_pregunta = valor

    @property
    def espera_wallpaper_abierta_en(self) -> Optional[float]:
        return self._espera_wallpaper_abierta_en

    @espera_wallpaper_abierta_en.setter
    def espera_wallpaper_abierta_en(self, valor: Optional[float]) -> None:
        self._espera_wallpaper_abierta_en = valor

    @property
    def sintesis_fallida(self) -> bool:
        return self._sintesis_fallida

    @sintesis_fallida.setter
    def sintesis_fallida(self, valor: bool) -> None:
        self._sintesis_fallida = valor

    @property
    def ultimos_resultados(self) -> Optional[List[Dict[str, Any]]]:
        return self._ultimos_resultados

    @ultimos_resultados.setter
    def ultimos_resultados(self, valor: Optional[List[Dict[str, Any]]]) -> None:
        self._ultimos_resultados = valor

    @property
    def timer_ocultar_resultados(self) -> Optional[Any]:
        return self._timer_ocultar_resultados

    @timer_ocultar_resultados.setter
    def timer_ocultar_resultados(self, valor: Optional[Any]) -> None:
        self._timer_ocultar_resultados = valor

    def limpiar_imagenes(self) -> None:
        """Los cuatro campos de tarjetas vuelven al estado de arranque.

        La espera de temática se queda donde está: ocultar el panel y cerrar la
        pregunta del fondo son dos decisiones distintas.
        """
        self._resultados_visuales = None
        self._imagenes_vistas = set()
        self._ultima_query_imagenes = None
        self._intencion_imagenes = None


def crear_sesion_resultados() -> PuertoSesionResultados:
    """El almacén vacío, listo para que lo reparta el núcleo."""
    return SesionResultados()
