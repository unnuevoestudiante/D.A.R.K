"""Fábrica del puente de overlay: el único lugar que conoce la implementación.

`crear_bridge()` toma por defecto los valores de `overlay/config.py` (y por
tanto las variables `OVERLAY_*` del entorno); un llamador puede pisar
cualquiera con kwargs, y las pruebas levantan el puente en puertos efímeros sin
tocar globales. Otro backend de interfaz (otra UI, otro transporte) se enchufa
aquí y ningún consumidor cambia.
"""
from __future__ import annotations

from typing import Callable

from . import config
from contratos.overlay import PuertoOverlay

# Claves de configuración que se traducen a argumentos del bridge.
_CLAVES_BRIDGE = ("host", "port", "http_port", "escritorio_vigilia_seg")


def crear_bridge(
    on_message: Callable[[str, str | None], None] | None = None,
    initial_state: str = "idle",
    **ajustes,
) -> PuertoOverlay:
    """Levanta el puente con `ajustes` pisando la config.

    `on_message` recibe el texto que escribe el usuario (campo seguro del
    bloqueo, caja de texto, modal de archivos) y la IP de quien lo envió: el
    puente escucha en 0.0.0.0 —tele y móvil también entran—, así que el que
    reciba el mensaje necesita saber de dónde viene para poder decidir.
    `initial_state` es el estado que se publica al primer cliente que conecta:
    el núcleo arranca en "lock".
    """
    desconocidas = set(ajustes) - set(_CLAVES_BRIDGE)
    if desconocidas:
        raise ValueError(
            f"ajustes de overlay no reconocidos: {sorted(desconocidas)}"
        )

    kwargs = {clave: getattr(config, clave.upper()) for clave in _CLAVES_BRIDGE}
    kwargs.update(ajustes)

    from modulos.dark_overlay_bridge import OverlayBridge

    return OverlayBridge(on_message=on_message, initial_state=initial_state,
                         **kwargs)
