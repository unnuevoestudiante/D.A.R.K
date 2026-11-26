"""Voces locales de Piper, a demanda y en un proceso aparte.

Piper (el motor) es GPL-3.0-or-later. Por eso **no viaja en la instalación ni se importa jamás en el proceso de
D.A.R.K.**: cuando la persona elige una voz de Piper, y solo entonces (con su consentimiento), se descargan las
ruedas oficiales del motor desde PyPI —con huella SHA-256 fijada— a la carpeta de datos, y se usan desde un
**proceso hijo** (`python -I worker`) con el que se habla por una tubería (JSON por línea hacia dentro, audio PCM hacia
fuera). El código del worker es un guion de unas pocas líneas con su propia cabecera GPL; se escribe junto al motor.

Capas de este módulo:
  * rutas y estado del motor (`motor_instalado`),
  * `instalar_motor`: descarga y verifica las ruedas (progreso 0–1),
  * `PiperLocal.sintetizar(texto, onnx)` → `AudioPcm` (mantiene vivo un worker por voz y cambia sin fugas).
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import subprocess
import sys
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from utils.rutas_estado import resolver_ruta_estado

from .proveedores_voz import AudioPcm, ErrorVoz
from .pronunciacion import para_voz

# (archivo, url, bytes, sha256, licencia). Solo estas cuatro ruedas oficiales; numpy y onnxruntime ya van en el núcleo.
RUEDAS = (
    ("piper_tts-1.8.0-cp39-abi3-win_amd64.whl",
     "https://files.pythonhosted.org/packages/12/9c/c736d1961cf9ce0655278731b9430df41892ca2ded7b09dabcb340612158/"
     "piper_tts-1.8.0-cp39-abi3-win_amd64.whl",
     34119688, "5da9bfdb05dfe15da3536859d422e605483ffa6d2b3ec2c5b9593bae6b5aa6a4", "GPL-3.0-or-later"),
    ("pathvalidate-3.3.1-py3-none-any.whl",
     "https://files.pythonhosted.org/packages/9a/70/875f4a23bfc4731703a5835487d0d2fb999031bd415e7d17c0ae615c18b7/"
     "pathvalidate-3.3.1-py3-none-any.whl",
     24305, "5263baab691f8e1af96092fa5137ee17df5bdfbd6cff1fcac4d6ef4bc2e1735f", "MIT"),
    ("regex-2026.9.29-cp312-cp312-win_amd64.whl",
     "https://files.pythonhosted.org/packages/93/19/489bc8db91196381c935752df01ba3f607140daece33b78d88573f028e64/"
     "regex-2026.9.29-cp312-cp312-win_amd64.whl",
     280334, "fdd88ed5e20b1bcdd234421e454962c971aa44b653bdb7f1ea9ef683e90fb649", "Apache-2.0 AND CNRI-Python"),
    ("sentence_stream-1.3.0-py3-none-any.whl",
     "https://files.pythonhosted.org/packages/48/b6/48339c109bab6f54ff608800773b9425464c6cbf7fd3f2ba01294d78be3d/"
     "sentence_stream-1.3.0-py3-none-any.whl",
     8707, "7448d131315b85eefdf238e5edd9caa62899acf609145d5e0e10c09812eb8a1d", "Apache-2.0"),
)
TAMANO_MOTOR_BYTES = sum(r[2] for r in RUEDAS)

WORKER = '''# SPDX-License-Identifier: GPL-3.0-or-later
# Worker de voz de D.A.R.K.: carga una voz de Piper y sintetiza lo que se le pide.
# Protocolo: stdin = una línea JSON {"texto": "..."} por frase; stdout = una línea JSON {"rate": N, "bytes": M}
# seguida de M bytes de PCM int16 mono. Código fuente de Piper: https://github.com/OHF-Voice/piper1-gpl
import json
import sys

sys.path.insert(0, sys.argv[2])
from piper import PiperVoice

voz = PiperVoice.load(sys.argv[1])
salida = sys.stdout.buffer
salida.write((json.dumps({"listo": True, "rate": voz.config.sample_rate}) + "\\n").encode("utf-8"))
salida.flush()
for linea in sys.stdin:
    try:
        texto = str(json.loads(linea).get("texto", ""))
        pcm, rate = b"", voz.config.sample_rate
        for trozo in voz.synthesize(texto):
            pcm += trozo.audio_int16_bytes
            rate = trozo.sample_rate
        salida.write((json.dumps({"rate": rate, "bytes": len(pcm)}) + "\\n").encode("utf-8"))
        salida.write(pcm)
    except Exception as error:
        salida.write((json.dumps({"error": type(error).__name__}) + "\\n").encode("utf-8"))
    salida.flush()
'''


def carpeta_motor() -> Path:
    return Path(resolver_ruta_estado("plugins", "piper"))


def carpeta_site_packages() -> Path:
    return carpeta_motor() / "site-packages"


def ruta_worker() -> Path:
    return carpeta_motor() / "piper_worker.py"


def motor_instalado() -> bool:
    return (carpeta_site_packages() / "piper" / "__init__.py").is_file() and ruta_worker().is_file()


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def instalar_motor(progreso: Callable[[float, str], None] = lambda f, m="": None,
                   cancelado: Callable[[], bool] = lambda: False,
                   abrir: Callable[..., object] = urllib.request.urlopen) -> None:
    """Descarga las ruedas del motor, las verifica y las extrae. Lanza `ErrorVoz` con un mensaje mostrable."""
    destino = carpeta_motor()
    temporal = destino.with_name(destino.name + ".instalando")
    import shutil

    shutil.rmtree(temporal, ignore_errors=True)
    (temporal / "descargas").mkdir(parents=True)
    hecho_total = 0
    try:
        for archivo, url, tamano, huella, _licencia in RUEDAS:
            ruta = temporal / "descargas" / archivo
            progreso(hecho_total / TAMANO_MOTOR_BYTES * 0.9, "Descargando el motor de voz…")
            try:
                with abrir(url, timeout=60) as resp, ruta.open("wb") as out:  # type: ignore[call-arg]
                    while True:
                        if cancelado():
                            raise ErrorVoz("Se canceló la descarga.")
                        bloque = resp.read(1 << 20)
                        if not bloque:
                            break
                        out.write(bloque)
                        hecho_total += len(bloque)
                        progreso(min(hecho_total, TAMANO_MOTOR_BYTES) / TAMANO_MOTOR_BYTES * 0.9, "Descargando el motor de voz…")
            except ErrorVoz:
                raise
            except Exception:
                raise ErrorVoz("No pude descargar el motor de voz. ¿Hay conexión a internet?") from None
            if ruta.stat().st_size != tamano or _sha256(ruta) != huella:
                raise ErrorVoz("El motor de voz descargado no coincide con la huella esperada; lo descarté.")
        progreso(0.92, "Preparando el motor de voz…")
        paquetes = temporal / "site-packages"
        for archivo, *_ in RUEDAS:
            with zipfile.ZipFile(temporal / "descargas" / archivo) as z:
                for miembro in z.namelist():
                    objetivo = (paquetes / miembro).resolve()
                    if paquetes.resolve() not in objetivo.parents:
                        raise ErrorVoz("El motor de voz trae una ruta insegura; lo descarté.")
                z.extractall(paquetes)
        (temporal / "piper_worker.py").write_text(WORKER, encoding="utf-8")
        shutil.rmtree(temporal / "descargas", ignore_errors=True)
        shutil.rmtree(destino, ignore_errors=True)
        os.replace(temporal, destino)
    except OSError as error:
        raise ErrorVoz(f"No pude guardar el motor de voz: {error.strerror or 'error de disco'}.") from None
    finally:
        shutil.rmtree(temporal, ignore_errors=True)
    progreso(1.0, "Motor de voz listo.")


def desinstalar_motor() -> bool:
    import shutil

    shutil.rmtree(carpeta_motor(), ignore_errors=True)
    return not carpeta_motor().exists()


class _Worker:
    def __init__(self, onnx: str, python: str, tiempo_arranque: float = 60.0) -> None:
        self.onnx = onnx
        self._proc = subprocess.Popen(
            [python, "-I", str(ruta_worker()), onnx, str(carpeta_site_packages())],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        saludo = self._linea(tiempo_arranque)
        if not saludo or not saludo.get("listo"):
            self.cerrar()
            raise ErrorVoz("La voz local no pudo arrancar.")
        self.rate = int(saludo.get("rate") or 22050)

    @property
    def vivo(self) -> bool:
        return self._proc.poll() is None

    def _linea(self, tiempo: float) -> dict | None:
        resultado: "queue.Queue[bytes | None]" = queue.Queue()

        def leer() -> None:
            try:
                resultado.put(self._proc.stdout.readline())  # type: ignore[union-attr]
            except Exception:
                resultado.put(None)

        threading.Thread(target=leer, daemon=True).start()
        try:
            datos = resultado.get(timeout=tiempo)
        except queue.Empty:
            return None
        if not datos:
            return None
        try:
            return json.loads(datos.decode("utf-8"))
        except ValueError:
            return None

    def sintetizar(self, texto: str, tiempo: float = 60.0) -> AudioPcm:
        try:
            self._proc.stdin.write((json.dumps({"texto": texto}) + "\n").encode("utf-8"))  # type: ignore[union-attr]
            self._proc.stdin.flush()  # type: ignore[union-attr]
        except OSError:
            raise ErrorVoz("La voz local se cerró.") from None
        cabecera = self._linea(tiempo)
        if not cabecera or "error" in cabecera:
            raise ErrorVoz("La voz local no pudo decir esa frase.")
        total = int(cabecera.get("bytes") or 0)
        pcm = self._proc.stdout.read(total) if total else b""  # type: ignore[union-attr]
        if len(pcm) != total or not pcm:
            raise ErrorVoz("La voz local devolvió un audio incompleto.")
        return AudioPcm(pcm, int(cabecera.get("rate") or self.rate), 1, 2)

    def cerrar(self) -> None:
        try:
            if self._proc.poll() is None:
                self._proc.kill()
        except Exception:
            pass


class PiperLocal:
    """Un worker vivo (el de la última voz usada); cambiar de voz lo reemplaza."""

    def __init__(self, python: str | None = None) -> None:
        self._python = python or sys.executable
        self._lock = threading.Lock()
        self._worker: _Worker | None = None

    def sintetizar(self, texto: str, onnx: str) -> AudioPcm:
        limpio = para_voz((texto or "").strip())
        if not limpio:
            raise ErrorVoz("No hay texto que decir.")
        if not motor_instalado():
            raise ErrorVoz("El motor de voz local no está instalado.")
        if not Path(onnx).is_file():
            raise ErrorVoz("La voz local no está descargada.")
        with self._lock:
            if self._worker is None or self._worker.onnx != onnx or not self._worker.vivo:
                if self._worker is not None:
                    self._worker.cerrar()
                self._worker = _Worker(onnx, self._python)
            try:
                return self._worker.sintetizar(limpio[:4000])
            except ErrorVoz:
                self._worker.cerrar()
                self._worker = None
                raise

    def cerrar(self) -> None:
        with self._lock:
            if self._worker is not None:
                self._worker.cerrar()
                self._worker = None
