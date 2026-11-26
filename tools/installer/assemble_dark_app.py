"""Assemble a local, unsigned Windows payload candidate from verified build outputs.

This is not a release publisher: it does not create a signed installer manifest,
choose licenses, download inputs, or overwrite an existing candidate.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import zipfile
import xml.etree.ElementTree as ET
from posixpath import basename
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / ".output" / "release" / "dark-app-payload-candidate-20261123-privacy-v30"
DOTNET_RELEASE = ROOT / ".output" / "release" / "rebuild-20261122"
PYTHON = ROOT / ".output" / "release" / "piper-runtime-prototype" / "python"
NODE = ROOT / ".output" / "private-node" / "node.exe"
NODE_LICENSE = ROOT / "tools" / "installer" / "third-party" / "node-24.22.3" / "LICENSE"
SPDX_INPUTS = ROOT / "tools" / "installer" / "spdx-license-inputs.json"
MPL_SOURCES = ROOT / "tools" / "installer" / "third-party" / "sources"
UI = ROOT / "dark_frontend" / ".output"
ELECTRON_DIST = ROOT / "dark_electron" / "node_modules" / "electron" / "dist"
ELECTRON_APP = ROOT / "dark_electron"

OMIT_DIRS = {
    ".git", ".pytest_cache", "__pycache__", "tests", "pruebas",
    "_voz_logs", "_voz_tmp", "_tts_temp", "_tts_cache", ".venv", ".estado_usuario",
}
OMIT_STATE_FILES = {
    "_cache_apps.json", "memoria.db", "dark_temas.json", "dark_memoria.json",
    "dark_intenciones.json", "dark_entidades.json", "dark_cache_patrones.json",
    "dark_perfil_conductual.json", "dark_neuronas.json",
}
OMIT_SUFFIXES = {".pyc", ".pyo", ".log", ".jsonl", ".db", ".sqlite", ".sqlite3", ".onnx", ".gguf", ".pt"}
# Compuerta de privacidad: nada de esto puede viajar en el payload propio de DARK.
FORBIDDEN_NAMES = {".env", ".env.local", "access-password.json", "online_coder.json", "apps.json", "gestos.log"}
FORBIDDEN_SUFFIXES = {".log", ".jsonl", ".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".onnx", ".gguf", ".pt"}
# Carpetas de terceros (runtimes) que se excluyen de la compuerta: traen sus propios .pem, etc.
THIRD_PARTY_DIRS = ("python/", "node/", "electron/runtime/", "THIRD-PARTY-NOTICES", "third-party-notices/")
BUILD_PATH_BINARY = re.compile(rb"(?i)Users.samue|U.s.e.r.s...s.a.m.u.e")
SECRET_PATTERNS = {
    "groq": re.compile(rb"gsk_[A-Za-z0-9]{20,}"),
    "google": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "openai": re.compile(rb"sk-[A-Za-z0-9_-]{32,}"),
    "github": re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "ruta-del-desarrollador": re.compile(rb"(?i)[A-Z]:[\/]+Users[\/]+samue"),
    "clave-privada": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
BINARY_SUFFIXES = {".dll", ".exe", ".pdb", ".node", ".png", ".ico", ".jpg", ".woff", ".woff2", ".zip", ".pyd"}

PIPER_OPTIONAL_PACKAGES = {
    "flatbuffers", "flatbuffers-25.12.19.dist-info",
    "onnxruntime", "onnxruntime-1.31.0.dist-info",
    "packaging", "packaging-26.3.dist-info",
    "pathvalidate", "pathvalidate-3.3.1.dist-info",
    "piper", "piper_tts-1.8.0.dist-info",
    "google", "protobuf-7.36.1.dist-info",
    "regex", "regex-2026.9.29.dist-info",
    "sentence_stream", "sentence_stream-1.3.0.dist-info",
    "wyoming_piper", "wyoming_piper-2.5.4.dist-info",
}
from vision_wheels import SIEMPRE_EN_EL_NUCLEO, dark_onnx, preparar as preparar_vision

PIPER_OPTIONAL_PACKAGES = PIPER_OPTIONAL_PACKAGES - SIEMPRE_EN_EL_NUCLEO
REQUIRED = (
    "DarkSupervisor.exe", "config/runtime.json", "python/python.exe",
    "node/node.exe", "node/LICENSE", "THIRD-PARTY-NOTICES.md",
    "services/DarkManager/DarkManager.exe",
    "services/DarkTaskManager/DarkTaskManager.exe",
    "ui/.output/server/index.mjs", "electron/runtime/electron.exe",
    "electron/app/main.cjs", "electron/app/preload.js",
    "dark_python/nucleo/dark_nucleo.py", "dark_python/voz/supervisor.py",
)


# El CPython "embeddable" ignora el directorio actual y PYTHONPATH cuando existe python312._pth,
# asi que `python -m nucleo.dark_nucleo` no encuentra los paquetes de dark_python. Se declaran aqui.
PYTHON_PTH_LINES = ["python312.zip", ".", "..\\dark_python", "Lib\\site-packages", "import site"]


def write_python_path_file(python_dir: Path) -> None:
    candidates = sorted(python_dir.glob("python*._pth"))
    if len(candidates) != 1:
        raise FileNotFoundError(f"Se esperaba un unico python*._pth en {python_dir}, hay {len(candidates)}.")
    candidates[0].write_bytes(("\n".join(PYTHON_PTH_LINES) + "\n").encode("ascii"))


def copy_tree(source: Path, destination: Path, *, filter_python_source: bool = False,
              strip_optional_piper: bool = False) -> None:
    if not source.is_dir():
        raise FileNotFoundError(f"No se encontró la entrada requerida: {source}")
    for current, directories, files in __import__("os").walk(source, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(source)
        directories[:] = sorted(
            name for name in directories
            if name not in OMIT_DIRS and not (current_path / name).is_symlink()
        )
        if strip_optional_piper and relative_dir.as_posix() == "Lib/site-packages":
            directories[:] = [name for name in directories if name not in PIPER_OPTIONAL_PACKAGES]
        for name in sorted(files):
            source_file = current_path / name
            relative = relative_dir / name
            if name.lower().endswith(".pdb"):
                continue  # simbolos de depuracion: llevan rutas del equipo de compilacion
            if strip_optional_piper and relative.as_posix() == "Lib/site-packages/COPYING":
                continue
            if source_file.is_symlink():
                continue
            if filter_python_source:
                if source_file.suffix.lower() in OMIT_SUFFIXES or name in OMIT_STATE_FILES:
                    continue
                if name.startswith(("test_", "probar_")) or name.endswith("_test.py") or name.endswith(".bak") or ".bak_" in name:
                    continue
                if name in {".env", ".env.local", "access-password.json", "online_coder.json"}:
                    continue
                if source_file.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
                    continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_file, target)


def copy_file(source: Path, destination: Path) -> None:
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(f"No se encontró el archivo requerido: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def assert_sha256(path: Path, expected: str, label: str) -> None:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    actual = hasher.hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(f"SHA-256 distinto para {label}: {actual}")


def package_license_metadata(nupkg: Path) -> tuple[str, str | None]:
    with zipfile.ZipFile(nupkg) as package:
        nuspec_path = next((name for name in package.namelist() if name.lower().endswith(".nuspec")), None)
        if nuspec_path is None:
            return "not declared in nuspec", None
        root = ET.fromstring(package.read(nuspec_path))
        node = root.find(".//{*}license")
        if node is not None:
            return f"{node.attrib.get('type', 'nuspec')}: {node.text or ''}".strip(), None
        node = root.find(".//{*}licenseUrl")
        return "license URL", node.text if node is not None else None


def copy_nupkg_legal_files(nupkg: Path, destination: Path) -> list[str]:
    markers = ("license", "licence", "notice", "copying", "copyright", "patent")
    copied: list[str] = []
    with zipfile.ZipFile(nupkg) as package:
        for member in sorted(package.infolist(), key=lambda item: item.filename.lower()):
            if member.is_dir():
                continue
            filename = basename(member.filename)
            if not filename or not any(marker in filename.lower() for marker in markers):
                continue
            target = destination / filename
            if target.exists():
                stem, suffix = target.stem, target.suffix
                target = destination / f"{stem}-{len(copied) + 1}{suffix}"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(member))
            copied.append(target.name)
    return copied


def add_npm_bundle_notices(app: Path) -> list[dict[str, object]]:
    bundle_pattern = re.compile(r"node_modules/((?:@[^/\s\"'`]+/)?[^/\s\"'`]+)")
    bundle_names: set[str] = set()
    bundle_root = app / "ui" / ".output"
    emitted_bundle_licenses: dict[str, list[dict[str, object]]] = {}
    for label, relative in (("browser", "public/dark-bundle-licenses.json"),
                            ("server", "server/dark-bundle-licenses.json")):
        source = bundle_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"Falta el inventario de licencias emitido por Vite: {source}")
        entries = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"Inventario de licencias vacío o inválido: {source}")
        destination = app / "third-party-notices" / f"npm-{label}-bundle-licenses.json"
        copy_file(source, destination)
        emitted_bundle_licenses[label] = entries
    for path in bundle_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".mjs", ".js", ".cjs", ".html", ".json"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        bundle_names.update(match.group(1) for match in bundle_pattern.finditer(content))
    bundle_names.discard(".nitro")

    import_pattern = re.compile(r"(?:from\s*|import\s*\(|require\s*\()\s*[\"']([^\"']+)[\"']")
    source_imports: set[str] = set()
    source_root = ROOT / "dark_frontend" / "src"
    for path in source_root.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".js", ".jsx"} or ".test." in path.name or ".spec." in path.name:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for imported in import_pattern.findall(content):
            if imported.startswith((".", "/", "#", "@/")):
                continue
            source_imports.add("/".join(imported.split("/")[:2]) if imported.startswith("@") else imported.split("/")[0])

    lock_paths = [ROOT / "dark_frontend" / "package-lock.json", ROOT / "dark_electron" / "package-lock.json"]
    package_roots = [ROOT / "node_modules", ROOT / "dark_frontend" / "node_modules", ROOT / "dark_electron" / "node_modules"]
    records: list[dict[str, object]] = []
    by_name: dict[str, list[dict[str, object]]] = {}
    for lock_path in lock_paths:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        for package_path, record in lock.get("packages", {}).items():
            if not package_path.startswith("node_modules/") or record.get("extraneous", False):
                continue
            lock_name = package_path.removeprefix("node_modules/")
            display_name = record.get("name") or lock_name
            entry = {"lockPath": lock_path.relative_to(ROOT).as_posix(), "packagePath": package_path,
                     "lockName": lock_name, "name": display_name, "record": record}
            records.append(entry)
            by_name.setdefault(display_name.lower(), []).append(entry)

    def package_json_for(entry: dict[str, object]) -> Path | None:
        relative_package = Path(str(entry["packagePath"]).removeprefix("node_modules/")) / "package.json"
        return next((base / relative_package for base in package_roots
                     if (base / relative_package / "").is_file()), None)

    selected: dict[tuple[str, str], dict[str, object]] = {}
    pending: list[dict[str, object]] = []
    bundle_lower = {name.lower() for name in bundle_names}
    imports_lower = {name.lower() for name in source_imports}
    for entry in records:
        record = entry["record"]
        name = str(entry["name"])
        lock_name = str(entry["lockName"])
        explicitly_in_bundle = lock_name.lower() in bundle_lower or name.lower() in bundle_lower
        imported_by_source = name.lower() in imports_lower and not record.get("dev", False)
        if explicitly_in_bundle or imported_by_source:
            pending.append(entry)
    while pending:
        entry = pending.pop()
        record = entry["record"]
        identity = (str(entry["name"]).lower(), str(record.get("version", "unknown")), str(entry["packagePath"]))
        if identity in selected:
            continue
        selected[identity] = entry
        for dependency in record.get("dependencies", {}):
            for candidate in by_name.get(dependency.lower(), []):
                candidate_record = candidate["record"]
                if candidate_record.get("dev", False):
                    continue
                if package_json_for(candidate) is None and candidate_record.get("optional", False):
                    continue
                pending.append(candidate)

    source_overrides = json.loads((ROOT / "tools" / "installer" / "npm-license-inputs.json").read_text(encoding="utf-8"))["inputs"]
    for source_record in source_overrides:
        source_path = ROOT / source_record["path"]
        assert_sha256(source_path, source_record["sha256"], "npm license input " + source_path.name)

    grouped: dict[tuple[str, str], dict[str, object]] = {}
    for entry in selected.values():
        record = entry["record"]
        name, version = str(entry["name"]), str(record.get("version", "unknown"))
        grouped.setdefault((name.lower(), version), {"name": name, "version": version, "entries": []})["entries"].append(entry)

    notice_dir = app / "third-party-notices" / "npm"
    rows = ["", "## Dependencias npm del frontend", "",
            "El build de Vite también emite inventarios con los paquetes y textos de licencia presentes en los módulos compilados: `third-party-notices/npm-browser-bundle-licenses.json` y `third-party-notices/npm-server-bundle-licenses.json`.",
            "Inventario conservador: paquetes importados por el código de la UI, sus dependencias de producción y rutas de módulos conservadas por el output. Puede incluir dependencias que el tree-shaking eliminó; no incluye paquetes solo de desarrollo salvo que una ruta aparezca en el output.",
            "", "| Paquete | Versión | Licencia declarada | Archivos de licencia incluidos |", "|---|---:|---|---|"]
    inventory: list[dict[str, object]] = []
    missing: list[str] = []
    for _, item in sorted(grouped.items()):
        display_name, version = str(item["name"]), str(item["version"])
        entries = item["entries"]
        package_json = next((package_json_for(entry) for entry in entries if package_json_for(entry) is not None), None)
        if package_json is None:
            missing.append(f"{display_name}@{version}: package directory not found")
            continue
        metadata = json.loads(package_json.read_text(encoding="utf-8"))
        license_value = metadata.get("license") or entries[0]["record"].get("license") or "undeclared"
        if display_name == "victory-vendor":
            license_value = "MIT + vendored ISC/BSD-3-Clause (vendored notices included)"
        if isinstance(license_value, (dict, list)):
            license_value = json.dumps(license_value, ensure_ascii=False, sort_keys=True)
        target_dir = notice_dir / f"{display_name.replace('/', '+')}@{version}"
        markers = ("license", "licence", "notice", "copying", "copyright", "patent")
        source_files = [path for path in package_json.parent.rglob("*") if path.is_file()
                        and "node_modules" not in path.relative_to(package_json.parent).parts
                        and any(marker in path.name.lower() for marker in markers)]
        copied: list[str] = []
        for source_file in sorted(source_files, key=lambda path: path.relative_to(package_json.parent).as_posix().lower()):
            relative_source = source_file.relative_to(package_json.parent)
            target = target_dir / relative_source
            copy_file(source_file, target)
            copied.append(f"`{target.relative_to(app).as_posix()}`")
        for license_input in source_overrides:
            if any(target.get("name", "").lower() == display_name.lower()
                   and target.get("version", "").lower() == version.lower()
                   for target in license_input["appliesTo"]):
                source_file = ROOT / license_input["path"]
                target = target_dir / source_file.name
                copy_file(source_file, target)
                copied.append(f"`{target.relative_to(app).as_posix()}`")
        if not copied:
            missing.append(f"{display_name}@{version}: no license or notice text found")
        rows.append(f"| {display_name} | {version} | {license_value} | {', '.join(sorted(set(copied))) or 'No license text found'} |")
        inventory.append({"name": display_name, "version": version, "license": license_value,
                          "lockPaths": sorted({str(entry['lockPath']) for entry in entries}),
                          "lockPackagePaths": sorted({str(entry['packagePath']) for entry in entries}),
                          "licenseFiles": sorted(set(copied))})

    if missing:
        raise FileNotFoundError("Faltan avisos npm en la clausura del frontend: " + "; ".join(missing))
    (app / "THIRD-PARTY-NOTICES.md").write_text(
        (app / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8") + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    inventory_path = app / "third-party-notices" / "npm-bundle-inventory.json"
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_text(json.dumps({"scope": "conservative frontend source import graph and production dependency closure; exact Vite module license records are preserved separately", "viteEmittedBundles": {key: [{"name": item.get("name"), "version": item.get("version"), "identifier": item.get("identifier")} for item in value] for key, value in emitted_bundle_licenses.items()}, "entries": inventory}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return inventory


def add_third_party_notices(app: Path) -> None:
    node_inputs = json.loads((ROOT / "tools" / "installer" / "node-24.22.3-input.json").read_text(encoding="utf-8"))
    node_license_inputs = node_inputs["license"]
    assert_sha256(NODE, node_inputs["sha256"], "Node.js 24.22.3")
    assert_sha256(ROOT / node_license_inputs["path"], node_license_inputs["sha256"], "Node.js LICENSE 24.22.3")
    copy_file(NODE_LICENSE, app / "node" / "LICENSE")

    spdx_inputs = json.loads(SPDX_INPUTS.read_text(encoding="utf-8"))
    for license_record in spdx_inputs["licenses"]:
        license_source = ROOT / license_record["path"]
        assert_sha256(license_source, license_record["sha256"], f"SPDX {license_record['spdxId']}")
        copy_file(license_source, app / "third-party-notices" / "licenses" / f"{license_record['spdxId']}.txt")

    sqlcipher = json.loads((ROOT / "tools" / "installer" / "sqlcipher-input.json").read_text(encoding="utf-8"))
    module_relative = Path(sqlcipher["modulePath"]).relative_to("app")
    sqlcipher_module = app / module_relative
    assert_sha256(sqlcipher_module, sqlcipher["moduleSha256"], "bundled SQLCipher extension")
    sqlcipher_license = ROOT / sqlcipher["nativeLibrary"]["licensePath"]
    assert_sha256(sqlcipher_license, sqlcipher["nativeLibrary"]["licenseSha256"], "SQLCipher 4.20.0 LICENSE")
    copy_file(sqlcipher_license, app / "third-party-notices" / "licenses" / "SQLCipher-4.20.0-BSD-3-Clause.md")

    source_inputs = json.loads((ROOT / "tools" / "installer" / "mpl-source-inputs.json").read_text(encoding="utf-8"))
    for source_record in source_inputs["sources"]:
        source_file = ROOT / source_record["path"]
        assert_sha256(source_file, source_record["sha256"], f"source {source_record['packageId']} {source_record['version']}")
        copy_file(source_file, app / "third-party-notices" / "source" / "MPL-2.0" / source_file.name)

    notice_root = app / "third-party-notices" / "dotnet"
    app_deps = [DOTNET_RELEASE / "DarkSupervisor" / "DarkSupervisor.deps.json"]
    app_deps.extend(sorted(DOTNET_RELEASE.glob("DarkManager/*.deps.json")))
    app_deps.extend(sorted(DOTNET_RELEASE.glob("DarkTaskManager/*.deps.json")))
    packages: dict[tuple[str, str], tuple[str, list[str]]] = {}
    for deps_path in app_deps:
        if not deps_path.is_file():
            raise FileNotFoundError(f"No se encontró el inventario .NET: {deps_path}")
        deps = json.loads(deps_path.read_text(encoding="utf-8"))
        for identity, record in deps.get("libraries", {}).items():
            if record.get("type") != "package":
                continue
            package_id, version = identity.rsplit("/", 1)
            key = (package_id.lower(), version.lower())
            source = deps_path.parent.name
            previous = packages.get(key)
            packages[key] = (package_id, sorted(set((previous[1] if previous else []) + [source])))

    for package_id, version in (
        ("Microsoft.NETCore.App.Runtime.win-x64", "10.0.15"),
        ("Microsoft.AspNetCore.App.Runtime.win-x64", "10.0.15"),
        ("Microsoft.NETCore.App.Host.win-x64", "10.0.15"),
    ):
        packages[(package_id.lower(), version.lower())] = (package_id, ["shared runtime"])

    index_lines = [
        "# Avisos de terceros de D.A.R.K. — candidato local",
        "",
        "Este archivo y su carpeta documentan componentes del candidato. No son el SBOM ni una aprobación legal de release.",
        "",
        "## Runtimes y componentes con licencia incluida",
        "",
        "- Node.js 24.22.3: `node/LICENSE` (licencia y avisos incluidos por el proyecto Node.js).",
        "- CPython 3.12.16: `python/LICENSE.txt`; las ruedas Python incluyen sus textos en `python/Lib/site-packages/*.dist-info/licenses/`.",
        "- PDF: `fpdf2` 2.9.0 declara LGPL-3.0-only y conserva su fuente Python y licencia en `python/Lib/site-packages/fpdf/` y `python/Lib/site-packages/fpdf2-2.9.0.dist-info/licenses/LICENSE`; `pypdfium2` 5.15.2 incluye PDFium y sus avisos de terceros bajo `python/Lib/site-packages/pypdfium2-5.15.2.dist-info/licenses/` (ver inventario de payload para hash y versión del binario). Los términos propios de DARK no sustituyen estas licencias.",
        "- SQLCipher Community 4.20.0 está enlazado estáticamente dentro de `python/Lib/site-packages/sqlcipher3/_sqlite3.cp312-win_amd64.pyd`; su aviso BSD-3-Clause está en `third-party-notices/licenses/SQLCipher-4.20.0-BSD-3-Clause.md`. El wrapper `sqlcipher3` conserva su licencia propia en `.dist-info/licenses/`.",
        "- Electron 45.3.3: `electron/runtime/LICENSE` y `electron/runtime/LICENSES.chromium.html`.",
        "- Los avisos .NET que venían en los paquetes NuGet locales están bajo `third-party-notices/dotnet/`.",
        "- Textos estándar MIT y MPL-2.0: `third-party-notices/licenses/`; fuentes correspondientes a paquetes MPL: `third-party-notices/source/MPL-2.0/`.",
        "",
        "## Paquetes NuGet del payload",
        "",
        "| Paquete | Versión | Licencia declarada en `.nuspec` | Texto copiado | Usado por |",
        "|---|---:|---|---|---|",
    ]
    for (package_id, version), (display_name, used_by) in sorted(packages.items()):
        cache_dir = Path.home() / ".nuget" / "packages" / package_id.lower() / version.lower()
        nupkg = cache_dir / f"{package_id.lower()}.{version.lower()}.nupkg"
        if not nupkg.is_file():
            raise FileNotFoundError(f"Falta el paquete NuGet en caché local: {nupkg}")
        package_destination = notice_root / f"{package_id}@{version}"
        license_declaration, license_url = package_license_metadata(nupkg)
        legal_files = copy_nupkg_legal_files(nupkg, package_destination)
        file_references = [f"`{package_destination.relative_to(app).as_posix()}/{name}`" for name in legal_files]
        source_record = next((record for record in source_inputs["sources"]
                              if record["packageId"].lower() == package_id.lower()
                              and record["version"].lower() == version.lower()), None)
        if source_record:
            file_references.append("`third-party-notices/licenses/MPL-2.0.txt`")
            file_references.append(f"`third-party-notices/source/MPL-2.0/{Path(source_record['path']).name}`")
        elif "mit" in license_declaration.lower():
            file_references.append("`third-party-notices/licenses/MIT.txt`")
        declared_text = license_declaration
        if package_id.lower() == "mono.posix.netstandard" and version == "1.0.0":
            declared_text = "MIT + BSD-3-Clause (Mono license set; exact files covered by each license require upstream confirmation)"
            file_references.extend(("`third-party-notices/licenses/MIT.txt`",
                                    "`third-party-notices/licenses/BSD-3-Clause.txt`"))
        files_text = ", ".join(sorted(set(file_references))) or "No viene en el `.nupkg`; licencia pendiente de conseguir"
        if license_url:
            declared_text += f" ([referencia]({license_url}))"
        index_lines.append(
            f"| {display_name} | {version} | {declared_text} | {files_text} | {', '.join(used_by)} |"
        )

    (app / "THIRD-PARTY-NOTICES.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    add_npm_bundle_notices(app)


def sanitize_ui_paths(app: Path) -> None:
    """Quita la ruta absoluta del equipo de build de los manifiestos de la UI (solo metadatos)."""
    prefix = (ROOT.as_posix() + "/").encode("utf-8")
    for path in (app / "ui").rglob("*.mjs"):
        data = path.read_bytes()
        if prefix in data:
            path.write_bytes(data.replace(prefix, b""))


def privacy_gate(app: Path) -> None:
    """Falla si el layout contiene datos del desarrollador o secretos en archivos propios."""
    findings: list[str] = []
    for path in sorted(p for p in app.rglob("*") if p.is_file()):
        relative = path.relative_to(app).as_posix()
        if relative.startswith(THIRD_PARTY_DIRS):
            continue
        name = path.name.lower()
        if relative == "dark.onnx" and path.read_bytes() == dark_onnx().read_bytes():
            continue  # la única excepción a «.onnx»: la palabra de activación aprobada, byte a byte
        if name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"archivo prohibido: {relative}")
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            # Binarios propios (.dll/.exe): solo se busca la ruta del equipo de compilacion
            # (la ruta del .pdb queda incrustada), en UTF-8 y UTF-16.
            if path.suffix.lower() in {".dll", ".exe", ".pdb"} and BUILD_PATH_BINARY.search(path.read_bytes()):
                findings.append(f"ruta del equipo de compilacion en binario: {relative}")
            continue
        data = path.read_bytes()
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(data):
                findings.append(f"posible secreto ({label}): {relative}")
    if findings:
        raise ValueError("Compuerta de privacidad fallida:\n  " + "\n  ".join(findings))


def file_inventory(root: Path) -> tuple[list[dict[str, object]], int]:
    items: list[dict[str, object]] = []
    total = 0
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        items.append({"path": relative, "bytes": size, "sha256": digest})
        total += size
    return items, total


def main() -> None:
    resume_candidate = OUTPUT.exists()
    app = OUTPUT / "app"
    summary_path = OUTPUT / "candidate-summary.json"
    archive_path = OUTPUT / "dark-app-payload-candidate.zip"
    if resume_candidate:
        if not app.is_dir() or summary_path.exists() or archive_path.exists():
            if not app.is_dir() or summary_path.exists():
                raise FileExistsError(f"El destino ya existe y no está en estado reanudable: {OUTPUT}")
            inventory_path = OUTPUT / "candidate-inventory.json"
            if not inventory_path.is_file() or not archive_path.is_file():
                raise FileExistsError(f"El destino ya existe y no está en estado reanudable: {OUTPUT}")
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
            with zipfile.ZipFile(archive_path, "r") as existing_archive:
                corrupt_entry = existing_archive.testzip()
                entries = existing_archive.infolist()
                expanded_bytes = sum(item.file_size for item in entries)
            if corrupt_entry is not None:
                raise zipfile.BadZipFile(f"Entrada ZIP dañada en el candidato: {corrupt_entry}")
            if len(entries) != inventory["files"] or expanded_bytes != inventory["installedBytes"]:
                raise zipfile.BadZipFile("El ZIP no coincide con el inventario del candidato.")
            hasher = hashlib.sha256()
            with archive_path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    hasher.update(chunk)
            summary = {
                "archive": archive_path.name,
                "archiveBytes": archive_path.stat().st_size,
                "archiveSha256": hasher.hexdigest(),
                "expandedBytes": expanded_bytes,
                "fileCount": len(entries),
                "status": inventory["status"],
            }
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return
        print(f"Finalizando el candidato local incompleto: {OUTPUT}", flush=True)
    else:
        OUTPUT.mkdir(parents=True)
        app.mkdir()

        # Runtime and code payload.
        # Wyoming remains in the core as the permissive client protocol. Piper,
        # ONNX Runtime and its engine dependencies ship only in the optional sidecar.
        copy_tree(PYTHON, app / "python", strip_optional_piper=True)
        # Visión y voz de entrada (OpenCV, MediaPipe…): ruedas verificadas por huella.
        copy_tree(preparar_vision(), app / "python" / "Lib" / "site-packages")
        write_python_path_file(app / "python")
        copy_tree(DOTNET_RELEASE / "DarkSupervisor", app)
        copy_tree(DOTNET_RELEASE / "DarkManager", app / "services" / "DarkManager")
        copy_tree(DOTNET_RELEASE / "DarkTaskManager", app / "services" / "DarkTaskManager")
        copy_tree(UI, app / "ui" / ".output")
        copy_tree(ELECTRON_DIST, app / "electron" / "runtime")
        for name in ("main.cjs", "reset.cjs", "preload.js", "package.json", "package-lock.json"):
            copy_file(ELECTRON_APP / name, app / "electron" / "app" / name)
        copy_file(NODE, app / "node" / "node.exe")
        copy_file(dark_onnx(), app / "dark.onnx")
        add_third_party_notices(app)
        copy_tree(ROOT / "dark_python", app / "dark_python", filter_python_source=True)
        copy_file(ROOT / "config" / "runtime.json", app / "config" / "runtime.json")
        copy_file(ROOT / "config" / "runtime.schema.json", app / "config" / "runtime.schema.json")
        copy_file(ROOT / "config" / "model-profiles.json", app / "config" / "model-profiles.json")

    missing = [relative for relative in REQUIRED if not (app / relative).is_file()]
    if missing:
        raise FileNotFoundError("Faltan archivos del layout instalado: " + ", ".join(missing))

    sanitize_ui_paths(app)
    privacy_gate(app)
    files, installed_bytes = file_inventory(app)
    manifest = {
        "schemaVersion": 1,
        "status": "unsigned-local-candidate-not-for-release",
        "target": "Windows x64",
        "appVersion": "unassigned",
        "sourceState": "local workspace at assembly time",
        "files": len(files),
        "installedBytes": installed_bytes,
        "excludedUserData": True,
        "releaseManifestCreated": False,
        "filesSha256": files,
    }
    (OUTPUT / "candidate-inventory.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    temporary_archive = OUTPUT / ".dark-app-payload-candidate.zip.tmp"
    with zipfile.ZipFile(temporary_archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in sorted(p for p in app.rglob("*") if p.is_file()):
            relative = path.relative_to(app).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                shutil.copyfileobj(source, target, length=1024 * 1024)

    hasher = hashlib.sha256()
    with temporary_archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    archive_hash = hasher.hexdigest()
    os.replace(temporary_archive, archive_path)
    summary = {
        "archive": archive_path.name,
        "archiveBytes": archive_path.stat().st_size,
        "archiveSha256": archive_hash,
        "expandedBytes": installed_bytes,
        "fileCount": len(files),
        "status": manifest["status"],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
