"""
Prototipo 2: puerta de acceso facial con liveness y bajo consumo.

Flujo:
  IDLE      -> camara a pocos FPS, solo detecta si hay un rostro (sin embeddings)
  VERIFY    -> compara con tu cara; exige 3 de los ultimos 5 aciertos (suavizado)
  LIVENESS  -> reto aleatorio: parpadear 2 veces  O  saludar con la mano
               (mientras tanto sigue comprobando que sea la misma persona)
  GRANTED / DENIED -> muestra el resultado 3 s y vuelve a IDLE

Requiere face_proto.py en la misma carpeta (usa sus funciones) y haber hecho:
    python face_proto.py enroll samuel

Uso:
    python face_proto2.py run
    python face_proto2.py run --threads 2 --idle-fps 2 --threshold 0.4

Teclas: Q = salir, L = forzar bloqueo (volver a IDLE)

Al salir imprime el CPU/FPS promedio por estado, para comparar con el prototipo 1.
"""
import os
import sys

# --- limitar hilos ANTES de importar numpy / onnxruntime ---
_T = "2"
if "--threads" in sys.argv:
    _T = sys.argv[sys.argv.index("--threads") + 1]
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_v] = _T

import argparse
import random
import time
import urllib.request
from collections import defaultdict, deque

import cv2
import mediapipe as mp
import numpy as np
import onnxruntime as ort
import psutil
from insightface.app import FaceAnalysis
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from face_proto import MODEL_PATH, MODEL_URL, align, embed, landmarks_5, load_db

HAND_MODEL_PATH = "hand_landmarker.task"
HAND_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                  "hand_landmarker/float16/1/hand_landmarker.task")

IDLE, VERIFY, LIVENESS, GRANTED, DENIED = "IDLE", "VERIFY", "LIVENESS", "GRANTED", "DENIED"

R_EYE = [33, 160, 158, 133, 153, 144]
L_EYE = [362, 385, 387, 263, 373, 380]


# ---------------------------------------------------------------- modelos
def download(path, url):
    if not os.path.exists(path):
        print(f"Descargando {path} ...")
        urllib.request.urlretrieve(url, path)


def load_models(threads):
    download(MODEL_PATH, MODEL_URL)
    download(HAND_MODEL_PATH, HAND_MODEL_URL)

    app = FaceAnalysis(name="buffalo_s", allowed_modules=["detection", "recognition"],
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1)
    rec = app.models["recognition"]
    # sesion propia de ArcFace con hilos limitados
    try:
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        rec.session = ort.InferenceSession(rec.model_file, sess_options=so,
                                           providers=["CPUExecutionProvider"])
    except Exception as e:  # si cambia la API interna de insightface, seguimos igual
        print("Aviso: no pude limitar hilos de ArcFace:", e)

    face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE, num_faces=1,
        min_face_detection_confidence=0.5, min_face_presence_confidence=0.5))
    hand = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
        running_mode=vision.RunningMode.VIDEO, num_hands=1,
        min_hand_detection_confidence=0.4, min_hand_presence_confidence=0.4,
        min_tracking_confidence=0.4))
    return face, hand, rec


def to_mp(frame):
    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


def detect_face(face, frame):
    res = face.detect(to_mp(frame))
    return res.face_landmarks[0] if res.face_landmarks else None


_last_ts = [0]


def detect_hand(hand, frame):
    ts = max(int(time.perf_counter() * 1000), _last_ts[0] + 1)  # debe ser creciente
    _last_ts[0] = ts
    res = hand.detect_for_video(to_mp(frame), ts)
    return res.hand_landmarks[0] if res.hand_landmarks else None


def embed_from(rec, frame, lm):
    h, w = frame.shape[:2]
    aligned = align(frame, landmarks_5(lm, w, h))
    return None if aligned is None else embed(rec, aligned)


def best_match(db, e):
    return max(((n, float(np.dot(e, v))) for n, v in db.items()), key=lambda x: x[1])


# ------------------------------------------------------------ liveness
def eye_ratio(lm, idx, w, h):
    p = [np.array([lm[i].x * w, lm[i].y * h]) for i in idx]
    return (np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])) / \
           (2 * np.linalg.norm(p[0] - p[3]) + 1e-9)


class BlinkDetector:
    """Cuenta parpadeos comparando el EAR actual con tu EAR normal (percentil 80)."""

    def __init__(self):
        self.hist = deque(maxlen=45)
        self.closed = False
        self.blinks = 0
        self.ear = 0.0

    def update(self, lm, w, h):
        self.ear = (eye_ratio(lm, R_EYE, w, h) + eye_ratio(lm, L_EYE, w, h)) / 2
        self.hist.append(self.ear)
        if len(self.hist) < 15:
            return self.blinks
        base = np.percentile(self.hist, 80)
        if not self.closed and self.ear < base * 0.72:
            self.closed = True
        elif self.closed and self.ear > base * 0.85:
            self.closed = False
            self.blinks += 1
        return self.blinks


def palm_open(hl):
    wr = np.array([hl[0].x, hl[0].y])
    ext = 0
    for tip, pip in ((8, 6), (12, 10), (16, 14), (20, 18)):
        d_tip = np.linalg.norm(np.array([hl[tip].x, hl[tip].y]) - wr)
        d_pip = np.linalg.norm(np.array([hl[pip].x, hl[pip].y]) - wr)
        if d_tip > d_pip * 1.05:
            ext += 1
    return ext >= 3


class OldWaveDetector:
    """(version 1, descartada) Saludo = palma abierta con la muñeca oscilando de lado a lado (>=3 cambios de sentido)."""

    def __init__(self, window=2.0, thr=0.05):
        self.buf = deque()
        self.window = window
        self.thr = thr
        self.reversals = 0

    def update(self, t, hl):
        if hl is None or not palm_open(hl):
            self.buf.clear()
            self.reversals = 0
            return False
        self.buf.append((t, hl[0].x))
        while self.buf and t - self.buf[0][0] > self.window:
            self.buf.popleft()
        xs = [x for _, x in self.buf]
        if len(xs) < 8:
            return False
        d, ext, rev = 0, xs[0], 0
        for x in xs[1:]:
            if d == 0:
                if x - ext > self.thr:
                    d, ext = 1, x
                elif ext - x > self.thr:
                    d, ext = -1, x
            elif d == 1:
                if x > ext:
                    ext = x
                elif ext - x > self.thr:
                    d, ext, rev = -1, x, rev + 1
            else:
                if x < ext:
                    ext = x
                elif x - ext > self.thr:
                    d, ext, rev = 1, x, rev + 1
        self.reversals = rev
        return rev >= 3


# ----------------------------------------------------------------- main
class WaveDetector:
    """Saludo v2: sigue el CENTRO de la mano (no la muñeca), tolera frames sin mano
    (hasta 0.6 s) y exige palma abierta en la mayoria de los frames, no en todos."""

    def __init__(self, window=2.0, thr=0.03):
        self.buf = deque()  # (t, x_centro, palma_abierta)
        self.window = window
        self.thr = thr
        self.last_seen = 0.0
        self.seen = False
        self.reversals = 0
        self.amp = 0.0
        self.open_frac = 0.0

    def update(self, t, hl):
        self.seen = hl is not None
        if hl is not None:
            self.last_seen = t
            cx = float(np.mean([p.x for p in hl]))
            self.buf.append((t, cx, palm_open(hl)))
        elif t - self.last_seen > 0.6:
            self.buf.clear()
            self.reversals, self.amp, self.open_frac = 0, 0.0, 0.0
            return False
        while self.buf and t - self.buf[0][0] > self.window:
            self.buf.popleft()
        if len(self.buf) < 6:
            return False
        xs = [x for _, x, _ in self.buf]
        self.amp = max(xs) - min(xs)
        self.open_frac = float(np.mean([o for _, _, o in self.buf]))
        d, ext, rev = 0, xs[0], 0
        for x in xs[1:]:
            if d == 0:
                if x - ext > self.thr:
                    d, ext = 1, x
                elif ext - x > self.thr:
                    d, ext = -1, x
            elif d == 1:
                if x > ext:
                    ext = x
                elif ext - x > self.thr:
                    d, ext, rev = -1, x, rev + 1
            else:
                if x < ext:
                    ext = x
                elif x - ext > self.thr:
                    d, ext, rev = 1, x, rev + 1
        self.reversals = rev
        return rev >= 3 and self.open_frac >= 0.5


def put(img, text, y, color=(255, 255, 0), scale=0.6):
    cv2.putText(img, text, (10, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2)


def run(args):
    db = load_db()
    if not db:
        print("Base vacia. Ejecuta primero: python face_proto.py enroll <nombre>")
        return
    face, hand, rec = load_models(args.threads)
    cv2.setNumThreads(args.threads)
    proc = psutil.Process(os.getpid())
    ncpu = psutil.cpu_count()
    proc.cpu_percent(None)

    cap = cv2.VideoCapture(0)
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    state, t_state = IDLE, time.time()
    matches = deque(maxlen=5)
    live_matches = deque(maxlen=4)
    presence = 0
    last_emb = 0.0
    last_face_t = time.time()
    who, score, msg = "", 0.0, ""
    challenge, blink, wave = None, None, None
    cpu_hist = defaultdict(list)
    fps_hist = defaultdict(list)
    cur_cpu, last_cpu_t = 0.0, time.time()
    last_loop = time.perf_counter()
    fps_win = deque(maxlen=30)

    def go(new, text=""):
        nonlocal state, t_state, msg
        print(f"[{time.strftime('%H:%M:%S')}] {state} -> {new} {text}")
        state, t_state, msg = new, time.time(), text

    print("Corriendo. Q = salir, L = bloquear.")
    while True:
        if state == IDLE:
            time.sleep(1.0 / args.idle_fps)
            for _ in range(3):      # descartar frames viejos del buffer
                cap.grab()
            ok, frame = cap.retrieve()
        else:
            ok, frame = cap.read()
        if not ok:
            break
        now = time.time()
        h, w = frame.shape[:2]
        lm = None
        hl_draw = None

        if state in (IDLE, VERIFY, LIVENESS):
            lm = detect_face(face, frame)
            if lm is not None:
                last_face_t = now

        # ---------------- IDLE ----------------
        if state == IDLE:
            presence = presence + 1 if lm is not None else 0
            if presence >= 2:
                matches.clear()
                presence = 0
                go(VERIFY)

        # ---------------- VERIFY ----------------
        elif state == VERIFY:
            if lm is None and now - last_face_t > 1.5:
                go(IDLE, "(sin rostro)")
            elif lm is not None and now - last_emb >= args.verify_interval:
                last_emb = now
                e = embed_from(rec, frame, lm)
                if e is not None:
                    who, score = best_match(db, e)
                    matches.append(who if score >= args.threshold else None)
                    counts = defaultdict(int)
                    for m in matches:
                        if m:
                            counts[m] += 1
                    if counts and max(counts.values()) >= 3:
                        who = max(counts, key=counts.get)
                        challenge = random.choice(["blink", "wave"])
                        blink, wave = BlinkDetector(), WaveDetector()
                        live_matches.clear()
                        go(LIVENESS, f"identidad={who} reto={challenge}")
            if state == VERIFY and now - t_state > args.verify_timeout:
                go(DENIED, "no reconocido")

        # ---------------- LIVENESS ----------------
        elif state == LIVENESS:
            if now - last_face_t > (4.0 if challenge == "wave" else 2.0):
                go(IDLE, "(perdi el rostro)")
            else:
                passed = False
                if challenge == "blink" and lm is not None:
                    passed = blink.update(lm, w, h) >= 2
                elif challenge == "wave":
                    hl_draw = detect_hand(hand, frame)
                    passed = wave.update(now, hl_draw)
                # seguir comprobando que sea la misma persona
                if lm is not None and now - last_emb >= 0.5:
                    last_emb = now
                    e = embed_from(rec, frame, lm)
                    if e is not None:
                        n, s = best_match(db, e)
                        score = s
                        live_matches.append(n == who and s >= args.threshold)
                if len(live_matches) >= 3 and sum(live_matches) < 2:
                    go(DENIED, "cambio la persona")
                elif passed:
                    go(GRANTED, f"bienvenido {who}")
                elif now - t_state > args.live_timeout:
                    go(DENIED, "reto no superado")

        # ---------------- GRANTED / DENIED ----------------
        elif state in (GRANTED, DENIED):
            if now - t_state > 3.0:
                go(IDLE)

        # ---------------- metricas ----------------
        t_perf = time.perf_counter()
        fps_win.append(1.0 / max(t_perf - last_loop, 1e-6))
        last_loop = t_perf
        if now - last_cpu_t >= 1.0:
            cur_cpu = proc.cpu_percent(None) / ncpu
            last_cpu_t = now
            cpu_hist[state].append(cur_cpu)
            fps_hist[state].append(float(np.mean(fps_win)))
        ram = proc.memory_info().rss / 1024 ** 2

        # ---------------- overlay ----------------
        vis = frame
        if lm is not None:
            xs = [p.x * w for p in lm]
            ys = [p.y * h for p in lm]
            cv2.rectangle(vis, (int(min(xs)), int(min(ys))), (int(max(xs)), int(max(ys))),
                          (0, 255, 0) if state != DENIED else (0, 0, 255), 2)
        put(vis, f"Estado: {state}", 25, (255, 255, 255), 0.8)
        put(vis, f"FPS: {np.mean(fps_win):.1f}  CPU: {cur_cpu:.0f}%  RAM: {ram:.0f} MB", 50)
        if state == VERIFY:
            put(vis, f"Verificando... {who} ({score:.2f})  aciertos {sum(1 for m in matches if m)}/5", 75)
        elif state == LIVENESS:
            if challenge == "blink":
                put(vis, f"RETO: parpadea 2 veces  ({blink.blinks}/2)  EAR={blink.ear:.2f}", 75,
                    (0, 200, 255))
            else:
                put(vis, f"RETO: saluda con la mano  (oscilaciones {wave.reversals}/3)", 75,
                    (0, 200, 255))
                put(vis, f"mano: {'SI' if wave.seen else 'NO'}  palma abierta: "
                         f"{wave.open_frac * 100:.0f}%  amplitud: {wave.amp:.2f} (min 0.06)", 125,
                    (0, 255, 255), 0.5)
                if hl_draw is not None:
                    for p in hl_draw:
                        cv2.circle(vis, (int(p.x * w), int(p.y * h)), 3, (0, 255, 255), -1)
            put(vis, f"Identidad: {who} ({score:.2f})", 100)
        elif state == GRANTED:
            put(vis, "ACCESO CONCEDIDO", 80, (0, 255, 0), 1.0)
            put(vis, msg, 110, (0, 255, 0))
        elif state == DENIED:
            put(vis, "ACCESO DENEGADO", 80, (0, 0, 255), 1.0)
            put(vis, msg, 110, (0, 0, 255))
        cv2.imshow("puerta facial", vis)
        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("l"):
            go(IDLE, "(bloqueo manual)")

    cap.release()
    cv2.destroyAllWindows()
    print("\n=== Promedio por estado (CPU normalizado por nº de CPUs) ===")
    for s in (IDLE, VERIFY, LIVENESS, GRANTED, DENIED):
        if cpu_hist[s]:
            print(f"{s:9s} CPU {np.mean(cpu_hist[s]):5.1f}%   FPS {np.mean(fps_hist[s]):5.1f}"
                  f"   ({len(cpu_hist[s])} muestras)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["run"])
    ap.add_argument("--threshold", type=float, default=0.4)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--idle-fps", type=float, default=2.0)
    ap.add_argument("--verify-interval", type=float, default=0.25)
    ap.add_argument("--verify-timeout", type=float, default=10.0)
    ap.add_argument("--live-timeout", type=float, default=8.0)
    run(ap.parse_args())