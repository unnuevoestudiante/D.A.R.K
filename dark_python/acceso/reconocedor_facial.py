"""Reconocedor facial SFace (OpenCV Zoo) sobre OpenCV, con licencia Apache 2.0.

Sustituye al modelo anterior (InsightFace «buffalo_s», solo de uso no comercial). El modelo
`face_recognition_sface_2021dec.onnx` (≈39 MB, Apache-2.0, https://github.com/opencv/opencv_zoo) no viaja en la
instalación: se descarga la primera vez que se registra un rostro (el consentimiento lo avisa), se verifica
por huella SHA-256 y se guarda en la carpeta de estado. Entrega vectores de 128 valores; los registros hechos
con el modelo anterior (512 valores) no son comparables y hay que repetirlos.

Cumple el protocolo `_RecognitionModel` de `herramientas.vision` (`get_feat` sobre un rostro ya alineado 112×112 BGR).
"""
from __future__ import annotations

import hashlib
import logging
import os
import urllib.request
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

LOGGER = logging.getLogger(__name__)

NOMBRE_MODELO = "face_recognition_sface_2021dec.onnx"
URL_MODELO = "https://huggingface.co/opencv/face_recognition_sface/resolve/main/" + NOMBRE_MODELO
SHA256_MODELO = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"
DIMENSION = 128
LICENCIA = "Apache-2.0"


class ErrorModeloFacial(RuntimeError):
    """No se pudo obtener o verificar el modelo de reconocimiento."""


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def asegurar_modelo(carpeta: Path, progreso: Callable[[int, int], None] | None = None) -> Path:
    """Devuelve la ruta del modelo verificado; lo descarga si falta."""
    destino = carpeta / NOMBRE_MODELO
    if destino.is_file() and _sha256(destino) == SHA256_MODELO:
        return destino
    carpeta.mkdir(parents=True, exist_ok=True)
    temporal = destino.with_name(destino.name + ".part")
    try:
        LOGGER.info("Descargando el modelo de reconocimiento facial (≈39 MB).")
        with urllib.request.urlopen(URL_MODELO, timeout=60) as resp, temporal.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            hecho = 0
            while True:
                bloque = resp.read(1 << 20)
                if not bloque:
                    break
                out.write(bloque)
                hecho += len(bloque)
                if progreso:
                    progreso(hecho, total)
        if _sha256(temporal) != SHA256_MODELO:
            raise ErrorModeloFacial("La descarga del modelo no coincide con la huella esperada; se descartó.")
        os.replace(temporal, destino)
        return destino
    except ErrorModeloFacial:
        raise
    except Exception as exc:  # red, disco…
        raise ErrorModeloFacial(f"No se pudo descargar el modelo de reconocimiento: {exc}") from exc
    finally:
        try:
            temporal.unlink()
        except OSError:
            pass


class ReconocedorSFace:
    def __init__(self, ruta_modelo: Path, hilos: int = 2) -> None:
        self.model_file = str(ruta_modelo)
        try:
            cv2.setNumThreads(max(1, int(hilos)))
        except Exception:
            pass
        self._modelo = cv2.FaceRecognizerSF.create(self.model_file, "")
        self.session = self._modelo  # el protocolo pide el atributo; aquí es el reconocedor de OpenCV

    def get_feat(self, imagen: np.ndarray) -> np.ndarray:
        """Vector de rasgos (1×128) de un rostro ya alineado (112×112, BGR)."""
        return np.asarray(self._modelo.feature(imagen), dtype=np.float32).reshape(1, -1)
