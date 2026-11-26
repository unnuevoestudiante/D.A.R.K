"""
Prototipo de reconocimiento facial: MediaPipe (deteccion) + ArcFace ONNX (embedding).

Instalacion:
    pip install mediapipe opencv-python insightface onnxruntime psutil numpy

Uso:
    python face_proto.py enroll samuel     # registra tu cara (pulsa ESPACIO varias veces, Q para terminar)
    python face_proto.py run               # reconoce en vivo y muestra metricas
    python face_proto.py run --threshold 0.45

Notas:
- La primera vez insightface descarga el modelo buffalo_s (~120 MB).
- Los embeddings se guardan en faces_db.npz (solo vectores, no fotos).
"""
import argparse
import os
import time
import urllib.request
from collections import deque

import cv2
import mediapipe as mp
import numpy as np
import psutil
from insightface.app import FaceAnalysis
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

DB_PATH = "faces_db.npz"
MODEL_PATH = "face_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")

# Alineacion ArcFace estandar a 112x112 (ojo der, ojo izq, nariz, boca-der, boca-izq)
ARCFACE_DST = np.array([
    [38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
    [41.5493, 92.3655], [70.7299, 92.2041]], dtype=np.float32)


def load_models():
    app = FaceAnalysis(name="buffalo_s", allowed_modules=["detection", "recognition"],
                       providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1)
    rec = app.models["recognition"]
    if not os.path.exists(MODEL_PATH):
        print(f"Descargando modelo de MediaPipe a {MODEL_PATH} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    options = vision.FaceLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5)
    detector = vision.FaceLandmarker.create_from_options(options)
    return detector, rec


def landmarks_5(face_landmarks, w, h):
    """5 puntos a partir de FaceMesh: ojos, nariz, comisuras de la boca."""
    lm = face_landmarks  # lista de landmarks normalizados

    def p(i):
        return np.array([lm[i].x * w, lm[i].y * h], dtype=np.float32)

    # Indices FaceMesh: ojo izq-imagen (33,133), ojo der-imagen (362,263), nariz 1, boca 61 y 291
    eye_a = (p(33) + p(133)) / 2   # lado izquierdo de la imagen
    eye_b = (p(362) + p(263)) / 2  # lado derecho de la imagen
    nose = p(1)
    mouth_a, mouth_b = p(61), p(291)
    return np.stack([eye_a, eye_b, nose, mouth_a, mouth_b])


def align(frame, pts5):
    M, _ = cv2.estimateAffinePartial2D(pts5, ARCFACE_DST, method=cv2.LMEDS)
    if M is None:
        return None
    return cv2.warpAffine(frame, M, (112, 112), borderValue=0.0)


def embed(rec, aligned):
    e = rec.get_feat(aligned).flatten()
    return e / (np.linalg.norm(e) + 1e-9)


def get_face(detector, rec, frame):
    h, w = frame.shape[:2]
    t0 = time.perf_counter()
    rgb = np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    res = detector.detect(mp_img)
    t_det = (time.perf_counter() - t0) * 1000
    if not res.face_landmarks:
        return None, None, t_det, 0.0
    fl = res.face_landmarks[0]
    pts = landmarks_5(fl, w, h)
    aligned = align(frame, pts)
    if aligned is None:
        return None, None, t_det, 0.0
    t1 = time.perf_counter()
    e = embed(rec, aligned)
    t_emb = (time.perf_counter() - t1) * 1000
    xs = [l.x * w for l in fl]
    ys = [l.y * h for l in fl]
    box = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
    return e, box, t_det, t_emb


def load_db():
    if os.path.exists(DB_PATH):
        d = np.load(DB_PATH, allow_pickle=True)
        return {k: d[k] for k in d.files}
    return {}


def enroll(name):
    detector, rec = load_models()
    cap = cv2.VideoCapture(0)
    samples = []
    print("ESPACIO = capturar muestra (haz 8-10 con distintos angulos/luz), Q = terminar")
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        e, box, _, _ = get_face(detector, rec, frame)
        vis = frame.copy()
        if box:
            cv2.rectangle(vis, box[:2], box[2:], (0, 255, 0), 2)
        cv2.putText(vis, f"muestras: {len(samples)}", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("enroll", vis)
        k = cv2.waitKey(1) & 0xFF
        if k == ord(" ") and e is not None:
            samples.append(e)
        elif k == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    if samples:
        mean = np.mean(samples, axis=0)
        mean /= np.linalg.norm(mean)
        db = load_db()
        db[name] = mean
        np.savez(DB_PATH, **db)
        print(f"Guardado '{name}' con {len(samples)} muestras en {DB_PATH}")


def run(threshold):
    db = load_db()
    if not db:
        print("Base vacia. Ejecuta primero: python face_proto.py enroll <nombre>")
        return
    detector, rec = load_models()
    proc = psutil.Process(os.getpid())
    proc.cpu_percent(None)
    cap = cv2.VideoCapture(0)
    fps_hist, det_hist, emb_hist = deque(maxlen=60), deque(maxlen=60), deque(maxlen=60)
    cpu = 0.0
    last = time.perf_counter()
    n = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        e, box, t_det, t_emb = get_face(detector, rec, frame)
        det_hist.append(t_det)
        label, score = "sin rostro", 0.0
        if e is not None:
            emb_hist.append(t_emb)
            best = max(((nm, float(np.dot(e, v))) for nm, v in db.items()), key=lambda x: x[1])
            score = best[1]
            label = best[0] if score >= threshold else "desconocido"
            color = (0, 255, 0) if label not in ("desconocido",) else (0, 0, 255)
            cv2.rectangle(frame, box[:2], box[2:], color, 2)
            cv2.putText(frame, f"{label} ({score:.2f})", (box[0], box[1] - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        now = time.perf_counter()
        fps_hist.append(1.0 / max(now - last, 1e-6))
        last = now
        n += 1
        if n % 15 == 0:
            cpu = proc.cpu_percent(None) / psutil.cpu_count()
        ram = proc.memory_info().rss / 1024 ** 2
        info = [f"FPS: {np.mean(fps_hist):.1f}",
                f"MediaPipe: {np.mean(det_hist):.1f} ms",
                f"ArcFace: {np.mean(emb_hist) if emb_hist else 0:.1f} ms",
                f"CPU proceso: {cpu:.0f}%  RAM: {ram:.0f} MB"]
        for i, t in enumerate(info):
            cv2.putText(frame, t, (10, 25 + 24 * i), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 0), 2)
        cv2.imshow("reconocimiento", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["enroll", "run"])
    ap.add_argument("name", nargs="?", default="samuel")
    ap.add_argument("--threshold", type=float, default=0.4)
    a = ap.parse_args()
    enroll(a.name) if a.mode == "enroll" else run(a.threshold)