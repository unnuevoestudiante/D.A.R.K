"""Modelos de Whisper que la persona puede habilitar en Voz de entrada (opcional).

Nada de esto viaja en la instalación: al elegir un modelo, y solo entonces, se descarga desde Hugging Face
(repositorios `Systran/faster-whisper-*`) a la carpeta de datos de D.A.R.K. La librería (`faster-whisper`)
sí viene incluida; sin un modelo descargado el reconocimiento usa el reconocedor de Windows.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils.rutas_estado import resolver_ruta_estado

ARCHIVOS = ["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"]


@dataclass(frozen=True)
class ModeloWhisper:
    id: str
    nombre: str
    repo: str
    megas: int
    nota: str


CATALOGO = (
    ModeloWhisper("tiny", "Tiny", "Systran/faster-whisper-tiny", 75, "El más rápido y ligero; entiende peor."),
    ModeloWhisper("base", "Base", "Systran/faster-whisper-base", 145, "Rápido; un paso por encima de Tiny."),
    ModeloWhisper("small", "Small", "Systran/faster-whisper-small", 485, "Buen equilibrio (el que usa D.A.R.K. por defecto)."),
    ModeloWhisper("medium", "Medium", "Systran/faster-whisper-medium", 1530, "El más preciso; exige un equipo potente."),
)


def modelo_por_id(id_: str) -> ModeloWhisper | None:
    return next((m for m in CATALOGO if m.id == id_), None)


def carpeta_modelos() -> Path:
    return Path(resolver_ruta_estado("modelos", "whisper"))


def ruta_de(id_: str) -> Path:
    return carpeta_modelos() / id_


def descargado(id_: str) -> bool:
    """Un modelo está listo si tiene su marca de descarga completa y sus archivos esenciales."""
    carpeta = ruta_de(id_)
    return (carpeta / ".completo").is_file() and (carpeta / "model.bin").is_file() and (carpeta / "config.json").is_file()


def tamano_en_disco(id_: str) -> int:
    carpeta = ruta_de(id_)
    if not carpeta.is_dir():
        return 0
    return sum(f.stat().st_size for f in carpeta.rglob("*") if f.is_file())


def descargar(id_: str, descargador: Callable[..., str] | None = None) -> Path:
    """Descarga el modelo `id_` y deja la marca de completo. Lanza `ValueError`/`OSError` si falla."""
    modelo = modelo_por_id(id_)
    if modelo is None:
        raise ValueError("Ese modelo de Whisper no existe.")
    destino = ruta_de(id_)
    destino.mkdir(parents=True, exist_ok=True)
    marca = destino / ".completo"
    if marca.exists():
        marca.unlink()
    if descargador is None:
        from huggingface_hub import snapshot_download as descargador
    descargador(repo_id=modelo.repo, local_dir=str(destino), allow_patterns=ARCHIVOS)
    if not (destino / "model.bin").is_file() or not (destino / "config.json").is_file():
        raise OSError("La descarga terminó incompleta (faltan archivos del modelo).")
    marca.write_text(json.dumps({"id": id_, "repo": modelo.repo}), encoding="utf-8")
    return destino


def borrar(id_: str) -> bool:
    import shutil

    carpeta = ruta_de(id_)
    if modelo_por_id(id_) is None or not carpeta.is_dir():
        return False
    shutil.rmtree(carpeta, ignore_errors=True)
    return not carpeta.exists()
