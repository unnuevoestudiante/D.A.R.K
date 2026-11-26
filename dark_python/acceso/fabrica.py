"""Fábrica de backends de acceso: el único lugar que conoce implementaciones.

`crear_gate()` toma por defecto los valores de `acceso/config.py` (y por tanto
las variables `ACCESO_*` del entorno); un llamador concreto puede pisar
cualquiera pasando kwargs, y las pruebas inyectan tiempos cortos sin tocar
globales. Un backend futuro (saludo gestual de manos, otro sensor) se enchufa
aquí y ningún consumidor —núcleo, fachada, pruebas— cambia.

Y `crear_servicio_camara()` es el único sitio que nombra `VisionService`. La
cámara del PC es una y no se puede abrir dos veces, así que desde la Fase A de
la línea gestual el núcleo es su dueño: la construye una vez y la reparte entre
el gate facial y el motor gestual, que se suscriben cada uno a su ritmo. El
índice del dispositivo sigue siendo una decisión de acceso (`ACCESO_CAMERA_INDEX`)
porque acceso es el consumidor que no puede vivir sin cámara; si eso incomoda,
mover la clave es cambiar una línea de esta fábrica.
"""
from __future__ import annotations

from typing import Callable

from . import config
from contratos.acceso import PuertoAcceso

MOTORES = ("facial",)

# Claves de configuración que se traducen a argumentos del gate.
_CLAVES_GATE = ("camera_index", "threshold", "idle_fps",
                "ausencia_seg", "watch_arm_seg")


def crear_servicio_camara(camera_index: int | None = None, **modo):
    """El `VisionService` único del PC, sin abrir todavía la cámara.

    No se inicia aquí: cada consumidor llama a `iniciar()` y el servicio abre el
    dispositivo solo mientras quede alguien pidiendo fps. Quien crea el servicio
    es quien lo detiene —`AccessGate` lo sabe por eso guarda `_servicio_propio`.

    El modo de captura (`ancho`, `alto`, `fps`, `codificador`) sale de
    `config.CAMARA_*` y se puede pisar con kwargs; son pedidos, no garantías: el
    driver devuelve lo que soporta y el servicio lo registra al abrir.
    """
    from herramientas.vision import VisionService

    indice = config.CAMERA_INDEX if camera_index is None else camera_index
    pedido = {
        "ancho": config.CAMARA_ANCHO,
        "alto": config.CAMARA_ALTO,
        "fps": config.CAMARA_FPS,
        "codificador": config.CAMARA_CODIFICADOR,
    }
    pedido.update(modo)
    return VisionService(indice, **pedido)


def crear_gate(
    motor: str | None = None,
    on_granted: Callable[[str], None] | None = None,
    on_locked: Callable[[str], None] | None = None,
    servicio=None,
    presencia_manos: Callable[[], float] | None = None,
    **ajustes,
) -> PuertoAcceso:
    """Levanta el gate del motor pedido con `ajustes` pisando la config.

    `servicio`: la cámara compartida creada por el núcleo. Con None, el gate se
    monta la suya propia con `camera_index` y es él quien la cierra al detenerse.

    `presencia_manos`: función sin argumentos que devuelve el monotonic de la
    última mano vista (el motor gestual). Con ella, las manos a la vista cuentan
    como presencia y gesticular tapándose la cara no rebloquea por ausencia.

    Acepta también `boot_timeout`, que no es del gate sino del hilo de
    arranque: se ignora aquí y lo consume `FachadaAcceso`.
    """
    motor = config.MOTOR if motor is None else motor
    if motor not in MOTORES:
        raise ValueError(
            f"motor de acceso desconocido: {motor!r} (opciones: {MOTORES})"
        )
    ajustes.pop("boot_timeout", None)
    desconocidas = set(ajustes) - set(_CLAVES_GATE)
    if desconocidas:
        raise ValueError(
            f"ajustes de acceso no reconocidos: {sorted(desconocidas)}"
        )

    kwargs = {clave: getattr(config, clave.upper()) for clave in _CLAVES_GATE}
    kwargs.update(ajustes)
    kwargs.update(on_granted=on_granted, on_locked=on_locked,
                  servicio=servicio, presencia_manos=presencia_manos)
    # Teclado y mouse cuentan como presencia (acceso/entrada.py).
    from acceso.entrada import ultima_entrada

    kwargs.setdefault("presencia_teclado", ultima_entrada)

    from herramientas.dark_acceso import AccessGate

    return AccessGate(**kwargs)
