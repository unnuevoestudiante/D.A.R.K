"""Fachada de gestos: compone motor + canal y decide qué hacer si algo falla.

El núcleo no sabe qué clase implementa el motor ni quién se lo escucha. Le pasa
la cámara compartida y el Event del acceso, y le pide `iniciar()` / `detener()`.

Orden de arranque, y por qué es este:

  1. se construye el motor y el canal,
  2. `canal.conectar_motor(motor)` pisa `on_evento` antes de que el motor emita
     nada, así no se pierde ni un `gestos_on`,
  3. el canal abre su WebSocket *antes* de arrancar el hilo del motor: si el
     puerto está ocupado, no nos quedamos con un motor gesticulando para nadie,
  4. y por último `motor.iniciar()`.

Degradar, nunca lanzar: si falta MediaPipe, no hay cámara, el modelo no está en
disco o el puerto no se abre, la fachada guarda el error, avisa por log y deja
los gestos apagados. El resto de D.A.R.K. sigue igual —es la misma política que
`FachadaAcceso` aplica cuando la verificación facial no arranca— y por eso
`ultima_mano_t` responde 0.0 en vez de fallar cuando no hay motor: el gate facial
lo consulta en cada cuadro.

`iniciar()` además enchufa `gestos/config.py:LOG` a los loggers del subsistema,
para que los eventos de una sesión real queden en disco y no sólo en la consola,
y enciende la lectura de 1 Hz según `config.LECTURA` — esa línea es el único
instrumento que queda después de la sesión, así que no puede depender de que el
overlay pida el andamio de video.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Callable

from . import config, fabrica

LOGGER = logging.getLogger(__name__)

# Lo que puede fallar al levantar el subsistema, todo esperado: ImportError si
# faltan cv2/MediaPipe, OSError si la cámara no existe, RuntimeError si el canal
# no arranca o el puerto está ocupado, ValueError si el host no es local.
FALLOS_DE_ARRANQUE = (ImportError, OSError, RuntimeError, ValueError)

_FORMATO_LOG = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s: %(message)s"
)


def enchufar_log(ruta: str) -> int:
    """Escribe los eventos del motor y del canal en `ruta`. Devuelve cuántos
    loggers se tocaron.

    Hace falta porque dentro del núcleo no hay ningún FileHandler: el que hay
    vive en el `__main__` de `herramientas/gestos.py` (flag `--log`) y sólo se
    configura cuando el motor corre suelto. Sin esto, `gestos_on` o
    `agarre_inicio` de una sesión real se van a la consola y se pierden al
    cerrarla, que es exactamente el agujero por el que no se puede calibrar el
    embrague mirando atrás.

    Idempotente: `iniciar()` se puede volver a llamar tras `detener()`, y un
    handler duplicado escribiría cada evento dos veces. Se enchufa también al
    logger de esta fachada, porque el aviso de "Gestos no disponibles" es justo
    el que quieres encontrar en el fichero cuando algo no arrancó.

    Y sube el nivel de esos loggers a INFO, que es la otra mitad del arreglo:
    `herramientas/gestos.py` emite cada evento con `LOGGER.info` y el núcleo
    nunca llama a `basicConfig`, así que el root se queda en WARNING y filtra el
    `gestos_on` antes de que llegue al fichero. Con el handler puesto y el nivel
    a media, el log existiría y estaría vacío.
    """
    if not ruta:
        return 0
    absoluto = os.path.abspath(ruta)
    tocados = 0
    for nombre in (*fabrica.LOGGERS, LOGGER.name):
        logger = logging.getLogger(nombre)
        if not logger.level or logger.level > logging.INFO:
            logger.setLevel(logging.INFO)
        if any(
            isinstance(m, logging.FileHandler)
            and getattr(m, "baseFilename", "") == absoluto
            for m in logger.handlers
        ):
            continue
        try:
            manejador = logging.FileHandler(ruta, encoding="utf-8")
        except OSError as error:
            LOGGER.warning("El log de gestos no se abre en %s: %s", ruta, error)
            return tocados
        manejador.setFormatter(_FORMATO_LOG)
        logger.addHandler(manejador)
        tocados += 1
    return tocados


class FachadaGestos:
    """Motor + canal detrás de una sola superficie. No implementa un puerto:
    es la composición de dos (`contratos/gestos.py` es el del motor)."""

    def __init__(
        self,
        servicio,
        acceso: threading.Event | None = None,
        *,
        crear_motor: Callable | None = None,
        crear_canal: Callable | None = None,
        ver: bool = False,
    ) -> None:
        self._servicio = servicio
        self._acceso = acceso
        self._crear_motor = crear_motor if crear_motor is not None else fabrica.crear_motor
        self._crear_canal = crear_canal if crear_canal is not None else fabrica.crear_canal
        self._ver = ver

        self.motor = None
        self.canal = None
        self.error: Exception | None = None
        self._arrancado = False

    # ------------------------------------------------------------------ API
    @property
    def activos(self) -> bool:
        """Hay motor y canal en marcha. Con False, la interfaz no va a recibir
        ni un evento: mejor saberlo que pintar una mano fantasma."""
        return self.motor is not None and self.canal is not None

    @property
    def estado(self) -> str | None:
        """Literal del motor ("APAGADO"/"ARMADO"/"AGARRE"), o None si no hay.
        No es el estado de la máquina: `activos` dice si el subsistema vive."""
        return self.motor.estado if self.motor is not None else None

    @property
    def ultima_mano_t(self) -> float:
        """Monotonic de la última mano vista; 0.0 si no hay motor o nunca hubo
        manos. Es `presencia_manos` para el gate facial, y se consulta por
        cuadro: no puede lanzar nada."""
        if self.motor is None:
            return 0.0
        return float(self.motor.ultima_mano_t)

    @property
    def clientes(self) -> int:
        """Overlays conectados al canal. 0 significa que nadie escucha, no que
        los gestos estén apagados."""
        return self.canal.clientes if self.canal is not None else 0

    def iniciar(self) -> bool:
        """Levanta el subsistema. True si quedó en marcha; False si degradó,
        con el motivo en `error`. Idempotente: no abre dos canales."""
        if self._arrancado:
            return self.activos
        self._arrancado = True
        # Antes de intentar nada: si el arranque falla, el aviso también tiene
        # que quedar escrito en el fichero.
        enchufar_log(config.LOG)

        canal = None
        try:
            motor = self._crear_motor(self._servicio, self._acceso, ver=self._ver)
            # La lectura a disco la decide el despliegue, no la interfaz: mientras
            # la pidió el overlay, cualquier conexión sin el andamio de calibración
            # la apagaba y el log se quedaba ciego — cuatro días del 29-oct al
            # 2-nov sin una sola línea con manos.
            motor.fijar_lectura(config.LECTURA)
            canal = self._crear_canal()
            canal.conectar_motor(motor)
            canal.iniciar()
            motor.iniciar()
        except FALLOS_DE_ARRANQUE as error:
            self.error = error
            if canal is not None:
                try:
                    canal.detener()
                except Exception:
                    LOGGER.debug("El canal de gestos no se pudo cerrar tras el fallo.")
            LOGGER.warning("Gestos no disponibles: %s", error)
            return False

        self.motor = motor
        self.canal = canal
        LOGGER.info(
            "Gestos en marcha: canal en ws://%s:%s, motor en %s.",
            config.HOST, self.canal.port, self.motor.estado,
        )
        return True

    def detener(self, timeout: float = 5.0) -> None:
        """Para el hilo del motor y luego el canal. Pensado para atexit: ningún
        fallo aquí puede interrumpir el cierre del resto del núcleo."""
        self._arrancado = False
        for nombre, objeto in (("motor", self.motor), ("canal", self.canal)):
            if objeto is None:
                continue
            try:
                objeto.detener(timeout=timeout)
            except Exception as error:
                LOGGER.warning("El %s de gestos no se detuvo limpio: %s", nombre, error)
        self.motor = self.canal = None
