"""Generate a preliminary license/component inventory for a local DARK payload.

The output is evidence for release review, not a legal conclusion or a final
SBOM. It intentionally reports missing license evidence instead of guessing.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / ".output" / "release" / "dark-app-payload-candidate-20261122-compliance-v10"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_files(directory: Path, app: Path) -> list[str]:
    return sorted(path.relative_to(app).as_posix() for path in directory.rglob("*") if path.is_file())


def python_components(app: Path) -> list[dict[str, Any]]:
    site_packages = app / "python" / "Lib" / "site-packages"
    components = []
    for metadata in sorted(site_packages.glob("*.dist-info/METADATA")):
        fields: dict[str, str] = {}
        classifiers = []
        for line in metadata.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith(("Name: ", "Version: ", "License: ", "License-Expression: ")):
                key, value = line.split(": ", 1)
                fields[key] = value
            elif line.startswith("Classifier: License :: "):
                classifiers.append(line.removeprefix("Classifier: License :: "))
        license_files = relative_files(metadata.parent / "licenses", app) if (metadata.parent / "licenses").is_dir() else []
        expression = fields.get("License-Expression") or fields.get("License") or "; ".join(classifiers) or None
        components.append({
            "type": "library",
            "ecosystem": "pypi",
            "name": fields.get("Name", metadata.parent.name),
            "version": fields.get("Version"),
            "licenseExpression": expression,
            "licenseEvidence": "METADATA" if expression else ("bundled license files" if license_files else "missing"),
            "licenseFiles": license_files,
            "distributionMetadata": metadata.relative_to(app).as_posix(),
        })
    return components


def npm_components() -> list[dict[str, Any]]:
    components: dict[tuple[str, str], dict[str, Any]] = {}
    lock_paths = [ROOT / "dark_frontend" / "package-lock.json", ROOT / "dark_electron" / "package-lock.json"]
    package_roots = [ROOT / "node_modules", ROOT / "dark_frontend" / "node_modules", ROOT / "dark_electron" / "node_modules"]
    for lock in lock_paths:
        data = read_json(lock)
        for package_path, record in data.get("packages", {}).items():
            if not package_path.startswith("node_modules/"):
                continue
            package_name = record.get("name") or package_path.removeprefix("node_modules/")
            version = record.get("version", "unknown")
            key = (package_name.lower(), version)
            relative_package = Path(package_path.removeprefix("node_modules/")) / "package.json"
            package_json = next((base / relative_package for base in package_roots if (base / relative_package).is_file()), None)
            license_value = None
            if package_json:
                try:
                    raw_license = read_json(package_json).get("license")
                    license_value = raw_license if isinstance(raw_license, str) else raw_license
                except (OSError, json.JSONDecodeError):
                    pass
            existing = components.get(key)
            lock_reference = lock.relative_to(ROOT).as_posix()
            if existing:
                existing["lockfiles"].append(lock_reference)
                existing["lockPackagePaths"].append(package_path)
                existing["lockRecords"] += 1
                existing["devOnly"] = existing["devOnly"] and bool(record.get("dev", False))
                existing["optional"] = existing["optional"] or bool(record.get("optional", False))
                if existing["licenseExpression"] is None and license_value:
                    existing["licenseExpression"] = license_value
                    existing["licenseEvidence"] = "installed package.json"
                existing["packagePresent"] = existing["packagePresent"] or bool(package_json)
                continue
            components[key] = {
                "type": "library",
                "ecosystem": "npm",
                "name": package_name,
                "version": version,
                "licenseExpression": license_value,
                "licenseEvidence": "installed package.json" if license_value else ("no local package metadata" if not package_json else "license field missing"),
                "packagePresent": bool(package_json),
                "devOnly": bool(record.get("dev", False)),
                "optional": bool(record.get("optional", False)),
                "lockfiles": [lock_reference],
                "lockPackagePaths": [package_path],
                "lockRecords": 1,
            }
    for component in components.values():
        component["lockfiles"] = sorted(set(component["lockfiles"]))
        component["lockPackagePaths"] = sorted(set(component["lockPackagePaths"]))
    return sorted(components.values(), key=lambda item: (item["name"].lower(), item["version"]))


def npm_bundle_references(app: Path, components: list[dict[str, Any]]) -> dict[str, Any]:
    """Collect package names explicitly referenced by generated UI bundle paths.

    This is evidence for scoping, not a complete dependency/SBOM extractor: minified
    or inlined code can lose its original package path.
    """
    bundle_root = app / "ui" / ".output"
    pattern = re.compile(r"node_modules/((?:@[^/\s\"'`]+/)?[^/\s\"'`]+)")
    names: set[str] = set()
    if bundle_root.is_dir():
        for path in bundle_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".mjs", ".js", ".cjs", ".html", ".json"}:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            names.update(match.group(1) for match in pattern.finditer(content))
    names.discard(".nitro")
    by_name: dict[str, list[dict[str, Any]]] = {}
    for component in components:
        by_name.setdefault(component["name"].lower(), []).append(component)
    mapped = [
        component for component in components
        if component["name"].lower() in {name.lower() for name in names}
        or any(path.removeprefix("node_modules/").lower() in {name.lower() for name in names}
               for path in component["lockPackagePaths"])
    ]
    return {
        "method": "package paths explicitly present in generated UI bundle text",
        "complete": False,
        "packageNamesReferenced": sorted(names),
        "matchedLockComponents": mapped,
        "unmatchedNames": sorted(
            name for name in names
            if name.lower() not in by_name
            and not any(path.removeprefix("node_modules/").lower() == name.lower()
                        for component in components for path in component["lockPackagePaths"])
        ),
        "limitation": "Bundlers may inline, minify, or tree-shake code without retaining package paths; use as scoping evidence, not as a final SBOM.",
    }


def vite_bundle_licenses(app: Path) -> dict[str, Any]:
    """Read Vite's module-level license metadata emitted for both build environments."""
    result: dict[str, Any] = {}
    for label, relative in (("browser", "ui/.output/public/dark-bundle-licenses.json"),
                            ("server", "ui/.output/server/dark-bundle-licenses.json")):
        path = app / relative
        if not path.is_file():
            result[label] = {"present": False, "entries": []}
            continue
        entries = read_json(path)
        result[label] = {
            "present": True,
            "file": relative,
            "entries": [{"name": item.get("name"), "version": item.get("version"),
                         "licenseExpression": item.get("identifier"),
                         "licenseTextIncluded": bool(item.get("text"))} for item in entries],
        }
    result["complete"] = all(result[key]["present"] for key in ("browser", "server"))
    return result


def pdf_component_evidence(app: Path) -> dict[str, Any]:
    site = app / "python" / "Lib" / "site-packages"
    dll = site / "pypdfium2_raw" / "pdfium.dll"
    version_path = site / "pypdfium2_raw" / "version.json"
    package_license_root = site / "pypdfium2-5.15.2.dist-info" / "licenses"
    fpdf_root = site / "fpdf2-2.9.0.dist-info"
    lock_text = (ROOT / "dark_python" / "requirements-core-win_amd64.lock.txt").read_text(encoding="utf-8")
    match = re.search(r"(?ms)^pypdfium2==5\.15\.2\s*\\\s*\n\s*--hash=sha256:([0-9a-f]{64})", lock_text)
    license_files = relative_files(package_license_root, app) if package_license_root.is_dir() else []
    return {
        "fpdf2": {
            "name": "fpdf2", "version": "2.9.0", "licenseExpression": "LGPL-3.0-only",
            "licenseFile": "python/Lib/site-packages/fpdf2-2.9.0.dist-info/licenses/LICENSE",
            "licenseFilePresent": (fpdf_root / "licenses" / "LICENSE").is_file(),
            "pythonSourcePresent": any((site / "fpdf").glob("*.py")),
            "distributionMetadata": "python/Lib/site-packages/fpdf2-2.9.0.dist-info/METADATA",
        },
        "pypdfium2": {
            "name": "pypdfium2", "version": "5.15.2",
            "declaredLicenses": "BSD-3-Clause, Apache-2.0, dependency licenses",
            "wheelSha256ExpectedFromLock": match.group(1) if match else None,
            "pdfium": {
                "version": json.loads(version_path.read_text(encoding="utf-8")) if version_path.is_file() else None,
                "binary": "python/Lib/site-packages/pypdfium2_raw/pdfium.dll",
                "sha256": hashlib.sha256(dll.read_bytes()).hexdigest() if dll.is_file() else None,
            },
            "licenseFiles": license_files,
            "licenseFileCount": len(license_files),
            "buildEvidence": "pypdfium2 5.15.2 release identifies win_amd64 as SBLD (source-built); wheel metadata reports sourcebuild-toolchained. Match provenance to the exact locked wheel before release.",
        },
    }


def nuget_components(app: Path) -> list[dict[str, Any]]:
    packages: dict[tuple[str, str], dict[str, Any]] = {}
    deps_files = [app / "DarkSupervisor.deps.json"]
    deps_files.extend(sorted((app / "services").glob("*/*.deps.json")))
    deps_files = [path for path in deps_files if path.is_file()]
    for deps in deps_files:
        data = read_json(deps)
        for library, record in data.get("libraries", {}).items():
            if record.get("type") != "package":
                continue
            name, version = library.rsplit("/", 1)
            key = (name.lower(), version.lower())
            if key in packages:
                packages[key]["usedBy"].append(deps.relative_to(app).as_posix())
                continue
            nuspec = Path.home() / ".nuget" / "packages" / key[0] / key[1] / f"{key[0]}.nuspec"
            license_value = None
            evidence = "missing local nuspec"
            license_file = None
            license_url = None
            if nuspec.is_file():
                try:
                    tree = ET.parse(nuspec)
                    node = tree.find(".//{*}license")
                    if node is not None:
                        license_value = node.text or None
                        evidence = node.attrib.get("type", "nuspec")
                        if evidence == "file" and license_value:
                            license_file = license_value
                    if license_value is None:
                        node = tree.find(".//{*}licenseUrl")
                        if node is not None:
                            license_url = node.text
                            evidence = "licenseUrl in nuspec"
                except ET.ParseError:
                    evidence = "unreadable nuspec"
            if name.lower() == "mono.posix.netstandard" and version == "1.0.0":
                license_value = "MIT AND BSD-3-Clause (license URL points to Mono license set)"
                evidence = "Mono licenseUrl plus upstream project license set; package contains managed and native Windows assets"
                license_file = None
            packages[key] = {
                "type": "library",
                "ecosystem": "nuget",
                "name": name,
                "version": version,
                "licenseExpression": license_value,
                "licenseEvidence": evidence,
                "licenseFileReference": license_file,
                "licenseUrl": license_url,
                "licenseFiles": ([f"third-party-notices/licenses/{name}.txt"] if (app / "third-party-notices" / "licenses" / f"{name}.txt").is_file() else [])
                                + [path for path in ["third-party-notices/licenses/MIT.txt", "third-party-notices/licenses/BSD-3-Clause.txt"] if (app / path).is_file()] if name.lower() == "mono.posix.netstandard" else [],
                "usedBy": [deps.relative_to(app).as_posix()],
            }
    for component in packages.values():
        component["usedBy"] = sorted(set(component["usedBy"]))
    return sorted(packages.values(), key=lambda item: (item["name"].lower(), item["version"]))


def runtime_components(candidate: Path, app: Path) -> list[dict[str, Any]]:
    file_records = read_json(candidate / "candidate-inventory.json")["filesSha256"]
    hashes = {item["path"]: item["sha256"] for item in file_records}
    node_input = read_json(ROOT / "tools" / "installer" / "node-24.22.3-input.json")
    electron_lock = read_json(ROOT / "dark_electron" / "package-lock.json")
    electron_version = electron_lock.get("packages", {}).get("node_modules/electron", {}).get("version")
    dotnet_versions = {}
    for runtimeconfig in [app / "DarkSupervisor.runtimeconfig.json", *sorted((app / "services").glob("*/*.runtimeconfig.json"))]:
        if not runtimeconfig.is_file():
            continue
        config = read_json(runtimeconfig)
        for framework in config.get("runtimeOptions", {}).get("includedFrameworks", []):
            dotnet_versions[framework["name"]] = framework["version"]
    return [
        {
            "type": "framework",
            "ecosystem": "cpython",
            "name": "CPython",
            "version": "3.12.16",
            "licenseEvidence": "license text included",
            "licenseFiles": ["python/LICENSE.txt"] if (app / "python" / "LICENSE.txt").is_file() else [],
        },
        {
            "type": "framework",
            "ecosystem": "nodejs",
            "name": "Node.js",
            "version": node_input["version"],
            "sha256": hashes.get("node/node.exe", node_input.get("sha256")),
            "licenseEvidence": "versioned Node.js license and notices included" if (app / "node" / "LICENSE").is_file() else "missing from payload",
            "licenseFiles": ["node/LICENSE"] if (app / "node" / "LICENSE").is_file() else [],
        },
        {
            "type": "framework",
            "ecosystem": "electron",
            "name": "Electron",
            "version": electron_version,
            "licenseEvidence": "license and Chromium notices included",
            "licenseFiles": [
                path for path in ["electron/runtime/LICENSE", "electron/runtime/LICENSES.chromium.html"]
                if (app / path).is_file()
            ],
        },
        {
            "type": "framework",
            "ecosystem": "dotnet",
            "name": ".NET runtime",
            "version": "; ".join(f"{name} {version}" for name, version in sorted(dotnet_versions.items())),
            "licenseEvidence": "runtime version verified; candidate notice index included" if (app / "THIRD-PARTY-NOTICES.md").is_file() else "runtime version verified; consolidated notice not found in payload",
            "licenseFiles": ["THIRD-PARTY-NOTICES.md"] if (app / "THIRD-PARTY-NOTICES.md").is_file() else [],
        },
    ]


def native_third_party_components(app: Path) -> list[dict[str, Any]]:
    sqlcipher = read_json(ROOT / "tools" / "installer" / "sqlcipher-input.json")
    module_relative = Path(sqlcipher["modulePath"]).relative_to("app")
    module = app / module_relative
    digest = hashlib.sha256(module.read_bytes()).hexdigest() if module.is_file() else None
    license_record = sqlcipher["nativeLibrary"]
    return [{
        "type": "library",
        "ecosystem": "native-bundled-in-python-wheel",
        "name": license_record["name"],
        "version": license_record["version"],
        "sqliteBase": license_record["sqliteBase"],
        "licenseExpression": license_record["license"],
        "licenseEvidence": "SQLCipher PRAGMA cipher_version and sqlite_version runtime probe; versioned upstream license text included",
        "licenseFile": "third-party-notices/licenses/SQLCipher-4.20.0-BSD-3-Clause.md" if (app / "third-party-notices/licenses/SQLCipher-4.20.0-BSD-3-Clause.md").is_file() else None,
        "containingBinary": module_relative.as_posix(),
        "containingBinarySha256": digest,
        "expectedBinarySha256": sqlcipher["moduleSha256"],
        "licenseSource": license_record["licenseUri"],
    }]


def kit_coder_components(app: Path) -> list[dict[str, Any]]:
    """Terceros del kit del coder (dark_python/especialistas/kit): viajan dentro de
    cada web que D.A.R.K. genera, con su licencia al lado."""
    kit = app / "dark_python" / "especialistas" / "kit"
    paquete = kit / "inmersivo" / "inmersivo.min.js"
    componentes: list[dict[str, Any]] = [{
        "type": "library",
        "ecosystem": "bundled-javascript",
        "name": "three",
        "version": "0.170.0",
        "licenseExpression": "MIT",
        "licenseEvidence": "SPDX header kept by esbuild --legal-comments=eof; full text alongside",
        "licenseFile": "dark_python/especialistas/kit/inmersivo/LICENCIAS.txt"
        if (kit / "inmersivo" / "LICENCIAS.txt").is_file() else None,
        "containingFile": "dark_python/especialistas/kit/inmersivo/inmersivo.min.js",
        "containingFileSha256": hashlib.sha256(paquete.read_bytes()).hexdigest() if paquete.is_file() else None,
    }]
    for familia in ("space-grotesk", "jetbrains-mono", "ibm-plex-sans", "ibm-plex-mono", "fraunces", "figtree"):
        componentes.append({
            "type": "font",
            "ecosystem": "fontsource-woff2",
            "name": familia,
            "licenseExpression": "OFL-1.1",
            "licenseFile": "dark_python/especialistas/kit/fuentes/LICENCIAS.txt"
            if (kit / "fuentes" / "LICENCIAS.txt").is_file() else None,
            "files": sorted(p.name for p in (kit / "fuentes").glob(f"{familia}-*.woff2")),
        })
    return componentes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    app = candidate / "app"
    if not app.is_dir():
        raise SystemExit(f"No existe el payload del candidato: {app}")

    summary = read_json(candidate / "candidate-summary.json")
    npm = npm_components()
    npm_notice_path = app / "third-party-notices" / "npm-bundle-inventory.json"
    npm_notice_inventory = read_json(npm_notice_path) if npm_notice_path.is_file() else {"entries": []}
    gaps = []
    if not (app / "node" / "LICENSE").is_file():
        gaps.append("Node.js LICENSE and bundled third-party notices are absent from the payload.")
    gaps.extend([
        "Vite emits module-level npm license metadata for the browser and SSR bundles; audit remains necessary for assets, Electron's separate runtime, embedded vendor notices, and package license scope beyond the nearest module package.",
        "Mono.Posix.NETStandard 1.0.0 is transitively included by LibreHardwareMonitor; MIT and BSD-3-Clause texts are included from the Mono license set, but upstream confirmation of which package files carry each license is still needed.",
        "fpdf2 2.9.0 LGPL-3.0-only source and license are included; legal review must confirm DARK terms preserve LGPL rights and the shipped layout permits replacement/modification of the library.",
        "pypdfium2/PDFium version, DLL hash and wheel license files are inventoried; final SBOM/legal review must correlate dependency notices to the exact Windows wheel build and confirm no applicable notice is missing.",
        "DARK proprietary terms and privacy notice remain draft and require owner/legal approval.",
    ])
    mpl_sources = read_json(ROOT / "tools" / "installer" / "mpl-source-inputs.json")["sources"]
    missing_mpl = [record["packageId"] for record in mpl_sources if not (app / "third-party-notices" / "source" / "MPL-2.0" / Path(record["path"]).name).is_file()]
    if missing_mpl:
        gaps.append("MPL corresponding-source snapshots missing from payload: " + ", ".join(missing_mpl))
    inventory = {
        "schemaVersion": 1,
        "status": "preliminary-not-for-release",
        "purpose": "Local license evidence inventory; not a final SBOM or legal approval.",
        "candidate": {
            "archive": summary["archive"],
            "archiveBytes": summary["archiveBytes"],
            "archiveSha256": summary["archiveSha256"],
            "fileCount": summary["fileCount"],
        },
        "runtimeComponents": runtime_components(candidate, app),
        "nativeThirdPartyComponents": native_third_party_components(app),
        "kitCoderComponents": kit_coder_components(app),
        "pythonDistributions": python_components(app),
        "npmLockComponents": npm,
        "npmBundleReferences": npm_bundle_references(app, npm),
        "viteBundleLicenses": vite_bundle_licenses(app),
        "pdfComponentEvidence": pdf_component_evidence(app),
        "npmNoticeComponents": npm_notice_inventory,
        "nugetPackages": nuget_components(app),
        "mplCorrespondingSource": mpl_sources,
        "gaps": gaps,
    }
    output = args.output or (candidate / "payload-license-inventory.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "python": len(inventory["pythonDistributions"]),
        "npm_unique": len(npm),
        "npm_without_local_package_metadata": sum(not item["packagePresent"] for item in npm),
        "nuget_unique": len(inventory["nugetPackages"]),
        "gaps": len(inventory["gaps"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
