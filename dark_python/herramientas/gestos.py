"""Motor gestual de D.A.R.K (Fase 1): manos -> eventos de intención, sin interfaz.

Qué hace
--------
Lee cuadros del ``VisionService`` (suscriptor "gestos"), detecta hasta dos
manos con MediaPipe y las convierte en EVENTOS de intención. No sabe quién los
recibe: hoy van al log y a un callback opcional; en la Fase 2 los recibirá el
puente hacia el overlay y, más adelante, HollOSW.

Flujo (todo en un hilo)
-----------------------
    cuadro -> espejo -> HandLandmarker(VIDEO, 2 manos) -> rasgos por mano
           -> identidad (mano 1 / mano 2 por cercanía, no por izquierda/derecha)
           -> máquina de estados con histéresis -> eventos

Estados
-------
    APAGADO : las manos se ignoran. Solo se sondea a ~8 fps buscando el embrague.
    ARMADO  : modo gestual activo (30 fps). Se esperan agarres.
    AGARRE  : 1 o 2 manos cerradas "sujetan" algo. Se emiten transformaciones.

    APAGADO --palma abierta quieta 0,5 s--> ARMADO
    ARMADO  --mano abierta que se cierra--> AGARRE
    AGARRE  --todas las manos se abren----> ARMADO
    ARMADO/AGARRE --UN puño cerrado y quieto 3 s--> APAGADO
    ARMADO  --sin manos / inactividad / acceso retirado--> APAGADO

    Cierre por puño: cuenta solo si hay UNA mano cerrada (con dos puños se está
    manipulando) y se mantiene quieta (RADIO_PUNO_PALMAS). Moverla, abrirla o
    perderla reinicia la cuenta. Tras T_PUNO_AVISO s de quietud se emite
    ``cierre_progreso`` para que la interfaz dibuje un anillo; si la cuenta se
    interrumpe después de avisar, se emite ``cierre_cancelado``.
    Si la interfaz avisa con ``fijar_sostiene(True)`` que el agarre sujeta un
    objeto, el puño no cuenta: solo una mano vacía cierra.

Eventos (diccionarios con la clave "evento")
--------------------------------------------
    gestos_on      {motivo, aspecto}
    gestos_off     {motivo}                  puno | sin_manos | inactividad | acceso
    manos          {manos:[{id,x,y,cerrada,apertura,quietud,candida,forma,pinza,giro,dedo,vel}]}  cada cuadro, callback
    agarre_inicio  {manos:[ids], n, ancla:[x,y], origen}   puno | permanencia | pinza
    agarre_cambio  {manos:[ids], n, ancla:[x,y], origen}   pasó de 1 a 2 manos o al revés
    transformacion {n, dx, dy, escala, giro}               relativa al último inicio/cambio
    agarre_fin     {}                              {motivo: quietud|abierto|interfaz} si lo causó una regla
    cierre_progreso {progreso}                     0..1 hasta el cierre, solo callback
    cierre_cancelado {}                            se interrumpió tras avisar, solo callback

    x,y de ``manos`` y ``ancla`` son 0..1 sobre el cuadro ESPEJADO (derecha del
    usuario = derecha de la pantalla). dx,dy están en "alturas de cámara" (1.0 =
    la altura del cuadro); giro en radianes (positivo = horario en pantalla);
    escala es adimensional. Con dos manos, escala y giro salen de SU separación y
    SU ángulo; con una, de cuánto se ha abierto y cuánto ha girado esa mano, siempre
    como DELTA tomado en el instante del último agarre (``_baseline``).

    ``dedo`` es la apertura del dedo MÁS abierto (con ella ``DEDO_CIERRA``/
    ``DEDO_ABRE`` deciden ``cerrada``), ``vel`` la velocidad en palmas por segundo
    (con ella ``VEL_QUIETUD`` decide ``quietud``) y ``pinza``/``giro`` las dos
    medidas que clasifican la ``forma``. Viajan solo como números: lo que el motor
    YA decidió no se recalcula en la interfaz.

Todos los umbrales son HIPÓTESIS iniciales: se calibran con ``--ver``, con el
panel de lectura del navegador y con el log (ver ``_principal`` y
``fijar_lectura``). Ejecutar como módulo desde la raíz del proyecto:

    python -m <paquete>.gestos --ver [--lectura]
"""
from __future__ import annotations

import base64
import logging
import math
import statistics
import threading
import time
import urllib.request
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import psutil
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from herramientas.vision import FPS_CONTINUO, VisionService, _to_mp

LOGGER = logging.getLogger(__name__)

# --- modelo -----------------------------------------------------------------
HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
# Se asume que este archivo vive junto a dark_acceso.py (mismo nivel de carpetas)
# para reutilizar la carpeta donde ya está face_landmarker.task.
_REFERENCE_DIR = Path(__file__).resolve().parents[2] / "Reconocimiento Facial"
_HAND_MODEL_PATH = _REFERENCE_DIR / "hand_landmarker.task"

# --- estados ----------------------------------------------------------------
APAGADO = "APAGADO"
ARMADO = "ARMADO"
AGARRE = "AGARRE"

# --- ritmo ------------------------------------------------------------------
FPS_SONDEO = 8.0            # buscando el embrague
FPS_ACTIVO = FPS_CONTINUO   # ARMADO y AGARRE

# --- forma de la mano -------------------------------------------------------
# Extensión de un dedo = dist(punta, muñeca) / dist(nudillo, muñeca).
R_CERRADO = 1.0             # dedo doblado
R_ABIERTO = 1.7             # dedo estirado
# "Cerrada" se decide por el dedo MÁS abierto (dedo_max), no por la media: un
# pellizco o una pose con dos dedos estirados tienen media baja y oscilante
# (0,2 <-> 0,5 con la misma pose) pero siempre un dedo alto. Un puño: ~0,00.
DEDO_CIERRA = 0.20          # dedo más abierto por debajo => mano cerrada
DEDO_ABRE = 0.40            # por encima => mano abierta (histéresis estrecha)
APERTURA_PALMA = 0.80       # palma abierta para el embrague
VERTICAL_MAX_GRADOS = 50.0  # desviación máxima de los dedos respecto a "arriba"
CONFIRMA_FRAMES = 2         # cuadros seguidos para cambiar abierta<->cerrada
# --- forma: pinza y C (añadidas el 26-oct, UMBRALES SIN CALIBRAR) ------------
# Las tres cantidades se sacan de los 21 puntos que ya llega a dar, así que no
# cuestan ni un cuadro más: a ~19,5 cuadros/s lo que cuesta es otro umbral que
# hay que afinar con las manos delante. Se ven en el banco (`--ver`) como
# `pz=` (pulgar↔índice en tamaños de palma), `in=` (índice estirado) y `gi=`.
PINZA_MAX = 0.45            # punta pulgar↔índice por debajo de esto es un pellizco
C_SPAN_MIN = 0.90           # hueco pulgar↔índice mínimo para que la mano abra una C
C_INDICE_MAX = 0.60         # con el índice del todo estirado es palma abierta, no C
# Un dedo "sin estirar del todo" es lo que separa la C de la palma plana: en la C
# el índice está curvado hacia dentro y aun así no llega al pulgar.

# --- embrague y cierre ------------------------------------------------------
T_EMBRAGUE = 0.5            # s con la palma abierta, vertical y quieta
VEL_MAX_EMBRAGUE = 1.5      # palmas/s: más rápido es un saludo, no un embrague
REARME_SEG = 1.0            # tras apagar, no se puede volver a armar antes
T_PUNO_CIERRA = 3.0         # s con UN puño cerrado y quieto para apagar los gestos
T_PUNO_AVISO = 1.0          # s de quietud antes de empezar a avisar (cierre_progreso)
APERTURA_PUNO_INICIA = 0.15 # el CIERRE exige que hasta el dedo MÁS abierto esté doblado (puño real: ~0.00)
APERTURA_PUNO_SIGUE = 0.25  # una vez contando, tolera esto antes de reiniciar (el dato oscila)
RADIO_PUNO_PALMAS = 0.8     # cuánto puede moverse el puño (en tamaños de palma) sin reiniciar
PASO_AVISO = 0.05           # el progreso se emite al cambiar al menos esto (evita 30 eventos/s)
SIN_MANOS_APAGA = 3.0       # s sin ver manos en ARMADO
INACTIVIDAD_APAGA = 20.0    # s en ARMADO sin ningún agarre

# --- permanencia y suelta (el agarre sin puño) -------------------------------
# Seleccionar por permanencia necesita algo que este motor no sabe: DÓNDE está
# cada objeto. La caja la tiene la interfaz (`data-agarrable`), así que ella
# reclama el agarre con `fijar_agarre` y de aquí solo sale la evidencia que le
# falta a ese criterio: cuántos segundos lleva quieta una mano (`quietud`).
VEL_QUIETUD = 0.6           # palmas/s: por debajo de esto la mano cuenta por quieta
T_QUIETUD_SUELTA = 0.30     # s quietas TODAS las manos del grupo para soltar
MIN_TRASLADO = 0.25         # palmas recorridas antes de que la quietud pueda soltar
# `MIN_TRASLADO` no es un adorno: el agarre se reclama con la mano quieta, así
# que en el instante de coger, `quietud` ya vale más que el umbral de suelta. Sin
# recorrido mínimo, la pausa natural entre coger y abrir las dos manos para
# escalar soltaría el objeto antes de empezar.
GRACIA_CAMBIO = 0.60        # s tras entrar una mano en el grupo: la suelta no cuenta
T_ESPERA_UNION = 1.00       # s que se le dan a la segunda mano antes de soltar igual

# --- manos fantasma (falsos positivos del detector) -------------------------
# MediaPipe a veces "ve" una mano sobre la cara o se queda enganchado donde
# estuvo la mano. Tres defensas, de la más barata a la más cara:
DETECCION_MIN = 0.7         # confianza del detector de palmas (MediaPipe usa 0.5)
PRESENCIA_MIN = 0.6         # confianza de que la mano sigue ahí (MediaPipe usa 0.5)
RASTREO_MIN = 0.6           # confianza del rastreo entre cuadros (MediaPipe usa 0.5)
PALMA_MIN = 0.04            # tamaño de palma plausible, en alturas de cámara
PALMA_MAX = 0.45
CONFIRMA_MANO_SEG = 0.2     # una mano nueva no cuenta hasta verse este tiempo seguida

# --- identidad de manos -----------------------------------------------------
GRACIA_MANO = 0.25          # s que una mano perdida conserva su identidad
GRACIA_AGARRE = 0.6         # s, para las manos sujetas en AGARRE (a 30 fps: ~18)
HUECO_DT_MAX = 0.1          # s: tras perder la mano, la velocidad se mide sobre este dt como mucho
MAX_SALTO_PALMAS = 4.0      # salto máximo entre cuadros para ser "la misma mano"

# --- suavizado (One Euro; unidades: alturas de cámara) ----------------------
MIN_CUTOFF_POS = 1.5
BETA_POS = 8.0
MIN_CUTOFF_DIST = 1.0
BETA_DIST = 4.0
MIN_CUTOFF_ANG = 1.0
BETA_ANG = 1.0
ESCALA_MIN, ESCALA_MAX = 0.1, 10.0
# Perillas de calibración (17-nov-2026): con 0,8 y división a pelo, abrir la mano
# un tramo cómodo o separar las dos un 50 % más no llegaba al umbral con que el
# frontend abre la zona de especialistas. Subidas las dos; pendientes de medir
# con mano real (el arnés sintético fija la forma de la curva, no el gusto).
APERTURA_A_ESCALA = 1.6     # escala ganada por cada 1,0 de apertura (0 puño, 1 abierta)
GANANCIA_PAR = 1.6          # amplificación del delta de separación: 1 + G*(dist/ref - 1)
# Es un DELTA, no un valor absoluto: la referencia se fija al coger, así que abrir la
# mano amplía lo mismo estés cerca o lejos de la cámara. Un umbral
# absoluto de apertura dependería de la distancia y habría que recalibrarlo por sesión.
# `apertura` es el ÚNICO rasgo que llegaba crudo al clasificador, y por él se iba la
# escala: en el log del 27-oct los tramos de una mano valen 1,00 1,00 0,20 1,00 1,00
# (muestreado a 1 Hz, así que el cuadro malo es todavía más hondo). Filtro como el de
# los demás rasgos, pero con BETA baja a propósito: aquí un cambio súbito es casi
# siempre un artefacto, no una intención, y el OneEuro de posición hace lo contrario
# (sube el corte cuando la mano corre) porque con la posición correr sí es intención.
MIN_CUTOFF_AP = 1.0
BETA_AP = 0.5
DIST_REF_MIN = 0.05         # evita escalas absurdas si las manos arrancan pegadas
# Cuando el par se reclama en el cuadro en que la segunda mano asoma no hay todavía
# tres separaciones de las que sacar mediana, y las tres que llegan a haberlas caen
# en mitad de la transición: la mano viene de lejos. Fijar ahí la referencia dejaba
# el tramo a 0,88 de escala con las manos ya en su sitio (medido: referencia 0,170
# para 0,15 reales). Es un residuo conocido y a propósito: esperar a que las dos
# manos se queden quietas para asentarse se comería el primer medio segundo de un
# estiramiento deliberado, que es la otra cara de la misma queja. `ref_dist=` en la
# línea de 1 Hz existe para medir cuál de las dos duele en la sesión real.

# --- vídeo de calibración (andamio; solo cuando la interfaz lo pide) ---------
VIDEO_FPS = 12.0            # cuadros por segundo reenviados
# El ancho del fondo no compra ni cuesta cuadros por segundo: medido en tres pasadas
# reales del 26-oct, el motor procesa ~19,5 fps con 320, con 640 y con 1280. Lo que
# cambia es el tiempo de worker (2,5 ms aquí, 7,5 ms en 1280), así que se toma el
# punto donde el cuadro se lee sin pagar de más: 640 estira 3× en un panel de 1920
# frente al estirado 6× de los 320 originales, que parecían un mosaico.
VIDEO_ANCHO = 640
VIDEO_CALIDAD = 75

# --- lectura de las manos a disco (instrumento; la enciende el despliegue) -----
# Con ~19,5 cuadros/s una línea por cuadro serían 19 líneas por segundo y el log
# dejaría de leerse. Un hertz basta para calibrar: los umbrales se miden en
# décimas de segundo y la lectura que importa es la del instante en que el motor
# decide, que ya viaja en `agarre_inicio`, `agarre_cambio` y `agarre_fin`.
LECTURA_CADA = 1.0

_CONEXIONES = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (5, 9),
    (9, 10), (10, 11), (11, 12), (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
]


# ---------------------------------------------------------------------------
# Filtro One Euro (Casiez, Roussel y Vogel, CHI 2012)
# ---------------------------------------------------------------------------
class _OneEuro:
    """Pasa-bajos cuyo corte sube con la velocidad: quieto no tiembla, rápido no se retrasa."""

    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float = 1.0) -> None:
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x: float | None = None
        self._raw: float = 0.0
        self._dx = 0.0
        self._t = 0.0

    @staticmethod
    def _alpha(corte: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * corte)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x: float, t: float) -> float:
        if self._x is None:
            self._x, self._raw, self._t = x, x, t
            return x
        dt = max(t - self._t, 1e-3)
        dx = (x - self._raw) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1.0 - a_d) * self._dx
        corte = self.min_cutoff + self.beta * abs(self._dx)
        a = self._alpha(corte, dt)
        self._x = a * x + (1.0 - a) * self._x
        self._raw, self._t = x, t
        return self._x


def _envolver(angulo: float) -> float:
    """Lleva un ángulo al rango [-pi, pi]."""
    return (angulo + math.pi) % (2.0 * math.pi) - math.pi


# ---------------------------------------------------------------------------
# Detección y rasgos
# ---------------------------------------------------------------------------
@dataclass
class _Deteccion:
    ancla: np.ndarray      # centro de la palma, en alturas de cámara
    palma: float           # tamaño de la palma, en alturas de cámara
    apertura: float        # 0 = puño, 1 = mano abierta
    vertical: bool         # dedos apuntando hacia arriba (±VERTICAL_MAX_GRADOS)
    etiqueta: str          # "Left"/"Right" = mano física del usuario (solo informativo)
    puntaje: float         # confianza de la etiqueta izquierda/derecha
    pts: np.ndarray        # 21x2, en alturas de cámara
    motivo: str | None = None   # None = aceptada; si no, por qué se rechazó
    # Apertura del dedo MÁS abierto (0 = los cuatro doblados). Un puño de verdad
    # tiene los cuatro doblados; un pellizco o una mano a medio curvar tienen
    # algún dedo estirado, y entonces la media (``apertura``) engaña.
    dedo_max: float = -1.0      # < 0 = sin dato: se toma ``apertura``
    # Distancia entre punta del pulgar y punta del índice, en tamaños de palma:
    # la evidencia cruda del pellizco y de la C. -1 = sin dato (mano de prueba
    # construida antes de estos campos).
    pinza: float = -1.0
    # Extensión del índice sola (la media de los cuatro dedos no la distingue).
    indice: float = -1.0
    giro: float = 0.0        # ángulo del eje muñeca->nudillo medio, grados

    def __post_init__(self) -> None:
        if self.dedo_max < 0.0:
            self.dedo_max = self.apertura
        if self.indice < 0.0:
            self.indice = self.apertura


def _rasgos(landmarks, ancho: int, alto: int, etiqueta: str, puntaje: float) -> _Deteccion | None:
    # Se divide todo por el alto: x e y quedan en la misma unidad (alturas).
    pts = np.array([(lm.x * ancho / alto, lm.y) for lm in landmarks], dtype=np.float64)
    palma = (
        np.linalg.norm(pts[0] - pts[9]) + np.linalg.norm(pts[5] - pts[17])
    ) / 2.0
    if palma < 1e-3:
        return None
    ancla = pts[[0, 5, 9, 13, 17]].mean(axis=0)

    aperturas = []
    for punta, nudillo in ((8, 5), (12, 9), (16, 13), (20, 17)):
        razon = np.linalg.norm(pts[punta] - pts[0]) / (
            np.linalg.norm(pts[nudillo] - pts[0]) + 1e-9
        )
        aperturas.append(float(np.clip((razon - R_CERRADO) / (R_ABIERTO - R_CERRADO), 0.0, 1.0)))
    apertura = float(np.mean(aperturas))
    dedo_max = float(np.max(aperturas))
    pinza = float(np.linalg.norm(pts[4] - pts[8]) / palma)

    eje = pts[9] - pts[0]
    if -eje[1] > 0:
        grados = math.degrees(math.atan2(abs(eje[0]), -eje[1]))
        vertical = grados <= VERTICAL_MAX_GRADOS
    else:
        vertical = False
    # Con signo: es el giro en el plano de la imagen, y la rotación que se pide
    # es un delta entre dos cuadros. `vertical` mira el valor absoluto; esto no.
    giro = float(math.degrees(math.atan2(eje[0], -eje[1])))
    return _Deteccion(ancla, float(palma), apertura, vertical, etiqueta, puntaje, pts,
                      dedo_max=dedo_max, pinza=pinza, indice=aperturas[0], giro=giro)


def _clasificar_forma(*, cerrada: bool, pinza: float, indice: float) -> str:
    """La forma de una mano, en cuatro estados y sin umbrales absolutos de tamaño.

    El orden importa: `cerrada` es la regla de siempre, así un puño no se reclasifica
    nunca por una vía nueva. Una mano sin `pinza` medida devuelve "abierta" en vez de
    inventársela, y así las manos de prueba anteriores a estos campos no se vuelven
    pinzas por un -1 sin dato.
    """
    if cerrada:
        return "puno"
    if pinza < 0.0 or indice < 0.0:
        return "abierta"
    if pinza <= PINZA_MAX:
        return "pinza"
    if pinza >= C_SPAN_MIN and indice <= C_INDICE_MAX:
        return "C"
    return "abierta"


def _validar(d: _Deteccion) -> str | None:
    """Motivo de rechazo de una detección dudosa, o None si es creíble.

    El puntaje de izquierda/derecha ya no rechaza nada. La etiqueta no la consume
    ninguna decisión —`_emparejar` empareja por posición y el evento `manos` no la
    lleva—, así que tirar la detección entera por su puntaje era descartar datos
    buenos en nombre de un campo muerto. Medido en una sesión de 43 min: de 8216
    detecciones caían 225 bajo el umbral de 0,8 que había aquí, el 67 % en ARMADO
    con una sola mano visible (donde se forma el par) y el 76 % eran el parpadeo de
    un cuadro en una mano que ese mismo segundo se aceptó muchas veces. Los
    fantasmas se siguen filtrando, pero por posición: `MAX_SALTO_PALMAS`, la pista
    pendiente que no se repite se retira en el acto y `CONFIRMA_MANO_SEG`.
    """
    if not PALMA_MIN <= d.palma <= PALMA_MAX:
        return "tamano"
    return None


def _bucket_lado(puntaje: float) -> str:
    """Clave del histograma del puntaje de izquierda/derecha: suelo del bucket de 0,1.

    Es el instrumento que respondió al hallazgo 5: sin él solo se sabía cuántas
    detecciones caían, no con qué puntaje, y por eso el umbral se había decidido por
    impresión. Se conserva ahora que ya no rechaza nada porque es lo único que avisa
    de que el detector está perdiendo confianza en el lado. El 1e-9 cubre la
    representación: `0.7 / 0.1` vale 6,999999999999999 (medido), así que ni se
    divide ni se fía uno del producto sin margen, y una frontera exacta caería en el
    bucket de abajo.
    """
    decimos = min(10, max(0, int(puntaje * 10 + 1e-9)))
    return f"lado_{decimos / 10:.1f}"


# MediaPipe (API de Tasks) etiqueta suponiendo la imagen SIN espejar; como aquí
# el cuadro ya llega espejado, las etiquetas salen cambiadas. Se intercambian
# para que "Left" sea la mano izquierda del usuario. (Solo informativo: la
# identidad de las manos se decide por posición, no por esta etiqueta.)
_LADO_FISICO = {"Left": "Right", "Right": "Left"}


def _asegurar_modelo(ruta: Path, url: str) -> None:
    if not ruta.is_file():
        LOGGER.info("Descargando modelo de manos: %s", ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(url, ruta)


class _DetectorManos:
    """MediaPipe HandLandmarker en modo VIDEO: reutiliza el recuadro del cuadro
    anterior y solo vuelve a correr el detector de palmas si pierde el rastreo."""

    def __init__(self) -> None:
        _asegurar_modelo(_HAND_MODEL_PATH, HAND_MODEL_URL)
        self._modelo = mp_vision.HandLandmarker.create_from_options(
            mp_vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(_HAND_MODEL_PATH)),
                running_mode=mp_vision.RunningMode.VIDEO,
                num_hands=2,
                min_hand_detection_confidence=DETECCION_MIN,
                min_hand_presence_confidence=PRESENCIA_MIN,
                min_tracking_confidence=RASTREO_MIN,
            )
        )

    def detectar(
        self, espejo: np.ndarray, ts_ms: int
    ) -> tuple[list[_Deteccion], list[_Deteccion]]:
        """Devuelve (aceptadas, rechazadas); las rechazadas llevan su ``motivo``."""
        alto, ancho = espejo.shape[:2]
        resultado = self._modelo.detect_for_video(_to_mp(espejo), ts_ms)
        aceptadas: list[_Deteccion] = []
        rechazadas: list[_Deteccion] = []
        for i, landmarks in enumerate(resultado.hand_landmarks):
            etiqueta, puntaje = "?", 0.0
            if i < len(resultado.handedness) and resultado.handedness[i]:
                etiqueta = _LADO_FISICO.get(
                    resultado.handedness[i][0].category_name,
                    resultado.handedness[i][0].category_name,
                )
                puntaje = float(resultado.handedness[i][0].score)
            d = _rasgos(landmarks, ancho, alto, etiqueta, puntaje)
            if d is None:
                continue
            d.motivo = _validar(d)
            (rechazadas if d.motivo else aceptadas).append(d)
        return aceptadas, rechazadas

    def cerrar(self) -> None:
        self._modelo.close()


# ---------------------------------------------------------------------------
# Seguimiento de manos
# ---------------------------------------------------------------------------
@dataclass
class _Mano:
    id: int
    ancla: np.ndarray
    palma: float
    apertura: float
    vertical: bool
    etiqueta: str
    pts: np.ndarray
    visto_t: float
    f_x: _OneEuro
    f_y: _OneEuro
    creado_t: float = 0.0
    visible: bool = True
    # Una mano nueva es "pendiente" hasta verse CONFIRMA_MANO_SEG seguida: los
    # fantasmas parpadean y mueren antes de contar para la máquina de estados.
    confirmada: bool = False
    velocidad: float = 0.0           # palmas por segundo
    cerrada: bool = False
    dedo_max: float = 1.0
    pinza: float = -1.0      # pulgar↔índice en tamaños de palma; -1 = sin dato
    indice: float = 1.0      # extensión del índice (la media de los dedos no basta)
    giro: float = 0.0        # ángulo del eje de la mano en el plano de la imagen
    # La forma es un ESTADO, no un instante: a ~19,5 cuadros/s un solo cuadro no
    # clasifica nada, y un pellizco interpretado como evento se perdería entre dos
    # fotos. Se confirma con la misma disciplina que `cerrada`.
    forma: str = "abierta"
    frames_forma: int = 0
    frames_cambio: int = 0
    # Una mano solo puede agarrar si antes se vio ABIERTA en modo armado: así
    # un puño que entra al cuadro, o que ya estaba cerrado al armar, no agarra.
    listo: bool = False
    palma_desde: float | None = None
    # Segundos continuos con `velocidad <= VEL_QUIETUD`. No es un filtro más: es
    # la única evidencia con la que la interfaz puede decidir «esta mano lleva
    # un rato dentro de la caja del objeto, cógelo».
    quietud: float = 0.0
    # Últimas tres aperturas crudas. Su mediana es el valor que ve el canal de la
    # escala: un cuadro suelto que el clasificador ve mal desaparece en la mediana,
    # igual que `CONFIRMA_FRAMES` exige dos cuadros seguidos para cambiar la forma.
    ap_hist: deque = field(default_factory=lambda: deque(maxlen=3))
    # False justo después de soltar por quietud. Una mano que acaba de soltar
    # SIGUE QUIETA, así que sin este bloqueo la permanencia la volvería a coger
    # sola en cuanto pasara su umbral: agarre y suelta oscilando para siempre.
    # Vuelve a True en cuanto la mano se mueve.
    candida: bool = True

    @property
    def activa(self) -> bool:
        """Vista en este cuadro Y ya confirmada: la única que ve la máquina de estados."""
        return self.visible and self.confirmada

    @property
    def apertura_robusta(self) -> float:
        """La mediana de las últimas tres aperturas: un cuadro loco no la mueve.

        Con menos de tres muestras vale el crudo de esta: la mediana de dos es su
        media, y media con un pico no rechaza nada. Para el primer cuadro de una mano
        no hay historia posible, así que se asume el valor del cuadro y ya está.

        Mediana y no media porque la media también se la lleva un pico: con 0,9 · 0,9
        · 0,0 daría 0,6 y el objeto se encogería un instante.
        """
        if len(self.ap_hist) < 3:
            return float(self.apertura)
        return float(statistics.median(self.ap_hist))


class GestureEngine:
    """Convierte manos en eventos de intención. Un hilo propio, sin interfaz."""

    def __init__(
        self,
        servicio: VisionService,
        acceso: threading.Event | None = None,
        on_evento: Callable[[dict], None] | None = None,
        debug: bool = False,
    ) -> None:
        self._servicio = servicio
        # Si se pasa, los gestos solo funcionan con este evento activo (la cara
        # desbloqueó la sesión). Sin él, siempre habilitado (modo de pruebas).
        self._acceso = acceso
        self.on_evento = on_evento
        self._debug = debug

        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: Exception | None = None
        self.contadores: dict[str, int] = defaultdict(int)

        self._estado = APAGADO
        self._aspecto = 4.0 / 3.0
        self._manos: dict[int, _Mano] = {}
        self._siguiente_id = 0
        self._grupo: list[int] = []
        # El agarre pedido por la interfaz (permanencia). `fijar_agarre` corre en
        # el hilo del canal, así que aquí solo se deja la petición: la máquina la
        # consume en el worker, que es el único que toca `_grupo` y `_estado`.
        self._agarre_pedido: list[int] | None = None
        self._agarre_externo = False
        self._recorrido = 0.0          # palmas desplazadas desde que se cogió
        self._mid_prev: np.ndarray | None = None
        # Suelta por quietud: piso de tiempo (`_gracia_hasta`) tras cada cambio de
        # grupo, y ventana abierta mientras una segunda mano todavía puede entrar.
        self._gracia_hasta = 0.0
        self._union_desde: float | None = None
        # Qué manda sobre la suelta de este agarre externo. Con `True`, el grupo se
        # cogió en forma de pellizco y se suelta ABRIENDO la mano; con `False`, es
        # quietud (permanencia o C). El puño cerrado tiene su propia regla fuera de
        # aquí y no usa este testigo. Lo que fija el valor es la forma de la mano que
        # abrió el agarre, no la de la que luego se suma (ver `_aplicar_agarre_externo`).
        self._suelta_al_abrir = False
        self._rearme_hasta = 0.0
        self._ultima_actividad = 0.0
        self._sin_manos_desde: float | None = None
        # Última vez (reloj del cuadro, = time.monotonic()) que hubo una mano
        # confirmada a la vista, en cualquier estado. AccessGate la usa para no
        # bloquear mientras las manos tapan la cara.
        self._ultima_mano_t = 0.0
        # cuenta del puño que cierra los gestos
        self._puno_id: int | None = None
        self._puno_desde: float | None = None
        self._puno_ref = np.zeros(2)
        self._puno_avisando = False
        self._puno_ultimo_aviso = -1.0
        self._puno_quieto = 0.0          # solo para --ver
        # La interfaz avisa (fijar_sostiene) si el agarre vigente sujeta un
        # objeto. Con True el puño NO cierra: solo una mano vacía apaga los gestos.
        self._sostiene = False
        # referencias del agarre vigente
        self._ref_mid = np.zeros(2)
        # `None` mientras el par no tenga tres separaciones medidas de las que sacar
        # mediana: una sola muestra fijaba el nivel de todo el tramo (ver `_dist_robusta`).
        self._ref_dist: float | None = None
        self._dist_hist: deque = deque(maxlen=3)
        self._ref_ang = 0.0
        self._ang_prev = 0.0
        self._ang_acum = 0.0
        self._f_dist = _OneEuro(MIN_CUTOFF_DIST, BETA_DIST)
        self._f_ang = _OneEuro(MIN_CUTOFF_ANG, BETA_ANG)
        # Con UNA mano la escala y el giro no salen de la separación entre dos: salen
        # de cuánto se ha abierto la mano y de cuánto la has girado, los dos medidos
        # como delta desde el instante del agarre (`_ref_apertura`, `_giro_acum`).
        self._ref_apertura = 0.5
        self._canal_apertura = True
        self._f_ap = _OneEuro(MIN_CUTOFF_AP, BETA_AP)
        self._giro_prev = 0.0
        self._giro_acum = 0.0
        self._f_giro1 = _OneEuro(MIN_CUTOFF_ANG, BETA_ANG)
        # instantánea para --ver
        self._snap_lock = threading.Lock()
        self._snap: tuple | None = None
        # vídeo de calibración hacia la interfaz (andamio, apagado por defecto)
        self._video = False
        self._video_hasta = 0.0
        # lectura de las manos al log y última transformación publicada, para que
        # la línea de 1 Hz la pueda nombrar. El motor arranca callado por no
        # decidir nada él solo: quien la enciende es el despliegue, vía fachada.
        self._lectura = False
        self._lectura_hasta = 0.0
        self._ultima_transf: dict | None = None

    # --- API pública -------------------------------------------------------
    @property
    def estado(self) -> str:
        return self._estado

    @property
    def ultima_mano_t(self) -> float:
        """Instante (time.monotonic) de la última mano confirmada vista; 0.0 si ninguna."""
        return self._ultima_mano_t

    def iniciar(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self.error = None
        self._stop.clear()
        self._servicio.iniciar()
        self._thread = threading.Thread(target=self._worker, name="dark-gestos", daemon=True)
        self._thread.start()

    def detener(self, timeout: float = 5.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("El hilo de GestureEngine no se detuvo a tiempo")

    def fijar_sostiene(self, valor: bool) -> None:
        """La interfaz avisa si el agarre vigente sujeta un objeto.

        Mientras sea True, un puño quieto no cuenta para cerrar los gestos (sería
        sostener un objeto quieto). Se limpia solo al terminar el agarre o al
        apagar; si la interfaz nunca llama a esto, el puño cierra como siempre.
        Se puede llamar desde otro hilo.
        """
        self._sostiene = bool(valor)

    def fijar_agarre(self, ids: list[int]) -> None:
        """La interfaz reclama (o suelta) el agarre de estas manos: AGARRE sin puño.

        Existe porque la selección por permanencia necesita un dato que este motor
        no tiene: dónde está el objeto. Lo tiene la interfaz (`data-agarrable`),
        que es quien decide «esta mano quieta lleva un rato dentro de esa caja» y
        manda los ids que el motor publicó en `manos`. De aquí ella aporta la
        evidencia (`quietud` por mano) y la suelta: con un grupo reclamado desde
        fuera, el objeto se suelta solo cuando todas las manos del grupo llevan
        `T_QUIETUD_SUELTA` quietas y ya se ha recorrido `MIN_TRASLADO`.

        A este motor le da igual dónde esté cada id: no conoce la pantalla ni las
        cajas, solo toma hasta dos ids que ya tiene. Así que la interfaz puede mandar
        la segunda mano del par aunque no pise el objeto (28-oct), y aquí la unión
        sale gratis: `_baseline` re-referencia el tramo en ese instante, de modo que
        la escala vuelve a 1,0 y el desplazamiento a 0 en vez de heredar lo que
        llevaba la mano sola.

        Con la lista vacía se suelta por la misma vía. Un id que el motor no conoce
        se descarta, no se inventa una mano.

        Se puede llamar desde otro hilo (el del canal): aquí solo se deja la
        petición; quien cambia `_grupo` y `_estado` es el worker, en `_paso_armado`.
        """
        self._agarre_pedido = [int(i) for i in ids] if ids else []

    def _aplicar_agarre_externo(self, ts: float, ids: list[int]) -> None:
        """Convierte la petición de la interfaz en estado de la máquina."""
        conocidos = list(dict.fromkeys(i for i in ids if i in self._manos))[:2]
        anterior = list(self._grupo)
        if not conocidos:
            if self._agarre_externo and anterior:
                self._grupo = []
                self._estado = ARMADO
                self._sostiene = False
                self._agarre_externo = False
                self._gracia_hasta = 0.0
                self._union_desde = None
                self._suelta_al_abrir = False
                self._emitir("agarre_fin", motivo="interfaz")
            return
        if conocidos == anterior and self._agarre_externo:
            return   # la misma reclamación de siempre: ni re-referenciar el tramo
        # La familia la decide la forma de la mano del grupo, no un mensaje nuevo: un
        # grupo con una mano en pellizco se suelta al abrir, y los demás siguen con la
        # suelta por quietud de siempre. Y la mano del grupo que manda es la que YA
        # sostenía el agarre: desde que la segunda se suma con solo asomar en cuadro
        # (28-oct), fiarse de «cualquiera de las dos» haría que un pellizco hecho por
        # casualidad al aire cambiara la regla de suelta a mitad de traslado, con lo
        # que el objeto caería en cuanto esa mano se abriera y la suelta por quietud
        # del agarre que él ya tenía quedaría apagada. Sin grupo anterior —o si el
        # dueño se perdió—, deciden las que entran.
        duenas = (
            [i for i in conocidos if i in anterior]
            if self._agarre_externo and anterior
            else conocidos
        )
        al_abrir = any(
            self._manos[i].forma == "pinza" for i in (duenas or conocidos)
        )
        origen = "pinza" if al_abrir else "permanencia"
        self._grupo = conocidos
        self._agarre_externo = True
        self._suelta_al_abrir = al_abrir
        self._ultima_actividad = ts
        self._mid_prev = None
        self._baseline(ts)
        # Cada cambio de grupo vuelve a armar la suelta. Sin esto, el `agarre_cambio`
        # que forma el par se emite en el mismo cuadro en que las dos manos ya pasan
        # de `T_QUIETUD_SUELTA` y el objeto se suelta justo al conseguir el par.
        self._gracia_hasta = ts + GRACIA_CAMBIO
        self._union_desde = None
        if not anterior:
            self._estado = AGARRE
            self._recorrido = 0.0
            self.contadores["agarres_permanencia"] += 1
            self._emitir("agarre_inicio", origen=origen, **self._datos_grupo())
        else:
            if len(self._grupo) == 2:
                self.contadores["agarres_2manos"] += 1
            self._emitir("agarre_cambio", origen=origen, **self._datos_grupo())

    def _acumular_recorrido(self) -> None:
        """Cuánto ha desplazado el grupo desde que se cogió, en palmas.

        Es la prueba de que el objeto se ha movido de verdad, y con ella la pausa
        entre coger y abrir las manos no puede soltar nada.
        """
        ms = [self._manos[i] for i in self._grupo if i in self._manos]
        if not ms:
            self._mid_prev = None
            return
        mid = np.mean([m.ancla for m in ms], axis=0)
        palma = float(np.mean([m.palma for m in ms])) or 1e-6
        if self._mid_prev is not None:
            self._recorrido += float(np.linalg.norm(mid - self._mid_prev)) / palma
        self._mid_prev = mid

    def _mano_que_puede_entrar(self) -> bool:
        """Hay una mano abierta, visible y candidata fuera del grupo.

        Es la única que la interfaz puede reclamar, así que es la única por la que
        merece la pena retrasar la suelta. Una mano no candidata (la que acaba de
        soltar) nunca produce un `coger`: esperarla sería dejar el objeto colgando.
        """
        return any(
            m.activa and m.candida and not m.cerrada and m.id not in self._grupo
            for m in self._manos.values()
        )

    def _suelta_por_quietud(self, ts: float) -> bool:
        """True si el grupo externo está quieto y ya ha recorrido lo bastante.

        Todas las manos, no el punto medio: dos manos abriendo para escalar están
        en casi el mismo sitio y cada una se mueve, así que el centro daría
        falso quieto. Una mano no visible tampoco cuenta quieta: la identidad
        puede seguir viva por `GRACIA_AGARRE` y soltar algo que ya no se ve sería
        soltarlo a ciegas.

        Dos frenos antes de soltar, y los dos miden el mismo hueco:
        `GRACIA_CAMBIO` (cada mano nueva re-arma el tramo; ver `_aplicar_agarre_externo`)
        y la ventana de unión. La ventana es lo que faltaba: el usuario deja quieta
        la primera mano para acercar la segunda, y mientras la segunda llega la
        primera ya cumple la quietud. Con el grupo de una mano, la suelta se decide
        SOLO con esa mano, así que el objeto caía antes de que el par existiera. Se
        espera `T_ESPERA_UNION` a que entre; si no entra nadie, se suelta igual.

        Solo con grupo externo: el puño conserva su regla de siempre (se suelta
        abriendo la mano), así que la nueva suelta no puede tirarle un agarre que
        él no pidió. Y el pellizco tampoco: ese se suelta al abrir (`_suelta_por_apertura`),
        porque pedirle quietud a una mano que está sujetando algo con dos dedos es
        pedirle que suelte.
        """
        if not self._agarre_externo or not self._grupo:
            return False
        if self._suelta_al_abrir:
            return False
        if ts < self._gracia_hasta:
            return False
        if self._recorrido < MIN_TRASLADO:
            return False
        ms = [self._manos[i] for i in self._grupo if i in self._manos]
        if not ms or not all(m.visible and m.quietud >= T_QUIETUD_SUELTA for m in ms):
            self._union_desde = None
            return False
        if len(ms) < 2 and self._mano_que_puede_entrar():
            if self._union_desde is None:
                self._union_desde = ts
            if ts - self._union_desde < T_ESPERA_UNION:
                return False
            self._union_desde = None
        return True

    def _suelta_por_apertura(self, ts: float) -> bool:
        """True si un agarre de pellizco ya está abierto: se suelta al abrir la mano.

        Se exige que TODAS las manos del grupo estén a la vista y abiertas o en C:
        cerrar hasta el puño no suelta nada (si lo hiciera, cerrar la mano para
        apagar los gestos tiraría el objeto al suelo), y perder la mano de vista
        tampoco, porque sin verla no hay prueba de que se haya abierto. Rige la
        misma gracia que en la quietud: el reclamo llega con la mano ya en pinza, y
        dos cuadros de parpadeo del clasificador no pueden soltar lo que acaban de
        coger.
        """
        if not self._agarre_externo or not self._suelta_al_abrir or not self._grupo:
            return False
        if ts < self._gracia_hasta:
            return False
        ms = [self._manos[i] for i in self._grupo if i in self._manos]
        if not ms:
            return False
        return all(m.visible and m.forma in ("abierta", "C") for m in ms)

    def _soltar_grupo_externo(self, ts: float, motivo: str) -> None:
        """Se acaba un agarre reclamado desde fuera, por quietud o por abrir la mano.

        Las manos del grupo dejan de ser candidatas hasta que se muevan: una mano
        quieta que acaba de soltar sigue cumpliendo la permanencia, y sin el bloqueo
        se cogería y soltaría sola para siempre.

        Aquí solo se cambia el estado; el `agarre_fin` lo emite quien nos llama,
        DESPUÉS del fotograma `manos`. Al revés, el receptor vería un instante de
        "sin agarre con la mano todavía candidata" y reclamaría el objeto que
        acaba de soltar: coger y soltar en bucle.
        """
        for i in self._grupo:
            m = self._manos.get(i)
            if m is not None:
                m.candida = False
        self._grupo = []
        self._agarre_externo = False
        self._recorrido = 0.0
        self._mid_prev = None
        self._gracia_hasta = 0.0
        self._union_desde = None
        self._suelta_al_abrir = False
        self._estado = ARMADO
        self._sostiene = False
        self._ultima_actividad = ts
        self.contadores[f"soltados_{motivo}"] += 1

    def instantanea(self) -> tuple | None:
        """(imagen_espejo, marcas, texto) del último cuadro; solo con debug=True."""
        with self._snap_lock:
            return self._snap

    def fijar_video(self, valor: bool) -> None:
        """La interfaz pide que se le reenvíe el cuadro que está viendo el motor.

        Es andamio de calibración (13.10): sin ver la foto no se puede comprobar
        si el círculo de una mano cae encima de esa mano. Manda SIEMPRE el mismo
        cuadro que procesa el motor (espejado, con su `aspecto`), nunca una segunda
        captura: si no, se calibraría contra una imagen que el motor no está mirando.
        Se puede llamar desde otro hilo; con False deja de emitir en el acto.
        """
        self._video = bool(valor)
        self._video_hasta = 0.0

    def fijar_lectura(self, valor: bool) -> None:
        """Enciende o apaga el registro de QUÉ está leyendo el motor de las manos.

        Nació como la otra mitad del andamio de calibración (13.10): el `video`
        enseña el cuadro y esta lectura enseña los números que ese cuadro produjo,
        una línea cada `LECTURA_CADA` segundos con lo mismo que viaja en el evento
        `manos` más el estado de la máquina. Sirve escrito a disco, así que se puede
        leer DESPUÉS de la sesión (`grep lectura gestos.log`) y comparar dos pasadas.
        Por eso dejó de ser andamio: es lo único que queda de una sesión real, y el
        vídeo se apaga en cuanto se quita el `?gestos=manos` de la URL. Quien la
        enciende es el despliegue (`gestos/config.py:LECTURA`, vía fachada); este
        método es el mando, y el mensaje del canal lo deja moverse en caliente, sin
        relanzar el núcleo.

        Se puede llamar desde otro hilo (el del canal); con False deja de registrar
        en el acto. No cambia ninguna decisión: mira, no toca.
        """
        self._lectura = bool(valor)
        self._lectura_hasta = 0.0

    # --- emisión -----------------------------------------------------------
    def _norm(self, p: np.ndarray) -> list[float]:
        return [round(float(p[0] / self._aspecto), 4), round(float(p[1]), 4)]

    def _emitir(self, evento: str, registrar: bool = True, **datos) -> None:
        carga = {"evento": evento, **datos}
        if registrar:
            LOGGER.info("%s %s", evento, datos if datos else "")
        if self.on_evento is not None:
            try:
                self.on_evento(carga)
            except Exception:
                LOGGER.exception("Falló on_evento (%s)", evento)

    def _codificar_cuadro(self, espejo: np.ndarray) -> tuple[str, int, int]:
        """Reduce y codifica a JPEG el cuadro espejado: (data-URL, ancho, alto).

        Este JPEG es sólo para los ojos de quien calibra: el detector recibe
        `espejo` entero antes de reducir, así que su calidad no mueve ni un grado
        de detección. Corre dentro del bucle del worker y por eso su coste se mide
        (2,5 ms con 640, 7,5 ms con 1280 sobre un cuadro real de 720p), pero en las
        tres pasadas reales del 26-oct no se tradujo en fps: el motor procesó ~19,5
        cuadros/s con 320, con 640 y con 1280, que es la primera evidencia de que el
        techo lo pone la tasa que entrega la cámara, no la codificación ni MediaPipe.
        La tabla y la corrección están en 13.10 de `docs/specs.md`.
        """
        alto, ancho = espejo.shape[:2]
        escala = VIDEO_ANCHO / max(ancho, 1)
        nuevo_alto = max(int(round(alto * escala)), 1)
        reducido = cv2.resize(espejo, (VIDEO_ANCHO, nuevo_alto), interpolation=cv2.INTER_AREA)
        ok, crudo = cv2.imencode(
            ".jpg", reducido, [int(cv2.IMWRITE_JPEG_QUALITY), VIDEO_CALIDAD]
        )
        if not ok:
            raise ValueError("cv2.imencode devolvió False")
        return (
            "data:image/jpeg;base64," + base64.b64encode(crudo.tobytes()).decode("ascii"),
            VIDEO_ANCHO, nuevo_alto,
        )

    def _emitir_cuadro(self, espejo: np.ndarray, ts: float) -> None:
        """JPEG reducido del cuadro espejado, a `VIDEO_FPS`, como `cuadro`.

        `registrar=False`: un fondo de 12 cuadros por segundo llenaría el log de
        gestos en minutos y no es un evento, es píxel.
        """
        if ts < self._video_hasta:
            return
        self._video_hasta = ts + 1.0 / VIDEO_FPS
        try:
            imagen, ancho, alto = self._codificar_cuadro(espejo)
        except Exception:
            self.contadores["video_no_codificado"] += 1
            return
        self.contadores["cuadros_enviados"] += 1
        self._emitir(
            "cuadro", registrar=False, imagen=imagen,
            ancho=ancho, alto=alto, aspecto=round(self._aspecto, 4),
        )

    def _registrar_lectura(self, ts: float) -> None:
        """Una línea por `LECTURA_CADA` con todo lo que el detector está viendo.

        Es el instrumento escrito a disco: lo mismo que pinta `--ver` en la ventana y
        el panel del navegador, pero legible DESPUÉS de la sesión y buscable con
        `grep lectura`. Por mano salen `ap` (apertura), `mx` (el dedo más abierto),
        `pz` (pulgar↔índice en palmas), `gi` (giro del eje de la mano, grados), `v`
        (velocidad en palmas/s), `q` (quietud acumulada) y los dos testigos que
        explican un agarre que no llega: `conf` (la mano ya pasó
        `CONFIRMA_MANO_SEG`) y `GRUPO` (sujeta el objeto). Van además las manos
        AÚN PENDIENTES, que el evento `manos` no publica y por lo tanto el panel
        del navegador no puede mostrar: son justo las que hacen de una sesión que
        no engancha. Cierra la línea el estado de la máquina y los contadores con
        valor, porque `rechazada_tamano` creciendo es la respuesta a «enseño la mano
        y no la registra». En esos contadores va además el histograma del puntaje de
        izquierda/derecha (`lado_0.9`, `lado_0.7`, `lado_0.5`): fue el instrumento
        que midió el hallazgo 5 y se queda como aviso, porque ese puntaje ya no
        rechaza nada y es lo único que diría que el detector está perdiendo
        confianza en el lado.

        Mira y no toca: no cambia ninguna decisión, solo lee campos ya calculados.
        """
        if not self._lectura or ts < self._lectura_hasta:
            return
        self._lectura_hasta = ts + LECTURA_CADA
        partes = [
            f"{self._estado} grupo={self._grupo or '-'}"
            f" ext={int(self._agarre_externo)}"
            f" suelta={'abrir' if self._suelta_al_abrir else 'quietud'}"
            f" canal_apertura={int(self._canal_apertura)}"
            f" sostiene={int(self._sostiene)}"
            f" recorrido={self._recorrido:.2f}/{MIN_TRASLADO}"
        ]
        partes.append(f" ref_ap={self._ref_apertura:.2f}")
        rd = "-" if self._ref_dist is None else f"{self._ref_dist:.3f}"
        partes.append(f" ref_dist={rd}")
        if ts < self._gracia_hasta:
            partes.append(f"gracia={self._gracia_hasta - ts:.2f}")
        if self._union_desde is not None:
            partes.append(
                f"espera_union={ts - self._union_desde:.2f}/{T_ESPERA_UNION}"
            )
        for m in sorted(self._manos.values(), key=lambda m: m.id):
            partes.append(
                f"#{m.id} {m.etiqueta} {m.forma} ap={m.apertura:.2f}"
                f" mx={m.dedo_max:.2f} pz={m.pinza:.2f} gi={m.giro:.0f}"
                f" v={m.velocidad:.1f} q={m.quietud:.2f}"
                f" cand={int(m.candida)} conf={int(m.confirmada)}"
                f" vio={int(m.visto_t == ts)}"
                + (" GRUPO" if m.id in self._grupo else "")
            )
        transf = self._ultima_transf
        if transf is not None:
            partes.append(
                f"transf n={transf['n']} dx={transf['dx']:.3f}"
                f" dy={transf['dy']:.3f} escala={transf['escala']:.3f}"
                f" giro={transf['giro']:.3f}"
            )
        cuenta = {k: v for k, v in self.contadores.items() if v}
        if cuenta:
            partes.append("c=" + ",".join(f"{k}:{v}" for k, v in sorted(cuenta.items())))
        LOGGER.info("lectura %s", " | ".join(partes))

    # --- hilo --------------------------------------------------------------
    def _entrega_de_camara(self) -> tuple[float, str]:
        """Lo que la cámara dice de sí misma: fps entregados y modo del driver.

        Viaja junto al rendimiento del motor porque procesados/s sin entregados/s
        no decide nada: si los dos números coinciden, el techo es el aparato, y si
        el de abajo es mayor, es el detector. Se leen con defecto porque
        `VisionService` no tiene puerto declarado que obligue a estos atributos y
        sus dobles de prueba no tienen por qué saber de ellos —y porque 0,0 con
        "sin medida" también es una respuesta que hay que poder escribir—.
        """
        servicio = self._servicio
        if servicio is None:
            return 0.0, "sin cámara"
        entregados = float(getattr(servicio, "fps_entregados", 0.0) or 0.0)
        modo = getattr(servicio, "modo_efectivo", None)
        return entregados, ("%dx%d@%.1f" % modo) if modo else "sin medida"

    def _worker(self) -> None:
        sub = None
        detector = None
        try:
            detector = _DetectorManos()
            sub = self._servicio.suscribir("gestos")
            proceso = psutil.Process()
            n_cpu = max(psutil.cpu_count() or 1, 1)
            proceso.cpu_percent(None)
            cpu_hist: dict[str, list[float]] = defaultdict(list)
            fps_hist: dict[str, list[float]] = defaultdict(list)
            ultimo_cpu = time.monotonic()
            cuadros = 0
            ultimo_ms = 0
            # Ventana de 5 s del cuello de botella (se registra en el log): lo que
            # tarda `detectar` y cuántos cuadros procesa el motor de verdad.
            ventana_t = time.monotonic()
            ventana_n = 0
            det_suma = 0.0
            det_max = 0.0
            det_sin_mano = 0

            while not self._stop.is_set():
                if self._acceso is not None and not self._acceso.is_set():
                    if self._estado != APAGADO:
                        self._apagar(time.monotonic(), "acceso")
                    sub.fijar_fps(0.0)
                    self._stop.wait(0.2)
                    continue

                sub.fijar_fps(FPS_SONDEO if self._estado == APAGADO else FPS_ACTIVO)
                cuadro = sub.siguiente(timeout=0.5)
                if cuadro is None:
                    continue

                espejo = cv2.flip(cuadro.imagen, 1)
                alto, ancho = espejo.shape[:2]
                self._aspecto = ancho / alto
                ts_ms = max(int(cuadro.ts * 1000), ultimo_ms + 1)
                ultimo_ms = ts_ms

                t_detector = time.perf_counter()
                aceptadas, rechazadas = detector.detectar(espejo, ts_ms)
                det_ms = (time.perf_counter() - t_detector) * 1000.0
                for r in rechazadas:
                    self.contadores[f"rechazada_{r.motivo}"] += 1
                self._procesar(cuadro.ts, aceptadas)
                if self._video:
                    self._emitir_cuadro(espejo, cuadro.ts)
                if self._debug:
                    self._guardar_instantanea(espejo, rechazadas)

                cuadros += 1
                det_suma += det_ms
                det_max = max(det_max, det_ms)
                if not aceptadas:
                    det_sin_mano += 1
                ventana_n += 1
                ahora = time.monotonic()
                if ahora - ventana_t >= 5.0:
                    if self._estado != APAGADO and ventana_n:
                        # Techo real del motor: si `VisionService` registra que la
                        # cámara entrega 60 y aquí salen 22, el cuello es el
                        # detector; si los dos salen ~20, el cuello es el modo de
                        # captura y abaratar la detección no compra ni un cuadro.
                        entregados, modo = self._entrega_de_camara()
                        LOGGER.info(
                            "gestos %s: %.1f cuadros procesados/s (la cámara "
                            "entrega %.1f, modo %s), detector %.1f ms (máx %.0f), "
                            "sin mano %.0f%%",
                            self._estado,
                            ventana_n / (ahora - ventana_t),
                            entregados,
                            modo,
                            det_suma / ventana_n,
                            det_max,
                            100.0 * det_sin_mano / ventana_n,
                        )
                    ventana_t = ahora
                    ventana_n = 0
                    det_suma = 0.0
                    det_max = 0.0
                    det_sin_mano = 0
                if ahora - ultimo_cpu >= 1.0:
                    cpu_hist[self._estado].append(proceso.cpu_percent(None) / n_cpu)
                    fps_hist[self._estado].append(cuadros / (ahora - ultimo_cpu))
                    cuadros = 0
                    ultimo_cpu = ahora

            LOGGER.info("=== Promedio GestureEngine por estado ===")
            for estado, muestras in cpu_hist.items():
                LOGGER.info(
                    "%s CPU %.1f%% FPS %.1f (%s muestras)",
                    estado, float(np.mean(muestras)),
                    float(np.mean(fps_hist[estado])), len(muestras),
                )
            LOGGER.info("Contadores de la sesión: %s", dict(self.contadores))
        except Exception as error:
            self.error = error
            LOGGER.exception("GestureEngine terminó por un error.")
        finally:
            if sub is not None:
                sub.cerrar()
            if detector is not None:
                detector.cerrar()

    # --- núcleo (sin hilos: se puede probar con detecciones sintéticas) ----
    def _procesar(self, ts: float, detecciones: list[_Deteccion]) -> None:
        self._asociar(detecciones, ts)
        self._registrar_distancia()
        if any(m.activa for m in self._manos.values()):
            self._ultima_mano_t = ts
        if self._estado == APAGADO:
            self._paso_apagado(ts)
        else:
            self._paso_armado(ts)
        self._registrar_lectura(ts)

    def _asociar(self, detecciones: list[_Deteccion], ts: float) -> None:
        manos = list(self._manos.values())
        usadas_m: set[int] = set()
        usadas_d = self._emparejar(manos, detecciones, ts, usadas_m)
        for d in detecciones:
            self.contadores[_bucket_lado(d.puntaje)] += 1
        for mi, m in enumerate(manos):
            if mi not in usadas_m:
                m.visible = False
        # Primero se retiran las que ya no cuentan, y solo después se decide si
        # hay sitio para una detección nueva. Una mano pendiente que no se repite
        # en el cuadro siguiente era un fantasma: se descarta sin gracia. Las
        # confirmadas sí tienen gracia (GRACIA_MANO, o GRACIA_AGARRE si está
        # sujetando el objeto).
        for m in list(self._manos.values()):
            if not m.visible and (
                not m.confirmada or ts - m.visto_t > self._gracia_de(m)
            ):
                self._retirar_mano(m.id)
        for di, d in enumerate(detecciones):
            if di in usadas_d:
                continue
            if len(self._manos) >= 2:
                # Ya hay dos manos vigentes (visibles o en gracia): la tercera
                # detección es casi seguro un fantasma. NUNCA expulsa a una mano
                # confirmada; si la mano en gracia no vuelve, caduca y entonces
                # una detección real podrá ocupar su sitio.
                self.contadores["tercera_mano_ignorada"] += 1
                continue
            self._crear_mano(d, ts)

    def _gracia_de(self, m: _Mano) -> float:
        """Cuánto sobrevive una mano sin verse.

        La identidad de las manos es posicional: si una pista se retira y vuelve,
        entra con id nuevo y `listo=False`, y hay que abrir la mano otra vez para
        poder agarrar. Por eso una mano sujeta tiene más margen que una suelta.
        """
        if self._estado == AGARRE and m.id in self._grupo:
            return GRACIA_AGARRE
        return GRACIA_MANO

    def _emparejar(
        self,
        manos: list[_Mano],
        detecciones: list[_Deteccion],
        ts: float,
        usadas_m: set[int],
    ) -> set[int]:
        """Empareja codiciosamente pista↔detección por cercanía.

        ``usadas_m`` se pasa para compartirlo entre pasadas; devuelve los índices
        de ``detecciones`` consumidos (son índices de ESA lista, no de la otra).
        """
        usadas_d: set[int] = set()
        pares = sorted(
            (
                float(np.linalg.norm(m.ancla - d.ancla) / max(m.palma, 1e-6)),
                mi, di,
            )
            for mi, m in enumerate(manos)
            for di, d in enumerate(detecciones)
        )
        for salto, mi, di in pares:
            if salto > MAX_SALTO_PALMAS:
                break
            if mi in usadas_m or di in usadas_d:
                continue
            usadas_m.add(mi)
            usadas_d.add(di)
            self._actualizar(manos[mi], detecciones[di], ts)
        return usadas_d

    def _crear_mano(self, d: _Deteccion, ts: float) -> None:
        self._siguiente_id += 1
        f_x = _OneEuro(MIN_CUTOFF_POS, BETA_POS)
        f_y = _OneEuro(MIN_CUTOFF_POS, BETA_POS)
        f_x(float(d.ancla[0]), ts)
        f_y(float(d.ancla[1]), ts)
        m = _Mano(
            id=self._siguiente_id, ancla=d.ancla.copy(), palma=d.palma,
            apertura=d.apertura, vertical=d.vertical, etiqueta=d.etiqueta,
            pts=d.pts, visto_t=ts, f_x=f_x, f_y=f_y, creado_t=ts,
            ap_hist=deque([float(d.apertura)], maxlen=3),
            cerrada=d.dedo_max <= DEDO_CIERRA, dedo_max=d.dedo_max,
            pinza=d.pinza, indice=d.indice, giro=d.giro,
            forma=_clasificar_forma(
                cerrada=d.dedo_max <= DEDO_CIERRA, pinza=d.pinza, indice=d.indice
            ),
        )
        self._manos[m.id] = m

    def _actualizar(self, m: _Mano, d: _Deteccion, ts: float) -> None:
        nuevo = np.array([m.f_x(float(d.ancla[0]), ts), m.f_y(float(d.ancla[1]), ts)])
        dt = max(ts - m.visto_t, 1e-3)
        # `m.visible` aún vale lo del cuadro ANTERIOR (`_asociar` lo recalcula al
        # final): False = la mano no se vio en el cuadro previo, y `dt` incluye ese
        # hueco. Ni la velocidad puede diluirse entre un tiempo en que no se midió
        # nada, ni ese tiempo puede contar como quietud: soltaría por quietud un
        # objeto cuya mano solo parpadeó (verificado: 0,4 s de hueco = suelta).
        hueco = not m.visible
        dt_medida = min(dt, HUECO_DT_MAX) if hueco else dt
        m.velocidad = float(np.linalg.norm(nuevo - m.ancla) / dt_medida / max(d.palma, 1e-6))
        if hueco:
            m.quietud = 0.0
        elif m.velocidad <= VEL_QUIETUD:
            m.quietud += dt
        else:
            m.quietud = 0.0
            m.candida = True   # se movió: ya puede volver a coger por permanencia
        m.ancla = nuevo
        m.palma, m.apertura, m.vertical = d.palma, d.apertura, d.vertical
        m.ap_hist.append(float(d.apertura))
        m.dedo_max = d.dedo_max
        m.pinza, m.indice, m.giro = d.pinza, d.indice, d.giro
        m.etiqueta, m.pts = d.etiqueta, d.pts
        m.visto_t, m.visible = ts, True
        if not m.confirmada and ts - m.creado_t >= CONFIRMA_MANO_SEG:
            m.confirmada = True
        # histéresis + confirmación de CONFIRMA_FRAMES cuadros seguidos
        quiere_cambiar = (not m.cerrada and d.dedo_max <= DEDO_CIERRA) or (
            m.cerrada and d.dedo_max >= DEDO_ABRE
        )
        m.frames_cambio = m.frames_cambio + 1 if quiere_cambiar else 0
        if m.frames_cambio >= CONFIRMA_FRAMES:
            m.cerrada = not m.cerrada
            m.frames_cambio = 0
        # Misma disciplina para la forma: el cambio se adopta tras CONFIRMA_FRAMES
        # cuadros seguidos pidiéndolo. Sin esto, un cuadro donde el índice se ve
        # doblado convertiría la mano en "C" un instante y la soltaría.
        deseada = _clasificar_forma(cerrada=m.cerrada, pinza=d.pinza, indice=d.indice)
        if deseada == m.forma:
            m.frames_forma = 0
        else:
            m.frames_forma += 1
            if m.frames_forma >= CONFIRMA_FRAMES:
                m.forma = deseada
                m.frames_forma = 0

    def _retirar_mano(self, mano_id: int) -> None:
        self._manos.pop(mano_id, None)

    # --- APAGADO: buscar el embrague ---------------------------------------
    def _paso_apagado(self, ts: float) -> None:
        if ts < self._rearme_hasta:
            for m in self._manos.values():
                m.palma_desde = None
            return
        for m in self._manos.values():
            ok = (
                m.activa and m.apertura >= APERTURA_PALMA and m.vertical
                and m.velocidad <= VEL_MAX_EMBRAGUE
            )
            if not ok:
                m.palma_desde = None
                continue
            if m.palma_desde is None:
                m.palma_desde = ts
            if ts - m.palma_desde >= T_EMBRAGUE:
                self._armar(ts, "palma")
                return

    def _armar(self, ts: float, motivo: str) -> None:
        self._estado = ARMADO
        self._ultima_actividad = ts
        self._sin_manos_desde = None
        # Una petición de agarre llegada después de `_apagar` (la interfaz aún no
        # había visto `gestos_off`) no puede sobrevivir hasta aquí: empezaría
        # cogiendo un objeto que nadie pidió en este estado.
        self._agarre_pedido = None
        self._reiniciar_puno()
        for m in self._manos.values():
            m.palma_desde = None
            m.listo = False
        self.contadores["embragues"] += 1
        self._emitir("gestos_on", motivo=motivo, aspecto=round(self._aspecto, 4))

    def _apagar(self, ts: float, motivo: str) -> None:
        if self._grupo:
            self._grupo = []
            self._emitir("agarre_fin", motivo=motivo)
        self._estado = APAGADO
        self._sostiene = False
        # Un agarre externo pendiente de consumir no puede sobrevivir al apagado:
        # si no, el siguiente ARMADO empieza cogiendo un objeto sin que nadie lo
        # haya pedido en este estado.
        self._agarre_pedido = None
        self._agarre_externo = False
        self._recorrido = 0.0
        self._mid_prev = None
        self._gracia_hasta = 0.0
        self._union_desde = None
        self._suelta_al_abrir = False
        self._rearme_hasta = ts + REARME_SEG
        self._reiniciar_puno()
        for m in self._manos.values():
            m.palma_desde = None
        self.contadores[f"apagados_{motivo}"] += 1
        self._emitir("gestos_off", motivo=motivo)

    # --- ARMADO / AGARRE ---------------------------------------------------
    def _paso_armado(self, ts: float) -> None:
        visibles = [m for m in self._manos.values() if m.activa]

        if self._detectar_cierre_puno(ts, visibles):
            self.contadores["cierres_puno"] += 1
            self._apagar(ts, "puno")
            return

        if visibles:
            self._sin_manos_desde = None
        elif not self._grupo:
            if self._sin_manos_desde is None:
                self._sin_manos_desde = ts
            elif ts - self._sin_manos_desde >= SIN_MANOS_APAGA:
                self._apagar(ts, "sin_manos")
                return
        if not self._grupo and ts - self._ultima_actividad >= INACTIVIDAD_APAGA:
            self._apagar(ts, "inactividad")
            return

        for m in visibles:
            if not m.cerrada:
                m.listo = True

        pedido = self._agarre_pedido
        if pedido is not None:
            self._agarre_pedido = None
            self._aplicar_agarre_externo(ts, pedido)

        anterior = list(self._grupo)
        if self._agarre_externo:
            # Un grupo reclamado desde fuera no depende del puño: solo de que la
            # mano siga en la máquina (la identidad la aguanta `GRACIA_AGARRE`).
            self._grupo = [i for i in self._grupo if i in self._manos]
            if not self._grupo:
                self._agarre_externo = False
        else:
            self._grupo = [i for i in self._grupo if i in self._manos and self._manos[i].cerrada]
            for m in sorted(visibles, key=lambda m: m.id):
                if len(self._grupo) >= 2:
                    break
                if m.id not in self._grupo and m.cerrada and m.listo:
                    self._grupo.append(m.id)

        if self._grupo != anterior:
            self._ultima_actividad = ts
            if not anterior and self._grupo:
                self._estado = AGARRE
                self.contadores["agarres"] += 1
                self._baseline(ts)
                self._emitir("agarre_inicio", origen="puno", **self._datos_grupo())
            elif anterior and not self._grupo:
                self._estado = ARMADO
                self._sostiene = False
                self._emitir("agarre_fin")
            else:
                if len(self._grupo) == 2:
                    self.contadores["agarres_2manos"] += 1
                self._baseline(ts)
                self._emitir("agarre_cambio", origen="puno", **self._datos_grupo())

        # La suelta se decide antes de publicar las manos y el `agarre_fin` se
        # emite después: ver las manos ya no candidatas es lo único que impide al
        # receptor reclamar, a mitad de lote, el objeto que acaba de soltar.
        suelta: str | None = None
        if self._grupo and self._agarre_externo:
            self._acumular_recorrido()
            if self._suelta_por_apertura(ts):
                self._soltar_grupo_externo(ts, "abierto")
                suelta = "abierto"
            elif self._suelta_por_quietud(ts):
                self._soltar_grupo_externo(ts, "quietud")
                suelta = "quietud"

        self._emitir(
            "manos", registrar=False,
            manos=[
                {
                    "id": m.id, "x": self._norm(m.ancla)[0], "y": self._norm(m.ancla)[1],
                    "cerrada": m.cerrada, "apertura": round(m.apertura, 3),
                    "quietud": round(m.quietud, 3), "candida": m.candida,
                    "forma": m.forma, "pinza": round(m.pinza, 3),
                    "giro": round(m.giro, 1),
                    "dedo": round(m.dedo_max, 3), "vel": round(m.velocidad, 2),
                }
                for m in visibles
            ],
        )
        if suelta is not None:
            self._emitir("agarre_fin", motivo=suelta)
        elif self._grupo:
            self._emitir_transformacion(ts)

    def _datos_grupo(self) -> dict:
        ms = [self._manos[i] for i in self._grupo]
        mid = np.mean([m.ancla for m in ms], axis=0)
        return {"manos": list(self._grupo), "n": len(ms), "ancla": self._norm(mid)}

    def _registrar_distancia(self) -> None:
        """Guarda la separación del par cuadro a cuadro, esté donde esté la máquina.

        Es el historial PREVIO al reclamo lo que necesita `_baseline`, igual que
        `ap_hist` de la mano: si solo se mirara el cuadro en que la segunda mano
        asoma, esa única muestra fijaría el nivel de escala de todo el tramo. Se
        alimenta de las dos manos CONFIRMADAS (`activa`), así que una segunda
        mano que acaba de aparecer no puede fijar referencia hasta que el detector
        la sostiene.
        """
        ms = sorted((m for m in self._manos.values() if m.activa), key=lambda m: m.id)
        if len(ms) == 2:
            self._dist_hist.append(float(np.linalg.norm(ms[1].ancla - ms[0].ancla)))

    def _dist_robusta(self) -> float | None:
        """Mediana de las tres últimas separaciones del par, o None si el par es recién nacido.

        Misma disciplina que la forma (`CONFIRMA_FRAMES`) y que la apertura: un
        fotograma no mide nada. Con menos de tres muestras devuelve None en vez de
        una de las dos; adivinar con la única muestra que hay es justo el defecto.
        """
        if len(self._dist_hist) < 3:
            return None
        return float(statistics.median(self._dist_hist))

    def _baseline(self, ts: float) -> None:
        """Fija la referencia: las transformaciones se miden contra este instante."""
        ms = [self._manos[i] for i in self._grupo]
        self._ref_mid = np.mean([m.ancla for m in ms], axis=0)
        # La mano que agarra en pellizco se suelta AL ABRIR, así que abrir no puede
        # además ampliar: el canal de la apertura se cierra para esa familia.
        self._canal_apertura = not self._suelta_al_abrir
        # La referencia es la mediana de lo que la mano venía mostrando al coger, no
        # el cuadro del agarre: una sola muestra sesgaba todo el tramo si ese
        # fotograma veía la mano a medio cerrar.
        self._ref_apertura = ms[0].apertura_robusta
        # El filtro arranca sobre la referencia, así que el primer `transformacion`
        # del tramo sale escala 1,0 igual que antes.
        self._f_ap = _OneEuro(MIN_CUTOFF_AP, BETA_AP)
        self._f_ap(self._ref_apertura, ts)
        self._giro_prev = math.radians(ms[0].giro)
        self._giro_acum = 0.0
        self._f_giro1 = _OneEuro(MIN_CUTOFF_ANG, BETA_ANG)
        self._f_giro1(0.0, ts)
        if len(ms) == 2:
            v = ms[1].ancla - ms[0].ancla
            ang = math.atan2(v[1], v[0])
            self._f_dist = _OneEuro(MIN_CUTOFF_DIST, BETA_DIST)
            self._f_ang = _OneEuro(MIN_CUTOFF_ANG, BETA_ANG)
            # La referencia del par es la mediana de lo que las dos venían separando,
            # y si el par todavía no tiene tres muestras NO se fija con una
            # aproximación: `_ref_dist` queda None y el canal de la escala se queda
            # en 1,0 hasta asentarse. Fijarla con la única muestra del cuadro de la
            # unión era el modo de que la segunda mano hinchara o encogiera el objeto
            # entero del tramo.
            ref = self._dist_robusta()
            self._ref_dist = None if ref is None else max(ref, DIST_REF_MIN)
            if self._ref_dist is not None:
                self._f_dist(self._ref_dist, ts)
            self._ang_prev = ang
            self._ang_acum = ang
            self._ref_ang = self._f_ang(ang, ts)

    def _emitir_transformacion(self, ts: float) -> None:
        ms = [self._manos[i] for i in self._grupo]
        mid = np.mean([m.ancla for m in ms], axis=0)
        dx, dy = mid - self._ref_mid
        escala, giro = 1.0, 0.0
        if len(ms) == 2:
            v = ms[1].ancla - ms[0].ancla
            dist = float(np.linalg.norm(v))
            ang = math.atan2(v[1], v[0])
            self._ang_acum += _envolver(ang - self._ang_prev)  # desenrolla el salto de ±pi
            self._ang_prev = ang
            giro = self._f_ang(self._ang_acum, ts) - self._ref_ang
            if self._ref_dist is None:
                ref = self._dist_robusta()
                if ref is not None:
                    # Asentado: el filtro arranca sobre la referencia, así que este
                    # primer cuadro publicado sale escala 1,0 y el tramo no da un salto.
                    self._ref_dist = max(ref, DIST_REF_MIN)
                    self._f_dist(self._ref_dist, ts)
                escala = 1.0
            else:
                ratio = self._f_dist(dist, ts) / self._ref_dist
                escala = float(np.clip(1.0 + (ratio - 1.0) * GANANCIA_PAR,
                                       ESCALA_MIN, ESCALA_MAX))
        else:
            # Una mano: gira lo que gire ella y escala lo que ella se abra, los dos
            # contra la referencia del instante del agarre. El giro se acumula
            # desenrollado, como con dos, para que pasar por arriba no reinvente la
            # rotación cada vez que la mano cruza el ±180.
            rad = math.radians(ms[0].giro)
            self._giro_acum += _envolver(rad - self._giro_prev)
            self._giro_prev = rad
            giro = self._f_giro1(self._giro_acum, ts)
            if self._canal_apertura:
                ap = self._f_ap(ms[0].apertura_robusta, ts)
                ganancia = APERTURA_A_ESCALA * (ap - self._ref_apertura)
                escala = float(np.clip(1.0 + ganancia, ESCALA_MIN, ESCALA_MAX))
        self._ultima_transf = {
            "n": len(ms), "dx": float(dx), "dy": float(dy),
            "escala": escala, "giro": float(giro),
        }
        self._emitir(
            "transformacion", registrar=False, n=len(ms),
            dx=round(float(dx), 4), dy=round(float(dy), 4),
            escala=round(escala, 4), giro=round(float(giro), 4),
        )

    # --- cierre por puño ---------------------------------------------------
    def _reiniciar_puno(self) -> None:
        """Borra la cuenta del puño en silencio (sin avisar a la interfaz)."""
        self._puno_id = None
        self._puno_desde = None
        self._puno_avisando = False
        self._puno_ultimo_aviso = -1.0
        self._puno_quieto = 0.0

    def _cancelar_cuenta_puno(self) -> None:
        """Reinicia la cuenta; si la interfaz ya estaba mostrando el anillo, se lo dice."""
        if self._puno_avisando:
            self._emitir("cierre_cancelado", registrar=False)
        self._reiniciar_puno()

    def _empezar_cuenta_puno(self, m: _Mano, ts: float) -> None:
        self._puno_id = m.id
        self._puno_desde = ts
        self._puno_ref = m.ancla.copy()

    def _detectar_cierre_puno(self, ts: float, visibles: list[_Mano]) -> bool:
        """True tras T_PUNO_CIERRA s con UN puño cerrado y quieto.

        Candidata: la única mano cerrada a la vista. Otra mano abierta no estorba;
        dos puños sí (se está manipulando con las dos). En AGARRE, además, esa mano
        tiene que ser la única que sujeta. Moverse más de RADIO_PUNO_PALMAS, abrir
        la mano o perderla reinicia la cuenta.
        """
        if self._sostiene:
            if self._grupo:
                self._cancelar_cuenta_puno()  # sostiene un objeto: no se cierra
                return False
            self._sostiene = False            # sin agarre no hay nada sujeto: bandera vieja
        cerradas = [m for m in visibles if m.cerrada]
        candidata = None
        if len(cerradas) == 1 and (not self._grupo or self._grupo == [cerradas[0].id]):
            candidata = cerradas[0]
        if candidata is not None:
            # "Cerrada" (para agarrar) es permisiva a propósito; apagar los gestos
            # no: una mano a medio curvar (ajustarse las gafas, pellizcar) no es un
            # puño. Para empezar la cuenta hace falta un puño apretado; ya contando,
            # se tolera algo más de apertura porque el valor oscila.
            contando = self._puno_id == candidata.id and self._puno_desde is not None
            limite = APERTURA_PUNO_SIGUE if contando else APERTURA_PUNO_INICIA
            if candidata.dedo_max > limite:
                candidata = None
        if candidata is None:
            self._cancelar_cuenta_puno()
            return False

        if self._puno_id != candidata.id or self._puno_desde is None:
            self._cancelar_cuenta_puno()
            self._empezar_cuenta_puno(candidata, ts)
            return False

        movimiento = float(np.linalg.norm(candidata.ancla - self._puno_ref)) / max(
            candidata.palma, 1e-6
        )
        if movimiento > RADIO_PUNO_PALMAS:
            self._cancelar_cuenta_puno()
            self._empezar_cuenta_puno(candidata, ts)
            return False

        quieto = ts - self._puno_desde
        self._puno_quieto = quieto
        if quieto >= T_PUNO_CIERRA:
            self._reiniciar_puno()  # cierre exitoso: nada que cancelar
            return True
        if quieto >= T_PUNO_AVISO:
            progreso = (quieto - T_PUNO_AVISO) / (T_PUNO_CIERRA - T_PUNO_AVISO)
            if not self._puno_avisando or progreso - self._puno_ultimo_aviso >= PASO_AVISO:
                self._puno_avisando = True
                self._puno_ultimo_aviso = progreso
                self._emitir("cierre_progreso", registrar=False, progreso=round(progreso, 3))
        return False

    # --- ayuda visual ------------------------------------------------------
    def _guardar_instantanea(self, espejo: np.ndarray, rechazadas: list[_Deteccion]) -> None:
        marcas = [
            (m.id, m.cerrada, m.apertura, m.ancla.copy(), m.pts.copy(), m.etiqueta,
             m.velocidad, m.confirmada, m.dedo_max, m.forma, m.pinza, m.giro,
             m.quietud)
            for m in self._manos.values() if m.visible
        ]
        descartes = [(r.pts.copy(), r.ancla.copy(), r.motivo, r.puntaje) for r in rechazadas]
        texto = f"{self._estado} grupo={len(self._grupo)} manos={len(marcas)}"
        if self._puno_desde is not None:
            texto += f"  puño quieto {self._puno_quieto:.1f}/{T_PUNO_CIERRA:.0f} s"
        with self._snap_lock:
            self._snap = (espejo, marcas, descartes, texto)


# ---------------------------------------------------------------------------
# Banco de pruebas: python -m <paquete>.gestos [--ver] [--lectura] [--camara N] [--log ARCHIVO]
# ---------------------------------------------------------------------------
def _dibujar(snap: tuple) -> np.ndarray:
    imagen, marcas, descartes, texto = snap
    salida = imagen.copy()
    alto = salida.shape[0]
    # Rechazadas: en gris, con el motivo. Si una mano REAL sale aquí, el umbral de
    # tamaño (PALMA_MIN/MAX) está mal; si el fantasma sale, funciona.
    for pts, ancla, motivo, puntaje in descartes:
        px = (pts * alto).astype(int)
        for a, b in _CONEXIONES:
            cv2.line(salida, tuple(px[a]), tuple(px[b]), (150, 150, 150), 1)
        cx, cy = (ancla * alto).astype(int)
        cv2.putText(
            salida, f"RECHAZADA {motivo} lado={puntaje:.2f}", (int(cx) + 12, int(cy)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (150, 150, 150), 1,
        )
    for (mano_id, cerrada, apertura, ancla, pts, etiqueta, velocidad, confirmada,
         dedo_max, forma, pinza, giro, quietud) in marcas:
        px = (pts * alto).astype(int)
        for a, b in _CONEXIONES:
            cv2.line(salida, tuple(px[a]), tuple(px[b]), (0, 200, 255), 1)
        cx, cy = (ancla * alto).astype(int)
        color = (0, 0, 255) if cerrada else (0, 255, 0)
        if not confirmada:
            color = (0, 215, 255)  # amarillo: pendiente de confirmar
        cv2.circle(salida, (int(cx), int(cy)), 10, color, 2)
        cv2.putText(
            salida,
            f"#{mano_id} {etiqueta} {forma} ap={apertura:.2f} mx={dedo_max:.2f}"
            f" pz={pinza:.2f} gi={giro:.0f} v={velocidad:.1f} q={quietud:.2f}"
            + ("" if confirmada else " (pendiente)"),
            (int(cx) + 12, int(cy)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1,
        )
    cv2.putText(salida, texto, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return salida


def _principal() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Banco de pruebas del motor gestual")
    parser.add_argument("--ver", action="store_true", help="ventana con manos y valores (q para salir)")
    parser.add_argument(
        "--lectura", action="store_true",
        help=f"una línea por segundo con lo que el motor lee de las manos (cada {LECTURA_CADA} s)",
    )
    parser.add_argument("--camara", type=int, default=0)
    parser.add_argument("--log", default="gestos.log", help="archivo donde se registran los eventos")
    args = parser.parse_args()

    formato = "%(asctime)s %(levelname)s %(message)s"
    logging.basicConfig(
        level=logging.INFO, format=formato,
        handlers=[logging.StreamHandler(), logging.FileHandler(args.log, encoding="utf-8")],
    )
    servicio = VisionService(args.camara)
    motor = GestureEngine(servicio, debug=args.ver)
    motor.fijar_lectura(args.lectura)
    servicio.iniciar()
    motor.iniciar()
    LOGGER.info("Motor gestual en marcha. Palma abierta 0,5 s para armar; un puño quieto 3 s para cerrar.")
    try:
        while motor.error is None:
            if args.ver:
                snap = motor.instantanea()
                if snap is not None:
                    cv2.imshow("gestos (q para salir)", _dibujar(snap))
                if cv2.waitKey(15) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        motor.detener()
        servicio.detener()
        if args.ver:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    _principal()