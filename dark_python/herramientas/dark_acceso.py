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
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from acceso.config import (
    AUSENCIA_SEG,
    BOOT_TIMEOUT,
    CAMERA_INDEX,
    IDLE_FPS,
    THRESHOLD,
    WATCH_ARM_SEG,
)
from acceso import biometria
from acceso.config import (
    PASO_TOLERANCIA_SEG,
    TOPE_AUSENCIA_SEG,
    VENTANA_FALSO_SEG,
)
from acceso.tolerancia import ToleranciaAusencia
from acceso.reconocedor_facial import ReconocedorSFace, asegurar_modelo
from herramientas.vision import (
    CAMERA_RETRY_SECONDS,
    FPS_CONTINUO,
    VisionService,
    _BlinkDetector,
    _FaceLandmarker,
    _RecognitionModel,
    _face_embedding,
    _to_mp,
)

LOGGER = logging.getLogger(__name__)

# Reexportado historico: `probar_dark_acceso.py` y las pruebas siguen leyendo
# estos nombres de aqui, pero el valor vive en acceso/config.py.
BOOT_ACCESS_TIMEOUT_SECONDS = BOOT_TIMEOUT

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
VERIFY_INTERVAL = 0.25
VERIFY_TIMEOUT = 10.0
LIVE_TIMEOUT = 8.0
DENIED_SECONDS = 3.0
# CAMERA_RETRY_SECONDS se importa de herramientas.vision: la cámara ya no la
# abre este archivo, pero el nombre se conserva por compatibilidad.
FACE_LOST_SECONDS = 2.0
# Tope de cuánto pueden prolongar las manos la presencia pasado el último
# rostro visto (p. ej. gestos con las manos tapando la cara). Es relativo al
# último rostro, así que no se encadena: pasado el tope, bloquea igual.
MANOS_EXTIENDEN_SEG = 15.0
# Falla cerrado: si la cámara que ya estaba entregando cuadros deja de hacerlo
# (desconectada, driver colgado), el acceso se retira pasado este tiempo. Se usa
# el mayor entre esto y 3 periodos de vigilancia, para no confundir el ritmo
# lento de `idle_fps` con una cámara muerta.
SIN_CAMARA_SEG = 5.0

IDLE = "IDLE"
VERIFY = "VERIFY"
LIVENESS = "LIVENESS"
GRANTED = "GRANTED"
DENIED = "DENIED"
LOCKED = "LOCKED"
WATCH = "WATCH"

def _ultima_presencia(cara_t: float, mano_t: float, tope: float) -> float:
    """Instante de la última presencia: el rostro, o una mano posterior con tope.

    Una mano vista después del último rostro prolonga la presencia, pero nunca
    más de ``tope`` segundos pasado ese rostro. Con ``mano_t`` anterior al
    rostro (o 0.0 = ninguna mano) manda el rostro.
    """
    return max(cara_t, min(mano_t, cara_t + tope))


def _ensure_model(path: Path, url: str) -> None:
    if not path.is_file():
        LOGGER.info("Descargando modelo de visión: %s", path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporal = path.with_name(path.name + ".part")
        urllib.request.urlretrieve(url, temporal)
        os.replace(temporal, path)


def _load_database() -> dict[str, np.ndarray]:
    """Rostros registrados con consentimiento (ver acceso/biometria.py)."""
    return biometria.cargar_base(solo_activas=True)


def _load_models() -> tuple[_FaceLandmarker, _RecognitionModel]:
    modelo = biometria.ruta_modelo()
    _ensure_model(modelo, MODEL_URL)

    rec = ReconocedorSFace(asegurar_modelo(biometria.ruta_modelo().parent), hilos=THREADS)

    face = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=str(modelo)
            ),
            running_mode=vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
        )
    )
    return face, rec


class AccessGate:
    """Reconoce una cara y valida vivacidad sin crear ventanas de OpenCV.

    La cámara ya no la abre el gate: la entrega un ``VisionService``. Si no se
    pasa uno, el gate crea el suyo (y lo detiene al detenerse), así que el uso
    anterior ``AccessGate(...)`` sigue funcionando igual. Si se pasa uno
    compartido, el gate solo se suscribe y ``camera_index`` se ignora (manda el
    del servicio); quien lo creó es quien lo detiene.
    """

    def __init__(
        self,
        on_granted: Callable[[str], None] | None = None,
        on_locked: Callable[[str], None] | None = None,
        camera_index: int = CAMERA_INDEX,
        threshold: float = THRESHOLD,
        idle_fps: float = IDLE_FPS,
        ausencia_seg: float = AUSENCIA_SEG,
        watch_arm_seg: float = WATCH_ARM_SEG,
        servicio: VisionService | None = None,
        presencia_manos: Callable[[], float] | None = None,
        manos_extienden_seg: float = MANOS_EXTIENDEN_SEG,
        sin_camara_seg: float = SIN_CAMARA_SEG,
        presencia_teclado: Callable[[], float] | None = None,
    ) -> None:
        if not math.isfinite(sin_camara_seg) or sin_camara_seg <= 0:
            raise ValueError("sin_camara_seg debe ser mayor que 0")
        if not math.isfinite(manos_extienden_seg) or manos_extienden_seg < 0:
            raise ValueError("manos_extienden_seg no puede ser negativo")
        if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold debe estar entre 0 y 1")
        if not math.isfinite(idle_fps) or idle_fps <= 0:
            raise ValueError("idle_fps debe ser mayor que 0")
        if not math.isfinite(ausencia_seg) or ausencia_seg <= 0:
            raise ValueError("ausencia_seg debe ser mayor que 0")
        if not math.isfinite(watch_arm_seg) or watch_arm_seg < 0:
            raise ValueError("watch_arm_seg no puede ser negativo")

        self.on_granted = on_granted
        self.on_locked = on_locked
        self.camera_index = camera_index
        self.threshold = threshold
        self.idle_fps = idle_fps
        # Vigilancia: segundos sin rostro antes de retirar el acceso y
        # margen anti-vaiven tras cada concesion.
        self.ausencia_seg = ausencia_seg
        self.watch_arm_seg = watch_arm_seg
        # Opcional: función sin argumentos que devuelve el time.monotonic() de
        # la última mano vista (p. ej. ``lambda: motor.ultima_mano_t``). Con ella,
        # tener las manos a la vista cuenta como presencia (con tope) y los
        # gestos que tapan la cara no disparan el bloqueo por ausencia.
        self.presencia_manos = presencia_manos
        self.manos_extienden_seg = manos_extienden_seg
        self.sin_camara_seg = sin_camara_seg
        # Opcional: monotonic de la última tecla o movimiento de mouse
        # (acceso/entrada.py). Escribir con la cabeza girada es estar delante:
        # cuenta como presencia. No tocar nada NO es ausencia por sí solo.
        self.presencia_teclado = presencia_teclado
        # Falsos bloqueos y tolerancia acumulativa (acceso/tolerancia.py).
        self._tolerancia = ToleranciaAusencia(
            ausencia_seg,
            ventana_falso_seg=VENTANA_FALSO_SEG,
            paso_seg=PASO_TOLERANCIA_SEG,
            tope_total_seg=TOPE_AUSENCIA_SEG,
        )
        #: La última concesión cerró un falso bloqueo (no hubo ausencia real).
        self.ultimo_bloqueo_falso = False
        self.acceso_concedido = threading.Event()

        self._servicio_propio = servicio is None
        self._servicio = (
            VisionService(camera_index) if servicio is None else servicio
        )

        self._state = IDLE
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._worker_error: Exception | None = None
        self._locked_flow = False
        self._watch_started_at = 0.0
        # El reto de parpadeo solo se exige la primera vez; tras un re-bloqueo
        # la identidad ya quedo validada y la cara reconocida reabre sola.
        self._rostro_validado = False
        self._face: _FaceLandmarker | None = None
        self._rec: _RecognitionModel | None = None

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
            self._servicio.iniciar()
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
            self._watch_started_at = time.monotonic()
        self.acceso_concedido.set()
        LOGGER.info("Acceso desbloqueado externamente.")
        # Notificar es lo que hace que la concesión exista para el núcleo: su
        # Event propio solo lo setea on_granted. Sin _rostro_validado, porque la
        # contraseña no supera el reto de parpadeo y la próxima apertura facial
        # debe seguir exigiéndolo.
        self._notify(self.on_granted, "contraseña", "on_granted")

    def detener(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("El hilo de AccessGate no se detuvo a tiempo")
        if self._servicio_propio:
            self._servicio.detener(timeout)

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
        falso = self._tolerancia.al_conceder(time.monotonic())
        self.ultimo_bloqueo_falso = falso
        if falso:
            LOGGER.info(
                "Falso bloqueo (estaba delante): no cuenta como ausencia; "
                "el próximo bloqueo espera %.0f s.", self._tolerancia.umbral_seg)
        with self._state_lock:
            self._locked_flow = False
            self._state = GRANTED
            self._watch_started_at = time.monotonic()
            self._rostro_validado = True
        self.acceso_concedido.set()
        LOGGER.info("Acceso concedido a %s.", name)
        self._notify(self.on_granted, name, "on_granted")

    def _retirar_acceso(self, motivo: str) -> None:
        """El watcher retira un acceso ya concedido y arma la re-verificación."""
        with self._state_lock:
            if self._state not in (GRANTED, WATCH):
                return
            self._locked_flow = True
            self._state = LOCKED
        self.acceso_concedido.clear()
        # Solo la ausencia puede ser un falso bloqueo (la cámara caída no).
        if motivo == "ausencia":
            self._tolerancia.al_bloquear(time.monotonic())
        LOGGER.info("Acceso retirado: %s", motivo)
        self._notify(self.on_locked, motivo, "on_locked")

    def _worker(self) -> None:
        suscriptor = None
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

            state_started = time.monotonic()
            last_face_time = state_started
            last_embedding_time = 0.0
            presence_frames = 0
            matches: deque[str | None] = deque(maxlen=5)
            live_matches: deque[bool] = deque(maxlen=4)
            who = ""
            score = 0.0
            blink_detector: _BlinkDetector | None = None
            # Falla cerrado sin romper el desbloqueo por contraseña: solo se retira
            # el acceso por cámara muerta si ESTA concesión ya vio cuadros. Si el
            # acceso llegó por contraseña con la cámara rota, nunca los vio y se
            # conserva (esa es justo la salida de emergencia).
            last_frame_time = state_started
            camara_viva_en_acceso = False

            suscriptor = self._servicio.suscribir("acceso")

            while not self._stop_event.is_set():
                state = self.estado
                if not self.acceso_concedido.is_set():
                    camara_viva_en_acceso = False
                if self.acceso_concedido.is_set() and state != GRANTED:
                    state = GRANTED
                    self._set_state(GRANTED, "(acceso externo)")
                if state == GRANTED:
                    # Con acceso vivo la máquina se queda en WATCH: presencia
                    # barata y retiro por ausencia.
                    state = WATCH
                    self._set_state(WATCH)
                if self._face is None or self._rec is None:
                    database = _load_database()
                    self._face, self._rec = _load_models()
                face = self._face
                rec = self._rec
                if face is None or rec is None:
                    raise RuntimeError("Los modelos de AccessGate no se cargaron")

                # Vigilancia pasiva (IDLE/WATCH) a idle_fps; LOCKED, VERIFY,
                # LIVENESS y DENIED amplificados: lectura continua como al
                # inicio. Cámara, reintentos y reapertura son del servicio.
                suscriptor.fijar_fps(
                    self.idle_fps if state in (IDLE, WATCH) else FPS_CONTINUO
                )
                cuadro = suscriptor.siguiente(timeout=0.5)
                if cuadro is None:
                    if (
                        state == WATCH
                        and camara_viva_en_acceso
                        and time.monotonic() - last_frame_time
                        >= max(self.sin_camara_seg, 3.0 / self.idle_fps)
                    ):
                        self._retirar_acceso("camara")
                        presence_frames = 0
                    continue
                frame = cuadro.imagen

                now = time.monotonic()
                last_frame_time = now
                if self.acceso_concedido.is_set():
                    camara_viva_en_acceso = True
                height, width = frame.shape[:2]
                landmarks = None
                if state in (IDLE, LOCKED, VERIFY, LIVENESS, WATCH):
                    result = face.detect(_to_mp(frame))
                    if result.face_landmarks:
                        landmarks = result.face_landmarks[0]
                        last_face_time = now

                if state == WATCH:
                    ultima_presencia = last_face_time
                    if self.presencia_manos is not None:
                        try:
                            ultima_presencia = _ultima_presencia(
                                last_face_time,
                                float(self.presencia_manos()),
                                self.manos_extienden_seg,
                            )
                        except Exception:
                            LOGGER.exception("Falló presencia_manos; se ignora.")
                    if self.presencia_teclado is not None:
                        try:
                            ultima_presencia = max(
                                ultima_presencia, float(self.presencia_teclado()))
                        except Exception:
                            LOGGER.exception("Falló presencia_teclado; se ignora.")
                    if (
                        now - self._watch_started_at >= self.watch_arm_seg
                        and now - ultima_presencia >= self._tolerancia.umbral_seg
                    ):
                        self._retirar_acceso("ausencia")
                        state = self.estado
                        presence_frames = 0
                        continue

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
                                if self._rostro_validado:
                                    # Segunda y siguientes aperturas: sin reto.
                                    self._grant(who)
                                    state = GRANTED
                                else:
                                    blink_detector = _BlinkDetector()
                                    live_matches.clear()
                                    state = LIVENESS
                                    state_started = now
                                    self._set_state(
                                        LIVENESS, f"identidad={who} reto=blink"
                                    )
                    if state == VERIFY and now - state_started > VERIFY_TIMEOUT:
                        state = DENIED
                        state_started = now
                        self._set_state(DENIED, "(no reconocido)")

                elif state == LIVENESS:
                    if now - last_face_time > FACE_LOST_SECONDS:
                        state = DENIED
                        state_started = now
                        self._set_state(DENIED, "(se perdió el rostro)")
                    else:
                        if blink_detector is None:
                            raise RuntimeError("El detector de parpadeo no está inicializado")
                        passed = (
                            landmarks is not None
                            and blink_detector.update(landmarks, width, height) >= 2
                        )

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
            if suscriptor is not None:
                suscriptor.cerrar()
            if self._face is not None:
                self._face.close()
            self._face = None
            self._rec = None