"""Read-only integrity and freshness audit for a local DARK app payload candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / ".output" / "release" / "dark-app-payload-candidate-20261123-privacy-v30"
OMIT_DIRS = {".git", ".pytest_cache", "__pycache__", "tests", "pruebas", "_voz_logs", "_voz_tmp", "_tts_temp", "_tts_cache", ".venv", ".estado_usuario"}
OMIT_STATE_FILES = {
    "_cache_apps.json", "memoria.db", "dark_temas.json", "dark_memoria.json", "dark_intenciones.json",
    "dark_entidades.json", "dark_cache_patrones.json", "dark_perfil_conductual.json", "dark_neuronas.json",
}
OMIT_SUFFIXES = {".pyc", ".pyo", ".log", ".jsonl", ".db", ".sqlite", ".sqlite3", ".onnx", ".gguf", ".pt"}
PIPER_OPTIONAL_PACKAGES = {
    "flatbuffers", "flatbuffers-25.12.19.dist-info", "onnxruntime", "onnxruntime-1.31.0.dist-info",
    "packaging", "packaging-26.3.dist-info", "pathvalidate", "pathvalidate-3.3.1.dist-info", "piper",
    "piper_tts-1.8.0.dist-info", "google", "protobuf-7.36.1.dist-info", "regex", "regex-2026.9.29.dist-info",
    "sentence_stream", "sentence_stream-1.3.0.dist-info", "wyoming_piper", "wyoming_piper-2.5.4.dist-info",
}


from vision_wheels import SIEMPRE_EN_EL_NUCLEO, dark_onnx, preparar as preparar_vision

PIPER_OPTIONAL_PACKAGES = PIPER_OPTIONAL_PACKAGES - SIEMPRE_EN_EL_NUCLEO


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


PYTHON_PTH_LINES = ["python312.zip", ".", "..\\dark_python", "Lib\\site-packages", "import site"]


def sanitized_source(path: Path) -> tuple[int, str]:
    """Tamaño y hash de la fuente tal como queda tras sanear rutas del equipo de build (solo .mjs de la UI)."""
    data = path.read_bytes()
    if path.name.lower().endswith("._pth"):
        data = ("\n".join(PYTHON_PTH_LINES) + "\n").encode("ascii")
    if path.suffix.lower() == ".mjs":
        data = data.replace((Path(__file__).resolve().parents[2].as_posix() + "/").encode("utf-8"), b"")
    return len(data), hashlib.sha256(data).hexdigest()


def add_tree(expected: dict[str, tuple[Path, str]], source: Path, prefix: str,
             *, filter_python_source: bool = False, strip_optional_piper: bool = False) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"Falta la fuente del candidato: {source}")
    for current, directories, files in os.walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        directories[:] = sorted(name for name in directories
            if name not in OMIT_DIRS and not (current_path / name).is_symlink())
        if strip_optional_piper and relative_dir.as_posix() == "Lib/site-packages":
            directories[:] = [name for name in directories if name not in PIPER_OPTIONAL_PACKAGES]
        for name in sorted(files):
            source_file = current_path / name
            if name.lower().endswith(".pdb"):
                continue
            if source_file.is_symlink():
                continue
            relative = relative_dir / name
            if filter_python_source:
                if source_file.suffix.lower() in OMIT_SUFFIXES or name in OMIT_STATE_FILES:
                    continue
                if name.startswith(("test_", "probar_")) or name.endswith("_test.py") or name.endswith(".bak") or ".bak_" in name:
                    continue
                if name in {".env", ".env.local", "access-password.json", "online_coder.json"}:
                    continue
                if source_file.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                    continue
            if strip_optional_piper and relative.as_posix() == "Lib/site-packages/COPYING":
                continue
            key = (Path(prefix) / relative).as_posix()
            if key in expected:
                raise ValueError(f"Dos fuentes intentan ocupar el mismo archivo del paquete: {key}")
            expected[key] = (source_file, "fuente " + source_file.relative_to(ROOT).as_posix())


def expected_source_files() -> dict[str, tuple[Path, str]]:
    expected: dict[str, tuple[Path, str]] = {}
    outputs = ROOT / ".output" / "release" / "rebuild-20261122"
    add_tree(expected, ROOT / ".output" / "release" / "piper-runtime-prototype" / "python", "python",
             strip_optional_piper=True)
    add_tree(expected, preparar_vision(), "python/Lib/site-packages")
    add_tree(expected, outputs / "DarkSupervisor", "")
    add_tree(expected, outputs / "DarkManager", "services/DarkManager")
    add_tree(expected, outputs / "DarkTaskManager", "services/DarkTaskManager")
    add_tree(expected, ROOT / "dark_frontend" / ".output", "ui/.output")
    add_tree(expected, ROOT / "dark_electron" / "node_modules" / "electron" / "dist", "electron/runtime")
    for name in ("main.cjs", "preload.js", "package.json", "package-lock.json"):
        source = ROOT / "dark_electron" / name
        expected[(Path("electron/app") / name).as_posix()] = (source, "fuente " + source.relative_to(ROOT).as_posix())
    node = ROOT / ".output" / "private-node" / "node.exe"
    expected["node/node.exe"] = (node, "runtime Node privado")
    expected["dark.onnx"] = (dark_onnx(), "palabra de activación dark.onnx")
    node_license = ROOT / "tools" / "installer" / "third-party" / "node-24.22.3" / "LICENSE"
    expected["node/LICENSE"] = (node_license, "licencia del runtime Node")
    add_tree(expected, ROOT / "dark_python", "dark_python", filter_python_source=True)
    for relative in ("config/runtime.json", "config/runtime.schema.json"):
        source = ROOT / relative
        expected[relative] = (source, "configuración " + relative)
    return expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE,
                        help="Carpeta local del candidato con app/, ZIP e inventarios.")
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    app = candidate / "app"
    archive_path = candidate / "dark-app-payload-candidate.zip"
    inventory_path = candidate / "candidate-inventory.json"
    summary_path = candidate / "candidate-summary.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("status") != "unsigned-local-candidate-not-for-release":
        raise ValueError("El candidato no conserva el estado esperado de paquete local sin firma.")
    declared = {item["path"]: item for item in inventory.get("filesSha256", [])}
    if len(declared) != len(inventory.get("filesSha256", [])):
        raise ValueError("El inventario repite rutas.")
    if len(declared) != inventory.get("files"):
        raise ValueError("El conteo de archivos no coincide con el inventario.")

    app_errors: list[str] = []
    for relative, record in declared.items():
        path = app / Path(relative)
        if not path.is_file():
            app_errors.append(f"falta del layout: {relative}")
            continue
        if path.stat().st_size != record["bytes"] or sha256(path) != record["sha256"]:
            app_errors.append(f"layout distinto al inventario: {relative}")
    actual_app = {path.relative_to(app).as_posix() for path in app.rglob("*") if path.is_file()}
    app_errors.extend(f"archivo no inventariado en layout: {path}" for path in sorted(actual_app - declared.keys()))
    if app_errors:
        raise ValueError("\n".join(app_errors[:30]))

    zip_errors: list[str] = []
    actual_zip: set[str] = set()
    with zipfile.ZipFile(archive_path, "r") as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise zipfile.BadZipFile(f"CRC inválido en entrada ZIP: {bad_member}")
        for member in archive.infolist():
            relative = member.filename
            if relative in actual_zip:
                zip_errors.append(f"ruta ZIP duplicada: {relative}")
            actual_zip.add(relative)
            record = declared.get(relative)
            if record is None:
                zip_errors.append(f"archivo ZIP no inventariado: {relative}")
                continue
            if member.file_size != record["bytes"]:
                zip_errors.append(f"tamaño ZIP distinto al inventario: {relative}")
                continue
            digest = hashlib.sha256()
            with archive.open(member, "r") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != record["sha256"]:
                zip_errors.append(f"hash ZIP distinto al inventario: {relative}")
    zip_errors.extend(f"falta en ZIP: {path}" for path in sorted(declared.keys() - actual_zip))
    if zip_errors:
        raise ValueError("\n".join(zip_errors[:30]))

    stale: list[str] = []
    expected = expected_source_files()
    for relative, (source, label) in expected.items():
        record = declared.get(relative)
        if record is None:
            stale.append(f"archivo del candidato no declarado: {relative}")
        elif not source.is_file() or sanitized_source(source) != (record["bytes"], record["sha256"]):
            stale.append(f"desactualizado respecto a {label}: {relative}")
    if stale:
        raise ValueError("\n".join(stale[:30]))

    archive_hash = sha256(archive_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("archiveSha256") != archive_hash or summary.get("archiveBytes") != archive_path.stat().st_size:
        raise ValueError("El resumen no coincide con los bytes del ZIP actual.")
    expanded = sum(item["bytes"] for item in declared.values())
    if inventory.get("installedBytes") != expanded:
        raise ValueError("El tamaño expandido no coincide con el inventario del candidato.")
    if (summary.get("archive") != archive_path.name or summary.get("status") != inventory["status"]
            or summary.get("expandedBytes") != expanded or summary.get("fileCount") != len(declared)):
        raise ValueError("El resumen no coincide con el inventario del candidato.")

    print(json.dumps({
        "result": "verified-local-candidate",
        "status": inventory["status"],
        "candidate": str(candidate),
        "files": len(declared),
        "installedBytes": expanded,
        "archiveBytes": archive_path.stat().st_size,
        "archiveSha256": archive_hash,
        "comparedCurrentSourceFiles": len(expected),
        "releaseReady": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(f"Verificación fallida: {error}")
