"""Paquete de visión y voz de entrada que viaja en el payload (OpenCV, MediaPipe, matplotlib, etc.).

Las ruedas viven en `.output/release/vision-wheels/` y sus huellas en `vision-wheels-inputs.json`.
Este módulo las verifica y las extrae a una carpeta de montaje limpia que el ensamblador copia
dentro de `python/Lib/site-packages` y el verificador usa como árbol esperado.

  python tools/installer/vision_wheels.py --write-inputs   # recalcula huellas tras cambiar ruedas
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WHEELS = ROOT / ".output" / "release" / "vision-wheels"
STAGE = ROOT / ".output" / "release" / "vision-stage"
INPUTS = Path(__file__).with_name("vision-wheels-inputs.json")
EXTRAS = ROOT / ".output" / "release" / "vision-extras"

#: Modelos que openWakeWord descargaría solo en su primer uso; viajan ya verificados.
MODELOS_WAKE = ("melspectrogram.onnx", "embedding_model.onnx")
MODELOS_WAKE_DESTINO = "openwakeword/resources/models"
#: Palabra de activación propia de D.A.R.K. (en la raíz de la aplicación instalada).
DARK_ONNX = ROOT / "dark.onnx"

# Paquetes que el payload ya no esconde para el sidecar de Piper: la visión y la palabra de
# activación los necesitan en el núcleo.
SIEMPRE_EN_EL_NUCLEO = {
    "flatbuffers", "flatbuffers-25.12.19.dist-info", "onnxruntime", "onnxruntime-1.31.0.dist-info",
    "packaging", "packaging-26.3.dist-info", "google", "protobuf-7.36.1.dist-info",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def escribir_entradas() -> None:
    ruedas = []
    for w in sorted(WHEELS.glob("*.whl")):
        ruedas.append({"file": w.name, "bytes": w.stat().st_size, "sha256": sha256(w)})
    extras = [{"file": n, "bytes": (EXTRAS / n).stat().st_size, "sha256": sha256(EXTRAS / n)} for n in MODELOS_WAKE]
    dark = {"file": "dark.onnx", "bytes": DARK_ONNX.stat().st_size, "sha256": sha256(DARK_ONNX)}
    INPUTS.write_text(json.dumps({"schemaVersion": 1, "target": "cp312 win_amd64", "wheels": ruedas,
                                  "wakeModels": extras, "darkOnnx": dark},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def preparar() -> Path:
    """Verifica cada rueda contra su huella y la extrae a una carpeta limpia. Devuelve esa carpeta."""
    datos = json.loads(INPUTS.read_text(encoding="utf-8"))
    esperadas = {r["file"]: r for r in datos["wheels"]}
    presentes = {p.name for p in WHEELS.glob("*.whl")}
    if presentes != set(esperadas):
        raise SystemExit(f"Las ruedas de visión no coinciden con vision-wheels-inputs.json: {sorted(presentes ^ set(esperadas))}")
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    for nombre, registro in sorted(esperadas.items()):
        rueda = WHEELS / nombre
        if rueda.stat().st_size != registro["bytes"] or sha256(rueda) != registro["sha256"]:
            raise SystemExit(f"Huella distinta en la rueda de visión {nombre}.")
        with zipfile.ZipFile(rueda) as z:
            for miembro in z.infolist():
                destino = (STAGE / miembro.filename).resolve()
                if STAGE.resolve() not in destino.parents and destino != STAGE.resolve():
                    raise SystemExit(f"Ruta insegura en {nombre}: {miembro.filename}")
            z.extractall(STAGE)
    destino = STAGE / MODELOS_WAKE_DESTINO
    destino.mkdir(parents=True, exist_ok=True)
    for registro in datos["wakeModels"]:
        origen = EXTRAS / registro["file"]
        if origen.stat().st_size != registro["bytes"] or sha256(origen) != registro["sha256"]:
            raise SystemExit(f"Huella distinta en el modelo de activación {registro['file']}.")
        shutil.copyfile(origen, destino / registro["file"])
    return STAGE


def dark_onnx() -> Path:
    """`dark.onnx` verificado contra su huella registrada."""
    registro = json.loads(INPUTS.read_text(encoding="utf-8"))["darkOnnx"]
    if DARK_ONNX.stat().st_size != registro["bytes"] or sha256(DARK_ONNX) != registro["sha256"]:
        raise SystemExit("dark.onnx no coincide con la huella registrada en vision-wheels-inputs.json.")
    return DARK_ONNX


if __name__ == "__main__":
    if "--write-inputs" in sys.argv:
        escribir_entradas()
        print("escrito", INPUTS)
    else:
        print(preparar())
