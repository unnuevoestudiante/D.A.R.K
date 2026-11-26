"""Puerta de acceso facial headless basada en los prototipos locales."""
from __future__ import annotations

import os

# Fijar los hilos antes de cargar NumPy, OpenCV o ONNX Runtime.
THREADS = 2
os.environ["OMP_NUM_THREADS"] = str(THREADS)
os.environ["OPENBLAS_NUM_THREADS"] = str(THREADS)
os.environ["MKL_NUM_THREADS"] = str(THREADS)

import logging
import math
import random
import threading
import time
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
import numpy as np
import onnxruntime as ort
import psutil
from insightface.app import FaceAnalysis
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from face_proto import MODEL_URL, align, embed, landmarks_5

LOGGER = logging.getLogger(__name__)

THRESHOLD = 0.4
IDLE_FPS = 2.0
VERIFY_INTERVAL = 0.25
VERIFY_TIMEOUT = 10.0
LIVE_TIMEOUT = 8.0
DENIED_SECONDS = 3.0
CAMERA_RETRY_SECONDS = 2.0
FACE_LOST_SECONDS = 2.0
WAVE_FACE_LOST_SECONDS = 4.0

IDLE = "IDLE"
VERIFY = "VERIFY"
LIVENESS = "LIVENESS"
GRANTED = "GRANTED"
DENIED = "DENIED"
LOCKED = "LOCKED"

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FACE_MODEL_PATH = _PROJECT_ROOT / "face_landmarker.task"
_FACE_DB_PATH = _PROJECT_ROOT / "faces_db.npz"
_HAND_MODEL_PATH = _PROJECT_ROOT / "hand_landmarker.task"
_HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

_R_EYE = [33, 160, 158, 133, 153, 144]
_L_EYE = [362, 385, 387, 263, 373, 380]


def _ensure_model(path: Path, url: str) -> None:
    if not path.is_file():
        LOGGER.info("Descargando modelo de visión: %s", path)
        urllib.request.urlretrieve(url, path)


def _load_database() -> dict[str, np.ndarray]:
    if not _FACE_DB_PATH.is_file():
        raise FileNotFoundError(
            f"No existe la base facial {_FACE_DB_PATH}. "
            "Registra primero una cara con face_proto.py enroll <nombre>."
        )
    with np.load(_FACE_DB_PATH, allow_pickle=True) as database:
        embeddings = {name: np.asarray(database[name]) for name in database.files}
    if not embeddings:
        raise ValueError(f"La base facial está vacía: {_FACE_DB_PATH}")
    return embeddings


def _load_models() -> tuple[vision.FaceLandmarker, vision.HandLandmarker, object]:
    _ensure_model(_FACE_MODEL_PATH, MODEL_URL)
    _ensure_model(_HAND_MODEL_PATH, _HAND_MODEL_URL)

    app = FaceAnalysis(
        name="buffalo_s",
        allowed_modules=["detection", "recognition"],
        providers=["CPUExecutionProvider"],
    )
    app.prepare(ctx_id=-1)
    rec = app.models["recognition"]
    try:
        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = THREADS
        session_options.inter_op_num_threads = 1
        rec.session = ort.InferenceSession(
            rec.model_file,
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
    except Exception:
        LOGGER.warning(
            "No se pudo limitar los hilos de ArcFace; se conserva la sesión "
            "creada por InsightFace.",
            exc_info=True,
        )

    face = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(_FACE_MODEL_PATH)
            ),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
        )
    )
    hand = vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(_HAND_MODEL_PATH)
            ),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
            min_hand_detection_confidence=0.4,
            min_hand_presence_confidence=0.4,
            min_tracking_confidence=0.4,
        )
    )
    return face, hand, rec


def _to_mp(frame: np.ndarray) -> mp.Image:
    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def _face_embedding(rec: object, frame: np.ndarray, landmarks: list) -> np.ndarray | None:
    height, width = frame.shape[:2]
    aligned = align(frame, landmarks_5(landmarks, width, height))
    return None if aligned is None else embed(rec, aligned)


def _eye_ratio(landmarks: list, indices: list[int], width: int, height: int) -> float:
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


def _palm_open(hand_landmarks: list) -> bool:
    wrist = np.array([hand_landmarks[0].x, hand_landmarks[0].y])
    extended = 0
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        tip_distance = np.linalg.norm(
            np.array([hand_landmarks[tip].x, hand_landmarks[tip].y]) - wrist
        )
        pip_distance = np.linalg.norm(
            np.array([hand_landmarks[pip].x, hand_landmarks[pip].y]) - wrist
        )
        if tip_distance > pip_distance * 1.05:
            extended += 1
    return extended >= 3


class _WaveDetector:
    def __init__(self, window: float = 2.0, threshold: float = 0.03) -> None:
        self.samples: deque[tuple[float, float, bool]] = deque()
        self.window = window
        self.threshold = threshold
        self.last_seen = 0.0
        self.reversals = 0

    def update(self, now: float, hand_landmarks: list | None) -> bool:
        if hand_landmarks is not None:
            self.last_seen = now
            center_x = float(np.mean([point.x for point in hand_landmarks]))
            self.samples.append((now, center_x, _palm_open(hand_landmarks)))
        elif now - self.last_seen > 0.6:
            self.samples.clear()
            self.reversals = 0
            return False

        while self.samples and now - self.samples[0][0] > self.window:
            self.samples.popleft()
        if len(self.samples) < 6:
            return False

        positions = [x for _, x, _ in self.samples]
        open_fraction = float(np.mean([opened for _, _, opened in self.samples]))
        direction, extreme, reversals = 0, positions[0], 0
        for position in positions[1:]:
            if direction == 0:
                if position - extreme > self.threshold:
                    direction, extreme = 1, position
                elif extreme - position > self.threshold:
                    direction, extreme = -1, position
            elif direction == 1:
                if position > extreme:
                    extreme = position
                elif extreme - position > self.threshold:
                    direction, extreme, reversals = -1, position, reversals + 1
            elif position < extreme:
                extreme = position
            elif position - extreme > self.threshold:
                direction, extreme, reversals = 1, position, reversals + 1
        self.reversals = reversals
        return reversals >= 3 and open_fraction >= 0.5


class AccessGate:
    """Reconoce una cara y valida vivacidad sin crear ventanas de OpenCV."""

    def __init__(
        self,
        on_granted: Callable[[str], None] | None = None,
        on_locked: Callable[[str], None] | None = None,
        camera_index: int = 0,
        threshold: float = THRESHOLD,
        idle_fps: float = IDLE_FPS,
    ) -> None:
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold debe estar entre 0 y 1")
        if not math.isfinite(idle_fps) or idle_fps <= 0:
            raise ValueError("idle_fps debe ser mayor que 0")

        self.on_granted = on_granted
        self.on_locked = on_locked
        self.camera_index = camera_index
        self.threshold = threshold
        self.idle_fps = idle_fps
        self.acceso_concedido = threading.Event()

        self._state = IDLE
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_error: Exception | None = None
        self._locked_flow = False
        self._face: vision.FaceLandmarker | None = None
        self._hand: vision.HandLandmarker | None = None
        self._rec = None
        self._last_hand_timestamp = 0

    @property
    def estado(self) -> str:
        with self._state_lock:
            return self._state

    def iniciar(self) -> None:
        with self._state_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._worker_error = None
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._worker,
                name="dark-access-gate",
                daemon=True,
            )
            self._thread.start()

    def esperar_acceso(self, timeout: float | None = None) -> bool:
        if timeout is not None and timeout < 0:
            raise ValueError("timeout no puede ser negativo")
        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if self.acceso_concedido.is_set():
                return True
            with self._state_lock:
                error = self._worker_error
            if error is not None:
                raise RuntimeError("AccessGate no pudo inicializarse") from error
            if self._stop_event.is_set():
                return False
            remaining = (
                None if deadline is None else max(0.0, deadline - time.monotonic())
            )
            if remaining == 0.0:
                return False
            self.acceso_concedido.wait(
                timeout=0.1 if remaining is None else min(0.1, remaining)
            )

    def bloquear(self, motivo: str) -> None:
        if not motivo.strip():
            raise ValueError("motivo no puede estar vacío")
        self.acceso_concedido.clear()
        with self._state_lock:
            self._locked_flow = True
            self._state = LOCKED
        LOGGER.info("Acceso bloqueado: %s", motivo)
        self._notify(self.on_locked, motivo, "on_locked")

    def desbloquear(self) -> None:
        with self._state_lock:
            self._locked_flow = False
            self._state = GRANTED
        self.acceso_concedido.set()
        LOGGER.info("Acceso desbloqueado externamente.")

    def detener(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("El hilo de AccessGate no se detuvo a tiempo")

    def _notify(
        self,
        callback: Callable[[str], None] | None,
        value: str,
        callback_name: str,
    ) -> None:
        if callback is None:
            return
        try:
            callback(value)
        except Exception:
            LOGGER.exception("Falló el callback %s", callback_name)

    def _set_state(self, state: str, detail: str = "") -> None:
        with self._state_lock:
            previous = self._state
            self._state = state
        if previous != state or detail:
            LOGGER.info("%s -> %s %s", previous, state, detail)

    def _grant(self, name: str) -> None:
        with self._state_lock:
            self._locked_flow = False
            self._state = GRANTED
        self.acceso_concedido.set()
        LOGGER.info("Acceso concedido a %s.", name)
        self._notify(self.on_granted, name, "on_granted")

    def _worker(self) -> None:
        camera = None
        try:
            cv2.setNumThreads(THREADS)

            process = psutil.Process(os.getpid())
            cpu_count = max(psutil.cpu_count() or 1, 1)
            process.cpu_percent(None)
            cpu_history: dict[str, list[float]] = defaultdict(list)
            fps_history: dict[str, list[float]] = defaultdict(list)
            fps_window: deque[float] = deque(maxlen=30)
            last_loop = time.perf_counter()
            last_cpu_time = time.monotonic()
            current_cpu = 0.0
            last_camera_attempt = 0.0

            state_started = time.monotonic()
            last_face_time = state_started
            last_embedding_time = 0.0
            presence_frames = 0
            matches: deque[str | None] = deque(maxlen=5)
            live_matches: deque[bool] = deque(maxlen=4)
            who = ""
            score = 0.0
            challenge = ""
            blink_detector: _BlinkDetector | None = None
            wave_detector: _WaveDetector | None = None

            while not self._stop_event.is_set():
                state = self.estado
                if state == GRANTED:
                    if camera is not None:
                        camera.release()
                        camera = None
                        LOGGER.info("Cámara liberada: no se necesita mientras hay acceso.")
                    self._stop_event.wait(0.1)
                    continue

                if self._face is None or self._hand is None or self._rec is None:
                    database = _load_database()
                    self._face, self._hand, self._rec = _load_models()
                state = self.estado
                if state == GRANTED:
                    continue
                face = self._face
                hand = self._hand
                rec = self._rec
                if face is None or hand is None or rec is None:
                    raise RuntimeError("Los modelos de AccessGate no se cargaron")

                now = time.monotonic()
                if camera is None:
                    if now - last_camera_attempt < CAMERA_RETRY_SECONDS:
                        self._stop_event.wait(0.1)
                        continue
                    last_camera_attempt = now
                    candidate = cv2.VideoCapture(self.camera_index)
                    if not candidate.isOpened():
                        candidate.release()
                        LOGGER.warning(
                            "No se pudo abrir la cámara %s; se reintentará en %.1f s.",
                            self.camera_index,
                            CAMERA_RETRY_SECONDS,
                        )
                        self._stop_event.wait(0.1)
                        continue
                    candidate.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    camera = candidate
                    LOGGER.info("Cámara %s disponible.", self.camera_index)
                    continue

                if state in (IDLE, LOCKED):
                    if self._stop_event.wait(1.0 / self.idle_fps):
                        break
                    for _ in range(3):
                        camera.grab()
                    ok, frame = camera.retrieve()
                else:
                    ok, frame = camera.read()
                if not ok or frame is None:
                    LOGGER.warning("La cámara dejó de entregar frames; se reabrirá.")
                    camera.release()
                    camera = None
                    continue

                now = time.monotonic()
                height, width = frame.shape[:2]
                landmarks = None
                if state in (IDLE, LOCKED, VERIFY, LIVENESS):
                    result = face.detect(_to_mp(frame))
                    if result.face_landmarks:
                        landmarks = result.face_landmarks[0]
                        last_face_time = now

                if state in (IDLE, LOCKED):
                    presence_frames = presence_frames + 1 if landmarks else 0
                    if presence_frames >= 2:
                        matches.clear()
                        live_matches.clear()
                        presence_frames = 0
                        state = VERIFY
                        state_started = now
                        self._set_state(VERIFY)

                elif state == VERIFY:
                    if landmarks is None and now - last_face_time > FACE_LOST_SECONDS:
                        state = DENIED
                        state_started = now
                        self._set_state(DENIED, "(sin rostro)")
                    elif landmarks is not None and now - last_embedding_time >= VERIFY_INTERVAL:
                        last_embedding_time = now
                        embedding = _face_embedding(rec, frame, landmarks)
                        if embedding is not None:
                            name, score = max(
                                (
                                    (candidate_name, float(np.dot(embedding, vector)))
                                    for candidate_name, vector in database.items()
                                ),
                                key=lambda item: item[1],
                            )
                            matches.append(name if score >= self.threshold else None)
                            counts: dict[str, int] = defaultdict(int)
                            for match in matches:
                                if match is not None:
                                    counts[match] += 1
                            if counts and max(counts.values()) >= 3:
                                who = max(counts, key=counts.get)
                                challenge = random.choice(("blink", "wave"))
                                blink_detector = _BlinkDetector()
                                wave_detector = _WaveDetector()
                                live_matches.clear()
                                state = LIVENESS
                                state_started = now
                                self._set_state(
                                    LIVENESS,
                                    f"identidad={who} reto={challenge}",
                                )
                    if state == VERIFY and now - state_started > VERIFY_TIMEOUT:
                        state = DENIED
                        state_started = now
                        self._set_state(DENIED, "(no reconocido)")

                elif state == LIVENESS:
                    lost_timeout = (
                        WAVE_FACE_LOST_SECONDS if challenge == "wave"
                        else FACE_LOST_SECONDS
                    )
                    if now - last_face_time > lost_timeout:
                        state = DENIED
                        state_started = now
                        self._set_state(DENIED, "(se perdió el rostro)")
                    else:
                        passed = False
                        if challenge == "blink" and landmarks is not None:
                            passed = blink_detector.update(
                                landmarks, width, height
                            ) >= 2
                        elif challenge == "wave":
                            timestamp = max(
                                int(time.perf_counter() * 1000),
                                self._last_hand_timestamp + 1,
                            )
                            self._last_hand_timestamp = timestamp
                            hand_result = hand.detect_for_video(
                                _to_mp(frame), timestamp
                            )
                            hand_landmarks = (
                                hand_result.hand_landmarks[0]
                                if hand_result.hand_landmarks else None
                            )
                            passed = wave_detector.update(now, hand_landmarks)

                        if landmarks is not None and now - last_embedding_time >= 0.5:
                            last_embedding_time = now
                            embedding = _face_embedding(rec, frame, landmarks)
                            if embedding is not None:
                                live_name, live_score = max(
                                    (
                                        (candidate_name, float(np.dot(embedding, vector)))
                                        for candidate_name, vector in database.items()
                                    ),
                                    key=lambda item: item[1],
                                )
                                score = live_score
                                live_matches.append(
                                    live_name == who and live_score >= self.threshold
                                )
                        if len(live_matches) >= 3 and sum(live_matches) < 2:
                            state = DENIED
                            state_started = now
                            self._set_state(DENIED, "(cambió la persona)")
                        elif passed:
                            self._grant(who)
                            state = GRANTED
                        elif now - state_started > LIVE_TIMEOUT:
                            state = DENIED
                            state_started = now
                            self._set_state(DENIED, "(reto no superado)")

                elif state == DENIED and now - state_started >= DENIED_SECONDS:
                    with self._state_lock:
                        return_to_lock = self._locked_flow
                    state = LOCKED if return_to_lock else IDLE
                    presence_frames = 0
                    last_face_time = now
                    state_started = now
                    self._set_state(state)

                loop_time = time.perf_counter()
                fps_window.append(1.0 / max(loop_time - last_loop, 1e-6))
                last_loop = loop_time
                if now - last_cpu_time >= 1.0:
                    current_cpu = process.cpu_percent(None) / cpu_count
                    last_cpu_time = now
                    cpu_history[state].append(current_cpu)
                    fps_history[state].append(float(np.mean(fps_window)))

            LOGGER.info("=== Promedio AccessGate por estado ===")
            for measured_state, samples in cpu_history.items():
                LOGGER.info(
                    "%s CPU %.1f%% FPS %.1f (%s muestras)",
                    measured_state,
                    float(np.mean(samples)),
                    float(np.mean(fps_history[measured_state])),
                    len(samples),
                )
        except Exception as error:
            with self._state_lock:
                self._worker_error = error
            LOGGER.exception("AccessGate terminó por un error.")
        finally:
            if camera is not None:
                camera.release()
            if self._face is not None:
                self._face.close()
            if self._hand is not None:
                self._hand.close()
            self._face = None
            self._hand = None
            self._rec = None
