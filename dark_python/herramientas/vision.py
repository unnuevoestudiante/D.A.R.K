"""Visión compartida de D.A.R.K: dueño único de la cámara y helpers de rostro.

Dos responsabilidades, separadas dentro del mismo archivo:

* ``VisionService``: el ÚNICO que abre la cámara. Publica el último cuadro y
  cada consumidor (acceso facial hoy, gestos mañana) se suscribe y pide su
  propio ritmo en fps. La cámara se abre solo mientras haya algún consumidor
  con fps > 0 y se libera sola cuando no queda ninguno.
* Helpers de rostro (alineación, embedding, liveness): movidos textualmente
  desde dark_acceso.py en la Fase B del plan (docs/plan-acceso-v2.md §6),
  funciones puras cuadro→vectores, sin cambios de comportamiento.

dark_acceso.py sigue siendo el dueño de la máquina de estados del acceso.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from typing import NamedTuple, Protocol, Sequence

import cv2
import mediapipe as mp
import numpy as np

LOGGER = logging.getLogger(__name__)

# Pedir este fps (o cualquiera >= UMBRAL_LECTURA_CONTINUA) significa "lectura
# continua": la cámara entrega a su ritmo nativo y nadie espera entre cuadros.
FPS_CONTINUO = 30.0
UMBRAL_LECTURA_CONTINUA = 15.0
CAMERA_RETRY_SECONDS = 2.0
# Cada cuánto registra el servicio los fps que de verdad está entregando el
# driver, mientras alguien lee en continuo. Es la única medida fiable: el
# `CAP_PROP_FPS` que devuelve el backend miente (DirectShow contesta -1).
FPS_VENTANA_SEG = 5.0
# Por debajo del umbral se lee "a pedido": se descartan los cuadros viejos que
# la cámara fue acumulando y se toma el más reciente (así se hacía en el gate).
_GRABS_DE_LIMPIEZA = 3
# Margen para que el reloj de un consumidor al mismo ritmo que el servicio no
# pierda un cuadro de cada dos por una diferencia de milisegundos.
_TOLERANCIA_PERIODO = 0.8


class Cuadro(NamedTuple):
    """Un cuadro publicado. ``imagen`` es compartida: tratarla como solo lectura."""

    seq: int
    ts: float
    imagen: np.ndarray


class _Suscriptor:
    """Vista de un consumidor sobre el servicio: su propio ritmo, su propia cola de uno."""

    def __init__(self, servicio: "VisionService", nombre: str) -> None:
        self._servicio = servicio
        self.nombre = nombre
        self._fps = 0.0
        self._ultimo_seq = 0
        self._ultimo_ts = 0.0
        # Un cuadro anterior al último cambio de ritmo no vale: puede tener
        # medio segundo si veníamos de vigilancia lenta.
        self._desde = 0.0
        self._cerrado = False

    def fijar_fps(self, fps: float) -> None:
        if not math.isfinite(fps) or fps < 0:
            raise ValueError("fps debe ser un número >= 0")
        if self._cerrado or fps == self._fps:
            return
        self._fps = fps
        self._desde = time.monotonic()
        self._servicio._cambiar_fps(self.nombre, fps)

    def siguiente(self, timeout: float) -> Cuadro | None:
        """Espera el próximo cuadro fresco respetando el fps de este consumidor.

        Devuelve None si vence el timeout, si el servicio se detuvo o si la
        cámara no está entregando cuadros.
        """
        servicio = self._servicio
        limite = time.monotonic() + timeout
        with servicio._cond:
            while not self._cerrado and not servicio._stop.is_set():
                cuadro = servicio._cuadro
                ahora = time.monotonic()
                periodo = (
                    0.0
                    if self._fps >= UMBRAL_LECTURA_CONTINUA or self._fps <= 0
                    else 1.0 / self._fps
                )
                if (
                    cuadro is not None
                    and cuadro.seq > self._ultimo_seq
                    and cuadro.ts >= self._desde
                    and cuadro.ts >= self._ultimo_ts + periodo * _TOLERANCIA_PERIODO
                ):
                    self._ultimo_seq = cuadro.seq
                    self._ultimo_ts = cuadro.ts
                    return cuadro
                restante = limite - ahora
                if restante <= 0:
                    return None
                servicio._cond.wait(min(restante, 0.1))
        return None

    def cerrar(self) -> None:
        if self._cerrado:
            return
        self._cerrado = True
        self._servicio._quitar(self.nombre)


class VisionService:
    """Único dueño de la cámara. Reparte el último cuadro a sus suscriptores."""

    def __init__(
        self,
        camera_index: int = 0,
        ancho: int = 0,
        alto: int = 0,
        fps: float = 0.0,
        codificador: str = "",
    ) -> None:
        self.camera_index = camera_index
        # Cero / cadena vacía = no pedir nada, dejar el modo por defecto del
        # driver. Son pedidos: lo que se obtiene se registra al abrir.
        self.ancho = int(ancho or 0)
        self.alto = int(alto or 0)
        self.fps = float(fps or 0.0)
        self.codificador = (codificador or "").strip().upper()
        # Los dos números que el consumidor necesita y el driver no devuelve
        # fiables: el modo que salió de verdad (`modo_efectivo`, leído tras pedirlo)
        # y los cuadros por segundo que se están publicando (`fps_entregados`,
        # contados en ventana). Se leen, no se piden: `CAP_PROP_FPS` contesta -1.
        self.modo_efectivo: tuple[int, int, float] | None = None
        self.fps_entregados = 0.0
        self._cond = threading.Condition()
        self._stop = threading.Event()
        self._despertar = threading.Event()
        self._reabrir = threading.Event()
        self._thread: threading.Thread | None = None
        self._peticiones: dict[str, float] = {}
        self._cuadro: Cuadro | None = None
        self._seq = 0

    def suscribir(self, nombre: str) -> _Suscriptor:
        if not nombre.strip():
            raise ValueError("nombre no puede estar vacío")
        with self._cond:
            if nombre in self._peticiones:
                raise ValueError(f"ya existe un suscriptor llamado {nombre!r}")
            self._peticiones[nombre] = 0.0
        return _Suscriptor(self, nombre)

    def iniciar(self) -> None:
        """Arranca el hilo del servicio. Idempotente; se puede reiniciar tras detener()."""
        with self._cond:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._despertar.clear()
            self._thread = threading.Thread(
                target=self._bucle, name="dark-vision", daemon=True
            )
            self._thread.start()

    def detener(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._despertar.set()
        with self._cond:
            self._cond.notify_all()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("El hilo de VisionService no se detuvo a tiempo")

    # --- uso interno por los suscriptores -------------------------------

    def _cambiar_fps(self, nombre: str, fps: float) -> None:
        with self._cond:
            if nombre not in self._peticiones:
                return
            self._peticiones[nombre] = fps
        self._despertar.set()

    def _quitar(self, nombre: str) -> None:
        with self._cond:
            self._peticiones.pop(nombre, None)
            self._cond.notify_all()
        self._despertar.set()

    def reabrir(self) -> None:
        """Suelta y vuelve a abrir el dispositivo (tras una suspensión del equipo el manejador queda muerto)."""
        self._reabrir.set()
        self._despertar.set()

    def _descartar_cuadro(self) -> None:
        with self._cond:
            self._cuadro = None

    def _publicar(self, imagen: np.ndarray) -> None:
        with self._cond:
            self._seq += 1
            self._cuadro = Cuadro(self._seq, time.monotonic(), imagen)
            self._cond.notify_all()

    # --- modo de captura --------------------------------------------------

    def _fijar_modo(self, camara) -> None:
        """Pide el modo al driver y registra lo que DEVOLVIÓ.

        El orden importa: el fourcc va ANTES del tamaño, porque hay drivers que
        ignoran la petición de codificador si ya cerraron un modo YUY2 por
        defecto. Y se registra lo devuelto, no lo pedido —aun así DirectShow
        suele mentir en `CAP_PROP_FPS` devolviendo -1, así que el fps real sale
        del contador de cuadros entregados de `_bucle`—.

        Un `set`/`get` que falle no puede tumbar el hilo de visión: se loguea y
        se sigue con el modo que el driver ya traía puesto.
        """
        try:
            if self.codificador:
                camara.set(
                    cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.codificador[:4])
                )
            if self.ancho:
                camara.set(cv2.CAP_PROP_FRAME_WIDTH, self.ancho)
            if self.alto:
                camara.set(cv2.CAP_PROP_FRAME_HEIGHT, self.alto)
            if self.fps:
                camara.set(cv2.CAP_PROP_FPS, self.fps)
            devuelto = (
                int(camara.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(camara.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                float(camara.get(cv2.CAP_PROP_FPS)),
            )
            self.modo_efectivo = devuelto
            LOGGER.info(
                "Cámara %s: pedido %s %dx%d@%.0f -> el driver dice %dx%d@%.1f",
                self.camera_index,
                self.codificador or "defecto",
                self.ancho,
                self.alto,
                self.fps,
                *devuelto,
            )
        except Exception as exc:
            LOGGER.warning(
                "No se pudo fijar/leer el modo de la cámara %s (%s); "
                "se usa el que trae el driver por defecto.",
                self.camera_index,
                exc,
            )

    def _bucle(self) -> None:
        camara = None
        ultimo_intento = float("-inf")
        entregados = 0
        ventana = time.monotonic()
        try:
            while not self._stop.is_set():
                self._despertar.clear()
                if self._reabrir.is_set():
                    self._reabrir.clear()
                    if camara is not None:
                        camara.release()
                        camara = None
                        self._descartar_cuadro()
                        LOGGER.info("Cámara %s: se reabre a petición.", self.camera_index)
                    ultimo_intento = float("-inf")
                with self._cond:
                    objetivo = max(self._peticiones.values(), default=0.0)

                if objetivo <= 0:
                    # Sin consumidores: la cámara se libera (y su luz se apaga).
                    if camara is not None:
                        camara.release()
                        camara = None
                        self._descartar_cuadro()
                        # Un número de entrega viejo no puede leerse como vivo.
                        self.fps_entregados = 0.0
                        LOGGER.info("Cámara %s liberada: sin consumidores.", self.camera_index)
                    self._despertar.wait(0.5)
                    continue

                if camara is None:
                    ahora = time.monotonic()
                    if ahora - ultimo_intento < CAMERA_RETRY_SECONDS:
                        self._despertar.wait(0.1)
                        continue
                    ultimo_intento = ahora
                    candidata = cv2.VideoCapture(self.camera_index)
                    if not candidata.isOpened():
                        candidata.release()
                        LOGGER.warning(
                            "No se pudo abrir la cámara %s; se reintentará en %.1f s.",
                            self.camera_index,
                            CAMERA_RETRY_SECONDS,
                        )
                        self._despertar.wait(0.1)
                        continue
                    candidata.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    self._fijar_modo(candidata)
                    camara = candidata
                    LOGGER.info("Cámara %s disponible.", self.camera_index)
                    continue

                if objetivo >= UMBRAL_LECTURA_CONTINUA:
                    ok, imagen = camara.read()
                else:
                    # Ritmo lento: esperar el periodo, pero despertar si alguien
                    # cambia su petición o se detiene el servicio.
                    if self._despertar.wait(1.0 / objetivo):
                        continue
                    for _ in range(_GRABS_DE_LIMPIEZA):
                        camara.grab()
                    ok, imagen = camara.retrieve()

                if not ok or imagen is None:
                    LOGGER.warning("La cámara dejó de entregar frames; se reabrirá.")
                    camara.release()
                    camara = None
                    self._descartar_cuadro()
                    continue

                self._publicar(imagen)
                entregados += 1
                ahora = time.monotonic()
                if objetivo < UMBRAL_LECTURA_CONTINUA:
                    # Con vigilancia lenta el número no dice nada del modo de
                    # captura: lo que manda aquí es el ritmo del gate, no el del
                    # driver. Se vuelve a abrir la ventana.
                    entregados = 0
                    ventana = ahora
                elif ahora - ventana >= FPS_VENTANA_SEG:
                    self.fps_entregados = entregados / (ahora - ventana)
                    LOGGER.info(
                        "Cámara %s entrega %.1f fps (%d cuadros en %.1f s).",
                        self.camera_index,
                        self.fps_entregados,
                        entregados,
                        ahora - ventana,
                    )
                    entregados = 0
                    ventana = ahora
        except Exception:
            LOGGER.exception("VisionService terminó por un error.")
        finally:
            if camara is not None:
                camara.release()
            self._descartar_cuadro()
            with self._cond:
                self._cond.notify_all()


# ---------------------------------------------------------------------------
# Helpers de rostro (sin cambios respecto a la Fase B)
# ---------------------------------------------------------------------------


class _Landmark(Protocol):
    x: float
    y: float


class _FaceResult(Protocol):
    face_landmarks: Sequence[Sequence[_Landmark]]


class _FaceLandmarker(Protocol):
    def detect(self, image: mp.Image) -> _FaceResult: ...

    def close(self) -> None: ...


class _RecognitionModel(Protocol):
    model_file: str
    session: object

    def get_feat(self, image: np.ndarray) -> np.ndarray: ...


_R_EYE = [33, 160, 158, 133, 153, 144]
_L_EYE = [362, 385, 387, 263, 373, 380]
_ARCFACE_DST = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)


def _to_mp(frame: np.ndarray) -> mp.Image:
    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def _landmarks_5(
    landmarks: Sequence[_Landmark], width: int, height: int
) -> np.ndarray:
    def point(index: int) -> np.ndarray:
        return np.array(
            [landmarks[index].x * width, landmarks[index].y * height],
            dtype=np.float32,
        )

    eye_a = (point(33) + point(133)) / 2
    eye_b = (point(362) + point(263)) / 2
    nose = point(1)
    mouth_a, mouth_b = point(61), point(291)
    return np.stack([eye_a, eye_b, nose, mouth_a, mouth_b])


def _face_embedding(
    rec: _RecognitionModel,
    frame: np.ndarray,
    landmarks: Sequence[_Landmark],
) -> np.ndarray | None:
    height, width = frame.shape[:2]
    points = _landmarks_5(landmarks, width, height)
    transform, _ = cv2.estimateAffinePartial2D(
        points, _ARCFACE_DST, method=cv2.LMEDS
    )
    if transform is None:
        return None
    aligned = cv2.warpAffine(frame, transform, (112, 112), borderValue=0.0)
    embedding = rec.get_feat(aligned).flatten()
    return embedding / (np.linalg.norm(embedding) + 1e-9)


def _eye_ratio(
    landmarks: Sequence[_Landmark],
    indices: Sequence[int],
    width: int,
    height: int,
) -> float:
    points = [
        np.array(
            [landmarks[index].x * width, landmarks[index].y * height]
        )
        for index in indices
    ]
    return float(
        (
            np.linalg.norm(points[1] - points[5])
            + np.linalg.norm(points[2] - points[4])
        )
        / (2 * np.linalg.norm(points[0] - points[3]) + 1e-9)
    )


class _BlinkDetector:
    def __init__(self) -> None:
        self.history: deque[float] = deque(maxlen=45)
        self.closed = False
        self.blinks = 0

    def update(self, landmarks: list, width: int, height: int) -> int:
        ear = (
            _eye_ratio(landmarks, _R_EYE, width, height)
            + _eye_ratio(landmarks, _L_EYE, width, height)
        ) / 2
        self.history.append(ear)
        if len(self.history) < 15:
            return self.blinks
        baseline = float(np.percentile(self.history, 80))
        if not self.closed and ear < baseline * 0.72:
            self.closed = True
        elif self.closed and ear > baseline * 0.85:
            self.closed = False
            self.blinks += 1
        return self.blinks