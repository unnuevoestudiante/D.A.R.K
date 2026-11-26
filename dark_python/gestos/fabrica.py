"""Fábrica de gestos: el único sitio que nombra las implementaciones.

`crear_motor()` levanta el motor gestual y `crear_canal()` el puente WebSocket
hacia el overlay. Nadie más —ni el núcleo, ni la fachada, ni las pruebas de
integración— debe importar `herramientas.gestos` ni
`herramientas.dark_gestos_canal`: así lo prueba `tests/test_gestos_fachada.py`.

Un motor futuro (otro detector, otro sensor, la tele del salón) implementa
`contratos/gestos.py` y se enchufa aquí; la fachada y el núcleo no cambian una
línea.

El import del motor es perezoso a propósito: `herramientas/gestos.py` tira de
cv2, numpy, psutil y MediaPipe al importarse. Si esa dependencia falta,
`crear_motor()` lanza `ImportError` y es la fachada quien decide degradar, no
que el núcleo muera al arrancar.
"""
from __future__ import annotations

import threading

from . import config
from contratos.gestos import PuertoGestos

# Claves de configuración que se traducen a argumentos del canal.
_CLAVES_CANAL = ("host", "port")

# Los loggers por los que hablan las implementaciones. Viven aquí, junto a los
# nombres de los módulos: la fachada necesita enchufarles un fichero y para eso
# no tiene por qué saber cómo se llama nadie.
LOGGERS = ("herramientas.gestos", "herramientas.dark_gestos_canal")


def crear_motor(
    servicio,
    acceso: threading.Event | None = None,
    *,
    ver: bool = False,
) -> PuertoGestos:
    """Motor gestual sobre la cámara compartida `servicio`.

    `servicio` es el `VisionService` único del PC: lo crea el núcleo (por la
    fábrica de acceso) y lo comparte con el gate facial, porque la cámara no se
    puede abrir dos veces.

    `acceso` es el `threading.Event` que el gate facial setea al conceder y
    limpia al retirar. Mientras no esté activo, el motor se queda en APAGADO y
    pide 0 fps: la cámara se libera sola. Sin `acceso` el motor responde siempre
    (modo banco de pruebas).

    `ver` levanta el dibujo de la instantánea del detector; en producción cuesta
    y no lo mira nadie.
    """
    from herramientas.gestos import GestureEngine

    return GestureEngine(servicio, acceso=acceso, debug=ver)


def crear_canal(**ajustes):
    """Canal WebSocket local del motor al overlay, con `ajustes` pisando la config.

    Sin ajustes: `gestos/config.py` (variables `GESTOS_*`). Las pruebas levantan
    el canal en un puerto efímero pasando `port=0` sin tocar globales.
    """
    desconocidas = set(ajustes) - set(_CLAVES_CANAL)
    if desconocidas:
        raise ValueError(
            f"ajustes de gestos no reconocidos: {sorted(desconocidas)}"
        )

    kwargs = {clave: getattr(config, clave.upper()) for clave in _CLAVES_CANAL}
    kwargs.update(ajustes)

    from herramientas.dark_gestos_canal import GestosCanal

    return GestosCanal(**kwargs)
