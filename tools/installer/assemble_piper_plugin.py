"""Build a separate local Piper sidecar candidate from already verified inputs.

This script performs no network access and never adds Piper to the DARK core
payload. Its output is an unsigned candidate, not a publishable plugin release.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PYTHON = ROOT / ".output" / "release" / "piper-runtime-prototype" / "python"
OUTPUT = ROOT / ".output" / "release" / "piper-plugin-candidate-20261121"
ARCHIVE_NAME = "piper-plugin-win-x64-python312.zip"
WORKER = ROOT / "tools" / "installer" / "piper_worker.py"

# Only the exact runtime closure for the previously verified Piper lock is
# copied. The plugin receives its own CPython and site-packages directory.
SITE_PACKAGES = {
    "flatbuffers", "flatbuffers-25.12.19.dist-info",
    "numpy", "numpy-2.5.3.dist-info", "numpy.libs",
    "onnxruntime", "onnxruntime-1.31.0.dist-info",
    "packaging", "packaging-26.3.dist-info",
    "pathvalidate", "pathvalidate-3.3.1.dist-info",
    "piper", "piper_tts-1.8.0.dist-info",
    "google", "protobuf-7.36.1.dist-info",
    "regex", "regex-2026.9.29.dist-info",
    "sentence_stream", "sentence_stream-1.3.0.dist-info",
    "wyoming", "wyoming-1.10.2.dist-info",
    "wyoming_piper", "wyoming_piper-2.5.4.dist-info",
}


def copy_runtime(source: Path, destination: Path) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"No se encontró el runtime verificado: {source}")
    for current, directories, files in __import__("os").walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        if relative_dir.as_posix() == "Lib/site-packages":
            directories[:] = sorted(name for name in directories if name in SITE_PACKAGES)
            files[:] = []
        else:
            directories[:] = sorted(
                name for name in directories
                if not (current_path / name).is_symlink()
            )
        for name in sorted(files):
            source_file = current_path / name
            if source_file.is_symlink():
                continue
            relative = relative_dir / name
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)


def inventory(root: Path) -> tuple[list[dict[str, object]], int]:
    items: list[dict[str, object]] = []
    total = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        size = path.stat().st_size
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        items.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": size,
            "sha256": hasher.hexdigest(),
        })
        total += size
    return items, total


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"El destino ya existe; no se sobrescribió: {OUTPUT}")
    plugin = OUTPUT / "plugin"
    python_root = plugin / "python"
    plugin.mkdir(parents=True)
    copy_runtime(SOURCE_PYTHON, python_root)
    shutil.copyfile(WORKER, plugin / "piper_worker.py")
    (plugin / "PLUGIN-NOTICE.txt").write_text(
        "D.A.R.K. Piper sidecar candidate (unsigned; not for release).\n"
        "This is an optional, independent child process. It is not part of the DARK core runtime.\n"
        "The launcher source is piper_worker.py (GPL-3.0-or-later).\n"
        "Piper, Wyoming Piper and all dependency notices/licenses are retained in python/Lib/site-packages.\n"
        "Voice models are intentionally not included. The user chooses and downloads a voice separately.\n",
        encoding="utf-8",
    )

    required = (
        "python/python.exe", "python/python312._pth", "piper_worker.py",
        "python/Lib/site-packages/piper/__init__.py",
        "python/Lib/site-packages/wyoming_piper/__main__.py",
        "python/Lib/site-packages/onnxruntime/__init__.py",
        "python/Lib/site-packages/numpy/__init__.py",
    )
    missing = [path for path in required if not (plugin / path).is_file()]
    if missing:
        raise FileNotFoundError("Faltan partes del sidecar Piper: " + ", ".join(missing))

    files, expanded_bytes = inventory(plugin)
    archive_path = OUTPUT / ARCHIVE_NAME
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as archive:
        for path in sorted(item for item in plugin.rglob("*") if item.is_file()):
            relative = path.relative_to(plugin).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    archive_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    summary = {
        "schemaVersion": 1,
        "status": "unsigned-local-optional-plugin-not-for-release",
        "componentId": "piper-sidecar",
        "version": "piper-tts 1.8.0 / wyoming-piper 2.5.4",
        "target": "Windows x64 / CPython 3.12",
        "archive": ARCHIVE_NAME,
        "archiveBytes": archive_path.stat().st_size,
        "archiveSha256": archive_hash,
        "expandedBytes": expanded_bytes,
        "fileCount": len(files),
        "voiceModelsIncluded": False,
        "filesSha256": files,
    }
    (OUTPUT / "candidate-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "filesSha256"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
