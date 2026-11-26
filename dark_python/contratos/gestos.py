"""Contrato del subsistema de GESTOS: puerto del motor gestual.

Qué es
------
El motor traduce manos en *intención* —arma, agarra, mueve, escala, gira, apaga—
y entrega eventos. No conoce la interfaz, no dibuja nada y no decide qué objeto
se puede agarrar: eso lo hace el reducer del frontend
(`dark_frontend/src/lib/gestos/gestos-logica.ts`) sobre lo que este puerto emite.

Qué consume quién (audit del 25-oct-2026, al cerrar la Fase A de la línea
gestual; cada firma es la que el llamador usa de verdad, no un deseo)
--------------------------------------------------------------------
  PuertoGestos (implementado por herramientas/gestos.py, `GestureEngine`; el
  único sitio que lo construye es `gestos/fabrica.py`):
      * herramientas/dark_gestos_canal.py  `conectar_motor()` pisa
            `motor.on_evento` con su `emitir` y, en el sentido inverso, llama
            `motor.fijar_sostiene(bool)` cuando el overlay avisa de que está
            sujetando algo, `motor.fijar_video(bool)` cuando pide ver el cuadro
            (calibración), `motor.fijar_lectura(bool)` cuando alguien cambia en
            caliente la línea a disco (por defecto la enciende
            `gestos/config.py:LECTURA` desde la fachada) y `motor.fijar_agarre(ids)`
            cuando una mano quieta ha entrado en la caja de un objeto. Por eso
            `on_evento` es un atributo escribible del puerto y no un parámetro del
            constructor.
      * gestos/fachada.py                 `iniciar()` y `detener(timeout)`, y en
            medio `fijar_lectura(config.LECTURA)`: la fachada es la única que
            decide el orden con el canal.
      * herramientas/gestos.py:529-534    el worker consulta el Event de acceso
            que se le pasó en la construcción: sin acceso concedido fija 0 fps y
            la cámara se libera sola (`VisionService` solo abre el dispositivo
            mientras alguien pide fps). No es un método del puerto: es una
            condición de arranque que la fábrica inyecta.
      * dark_nucleo.py (`_crear_gate_facial`)  `ultima_mano_t` se pasa al gate
            facial como `presencia_manos`, para que tener las manos a la vista
            cuente como presencia y gesticular tapándose la cara no rebloquee.

Emisión (la carga de cada evento, medida en herramientas/gestos.py:38-46)
------------------------------------------------------------------------
`gestos_on` con `motivo` y `aspecto`, `gestos_off`, `manos` (por mano: `id`,
`x`, `y`, `cerrada`, `apertura`, `quietud` (s continuos quieta) y `candida` (puede
volver a coger por permanencia); desde el 26-oct también `forma` (`puno` | `pinza` |
`C` | `abierta`, un ESTADO confirmado como `cerrada`, nunca un instante), `pinza`
(pulgar↔índice en tamaños de palma, -1 = sin dato) y `giro` (ángulo del eje de la mano
en el plano de la imagen, grados con signo)), `dedo` (la
apertura del dedo MÁS abierto, la que decide `cerrada`) y `vel` (palmas por segundo,
la que decide `quietud`), que viajan como números para que el andamio los pinte sin
recalcular nada aquí. `agarre_inicio` / `agarre_cambio` con
`manos`, `n`, `ancla` y `origen` (`puno` | `permanencia` | `pinza`: dice si lo cogió
un puño, la interfaz o un pellizco, y con ello quién manda sobre la suelta),
`transformacion` con `n`, `dx`, `dy`, `escala` y `giro`,
`agarre_fin` (con `motivo` `quietud` | `abierto` | `interfaz`, y sin él cuando la
máquina lo suelta porque la mano caducó), `cierre_progreso` y `cierre_cancelado`. Las
coordenadas de `manos`
y `ancla` son 0..1 sobre el cuadro YA ESPEJADO; `dx`/`dy` van en alturas de
cámara, `giro` en radianes (positivo = horario en pantalla) y `escala` es
adimensional. Con una mano, la escala y el giro salen de la propia mano —cuánto se ha
abierto y cuánto ha girado DESDE el instante de coger, como delta, no como valor
absoluto—; con dos salen de su separación y de su ángulo. En un agarre de pellizco el
canal de la apertura está apagado: abrir es la suelta, no puede además ampliar. Y
`cuadro` (`imagen` como data-URL JPEG, `ancho`, `alto`, `aspecto`) solo mientras
la interfaz tenga pedido el vídeo: es el cuadro espejado que el motor está
procesando, reducido, para calibrar la correspondencia cámara↔pantalla.

Estados (valores de `estado`, literales en gestos.py)
-----------------------------------------------------
APAGADO → ARMADO → AGARRE → ARMADO → … APAGADO. `AGARRE` con una o dos manos.
Son comparaciones por igualdad de cadena: se conservan los literales exactos
porque el worker los usa como clave de sus histogramas de CPU y fps.

Un contrato nunca importa un motor concreto: MediaPipe, OpenCV y psutil viven
detrás de `gestos/fabrica.py`. El núcleo solo importa este puerto y la fachada.

Solo stdlib.
"""
from enum import Enum
from typing import Callable, Optional, Protocol, runtime_checkable


class EstadosGestos(str, Enum):
    """Estados de la máquina gestual. Valores = los literales de
    herramientas/gestos.py (`APAGADO`, `ARMADO`, `AGARRE`).

    Mezcla con `str`, así que `"AGARRE" == EstadosGestos.AGARRE` es True y las
    comparaciones del worker siguen valiendo sin convertir nada. Ojo con el
    formato: en Python 3.12 `str(EstadosGestos.AGARRE)` da
    "EstadosGestos.AGARRE", no "AGARRE" — para pintar, `.value`. El worker usa
    estos literales como clave de sus histogramas de CPU y fps, y
    `tests/test_gestos_fachada.py` ata esta tabla a las constantes del motor.
    """

    APAGADO = "APAGADO"
    ARMADO = "ARMADO"
    AGARRE = "AGARRE"


@runtime_checkable
class PuertoGestos(Protocol):
    """Puerto del motor que convierte manos en eventos de intención.

    Implementación actual: herramientas/gestos.py (`GestureEngine`, MediaPipe
    HandLandmarker en su propio hilo). Otro motor futuro (otro detector, otro
    sensor) implementa esto y se enchufa en `gestos/fabrica.py` sin tocar al
    núcleo ni a la fachada.
    """

    on_evento: Optional[Callable[[dict], None]]
    """Salida de eventos. La conecta el canal (`conectar_motor`) pisándola, así
    que el motor no exige conocer a nadie: se le asigna o emite a la nada."""

    @property
    def estado(self) -> str:
        """Estado actual de la máquina, lectura no bloqueante. Literal de
        `EstadosGestos`."""
        ...

    @property
    def ultima_mano_t(self) -> float:
        """`time.monotonic()` de la última mano confirmada a la vista, en
        cualquier estado; 0.0 si nunca se vio ninguna. Lo consume el gate
        facial como `presencia_manos`."""
        ...

    def iniciar(self) -> None:
        """Arranca el hilo del motor. Idempotente: si ya corre, no-op. Inicia
        también el servicio de cámara compartido; a partir de ahí el Event de
        acceso decide si gasta fps o no."""
        ...

    def detener(self, timeout: float = 5.0) -> None:
        """Detiene el hilo y libera el detector. Lanza TimeoutError si el hilo
        no muere a tiempo."""
        ...

    def fijar_sostiene(self, valor: bool) -> None:
        """La interfaz avisa de si el agarre vigente sujeta un objeto. Con True
        un puño quieto NO cierra los gestos (sería sostener algo quieto); sin
        llamada, el puño apaga siempre. Se puede invocar desde otro hilo."""
        ...

    def fijar_video(self, valor: bool) -> None:
        """La interfaz pide que se le reenvíe el cuadro que está viendo el motor,
        como evento `cuadro`. Solo andamio de calibración: nada lo pide en la
        sesión normal, y con False deja de emitir en el acto. Barato a propósito
        (ancho reducido, ~12 fps, sin registrar en el log). Se puede invocar
        desde otro hilo."""
        ...

    def fijar_lectura(self, valor: bool) -> None:
        """Que se registre en el log lo que el motor está leyendo de las manos:
        una línea cada `LECTURA_CADA` segundos con los mismos números del evento
        `manos` —más `dedo`, `vel` y las manos todavía pendientes de confirmar,
        que el cable no publica—, el estado de la máquina y la última
        transformación. Con False calla en el acto. Mira y no toca: no cambia
        ninguna decisión. Se puede invocar desde otro hilo.

        Es instrumento, no andamio: lo enciende el despliegue
        (`gestos/config.py:LECTURA`, True por defecto) a través de la fachada en
        `iniciar()`. El mensaje `{tipo:"lectura"}` del canal queda para cambiarlo
        en caliente, sin relanzar el núcleo.
        """
        ...

    def fijar_agarre(self, ids: list[int]) -> None:
        """La interfaz reclama el agarre de estas manos SIN puño (permanencia),
        o lo suelta con la lista vacía.

        Existe porque seleccionar por permanencia exige saber dónde está cada
        objeto, y eso solo lo sabe la interfaz (`data-agarrable`). El motor pone
        la evidencia que falta en el evento `manos` —`quietud` (segundos quieto)
        y `candida` (puede volver a coger)— y aquí recibe los ids. Con un grupo
        así, la suelta la decide el motor: todas las manos quietas
        `T_QUIETUD_SUELTA` y objeto ya trasladado. Se puede invocar desde otro
        hilo: deja la petición y la consume el worker."""
        ...


__all__ = ["EstadosGestos", "PuertoGestos"]
