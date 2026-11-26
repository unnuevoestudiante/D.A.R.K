"""Prepare a public GitHub Release (single-file DarkInstaller.exe + payload ZIP) from a verified candidate."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / ".output/release/dark-app-payload-candidate-20261123-privacy-v30"
DEFAULT_OUTPUT = ROOT / ".output/release/dark-public-release"
DEFAULT_PRIVATE = ROOT / ".output/release/dark-public-private"
DEFAULT_TERMS = ROOT / "docs/installer/CONDICIONES_PUBLIC_PREVIEW.md"
PAYLOAD_NAME = "dark-app-payload-candidate.zip"
NOTICE_NAME = "THIRD-PARTY-NOTICES.md"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def get_or_create_signing_key(path: Path) -> ec.EllipticCurvePrivateKey:
    if path.exists():
        key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError("La llave privada debe ser ECDSA P-256.")
        return key
    path.parent.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def verify_candidate(candidate: Path, terms_file: Path) -> tuple[Path, dict[str, object], bytes]:
    inventory_path = candidate / "candidate-inventory.json"
    payload_source = candidate / PAYLOAD_NAME
    notice_source = candidate / "app" / NOTICE_NAME
    if not inventory_path.is_file() or not payload_source.is_file() or not notice_source.is_file():
        raise FileNotFoundError("El candidato debe incluir candidate-inventory.json, ZIP y THIRD-PARTY-NOTICES.md.")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if not isinstance(inventory.get("installedBytes"), int) or inventory["installedBytes"] <= 0:
        raise ValueError("El inventario del candidato no declara el tamaño expandido.")
    terms_bytes = terms_file.read_bytes()
    terms_text = terms_bytes.decode("utf-8-sig").lower()
    if "borrador" in terms_text or "[pendiente]" in terms_text:
        raise ValueError("El texto de condiciones contiene marcas de borrador o campos pendientes.")
    with zipfile.ZipFile(payload_source, "r") as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise zipfile.BadZipFile(f"El payload candidato tiene una entrada dañada: {corrupt}")
        if archive.namelist().count(NOTICE_NAME) != 1 or archive.read(NOTICE_NAME) != notice_source.read_bytes():
            raise ValueError("El aviso incluido en el payload no coincide exactamente con el del layout.")
    return payload_source, inventory, terms_bytes


def derive_allowed_hosts(payload_url: str, license_url: str, extra_hosts: list[str]) -> list[str]:
    hosts: list[str] = []
    for raw in (payload_url, license_url):
        parsed = urlparse(raw)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError(f"La URL debe usar HTTPS válido: {raw}")
        if parsed.hostname not in hosts:
            hosts.append(parsed.hostname)
    if "github.com" in hosts:
        for gh_cdn in ("objects.githubusercontent.com", "release-assets.githubusercontent.com"):
            if gh_cdn not in hosts:
                hosts.append(gh_cdn)
    for host in extra_hosts:
        cleaned = host.strip()
        if cleaned and cleaned not in hosts:
            hosts.append(cleaned)
    return hosts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-url", required=True, help="URL HTTPS pública del ZIP en GitHub Releases.")
    parser.add_argument("--license-url", help="URL HTTPS de referencia de licencia/repositorio. Por defecto usa el repo de --payload-url.")
    parser.add_argument("--version", default="0.1.0-preview", help="Versión del artefacto en el manifiesto.")
    parser.add_argument("--terms-version", default="public-preview-v1", help="Versión de las condiciones (sin 'draft').")
    parser.add_argument("--terms", type=Path, default=DEFAULT_TERMS)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--extra-host", action="append", default=[], help="Host HTTPS adicional permitido en redirecciones.")
    parser.add_argument("--skip-publish", action="store_true", help="Solo genera manifiesto y metadatos sin ejecutar dotnet publish.")
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    output = args.output.resolve()
    private_dir = args.private_dir.resolve()
    terms_file = args.terms.resolve()
    if output == private_dir or output in private_dir.parents or private_dir in output.parents:
        raise ValueError("La llave privada debe permanecer fuera de la carpeta de salida.")

    parsed_payload = urlparse(args.payload_url)
    asset_name = Path(parsed_payload.path).name or "dark-app-payload.zip"
    if not asset_name.lower().endswith(".zip"):
        raise ValueError("La URL --payload-url debe terminar en un archivo .zip.")
    license_url = args.license_url or f"https://{parsed_payload.hostname}{'/'.join(parsed_payload.path.split('/')[:3])}"

    payload_source, inventory, terms_bytes = verify_candidate(candidate, terms_file)
    output.mkdir(parents=True, exist_ok=True)
    metadata_dir = output / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    payload_out = output / asset_name
    expected_payload_hash = sha256_file(payload_source)
    if not payload_out.exists() or sha256_file(payload_out) != expected_payload_hash:
        shutil.copyfile(payload_source, payload_out)

    key_path = private_dir / "manifest-release-private.pem"
    private_key = get_or_create_signing_key(key_path)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    public_key_path = metadata_dir / "release-manifest-public.pem"
    public_key_path.write_bytes(public_key)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    terms_hash = hashlib.sha256(terms_bytes).hexdigest()
    payload_data = {
        "schemaVersion": 1,
        "issuedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": "9999-12-31T23:59:59Z",
        "artifacts": [{
            "id": "dark-app",
            "kind": "runtime",
            "version": args.version,
            "architecture": "win-x64",
            "sourceUri": args.payload_url,
            "relativePath": asset_name,
            "sizeBytes": payload_out.stat().st_size,
            "sha256": expected_payload_hash,
            "licenseId": "DARK-PUBLIC-PREVIEW-v1",
            "licenseUri": license_url,
            "installAction": "extractZip",
            "installTargetPath": ".",
            "estimatedInstalledBytes": inventory["installedBytes"],
            "optional": False,
            "displayName": "D.A.R.K. — Aplicación principal",
            "description": "Primera versión pública de D.A.R.K. para Windows x64.",
            "publisher": "S2",
            "allowedExitCodes": [],
            "dependsOn": [],
        }],
        "models": [],
        "termsVersion": args.terms_version,
        "termsSha256": terms_hash,
    }
    payload_bytes = json.dumps(payload_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    signature = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA256()))
    envelope = {
        "schemaVersion": 1,
        "algorithm": "ECDSA_P256_SHA256",
        "payloadBase64": base64.b64encode(payload_bytes).decode("ascii"),
        "signatureBase64": base64.b64encode(signature).decode("ascii"),
    }
    manifest_path = metadata_dir / "release-manifest.signed.json"
    manifest_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    allowed_hosts = derive_allowed_hosts(args.payload_url, license_url, args.extra_host)
    hosts_path = metadata_dir / "release-source-hosts.txt"
    hosts_path.write_text("\n".join(allowed_hosts) + "\n", encoding="ascii")

    notices_path = candidate / "app" / NOTICE_NAME
    if not args.skip_publish:
        publish_dir = output / "publish"
        cmd = [
            "dotnet", "publish", str(ROOT / "DarkInstaller/DarkInstaller.csproj"),
            "-c", "Release",
            "-o", str(publish_dir),
            f"-p:InstallerManifestFile={manifest_path}",
            f"-p:InstallerManifestPublicKeyFile={public_key_path}",
            f"-p:InstallerSourceHostsFile={hosts_path}",
            f"-p:InstallerThirdPartyNotices={notices_path}",
            f"-p:InstallerTermsFile={terms_file}",
            f"-p:InstallerTermsVersion={args.terms_version}",
            f"-p:InstallerPayloadArchive={payload_out}",
            f"-p:InstallerPythonCommand={sys.executable}",
        ]
        subprocess.run(cmd, check=True, cwd=str(ROOT))
        shutil.copyfile(publish_dir / "DarkInstaller.exe", output / "DarkInstaller.exe")

    print(json.dumps({
        "status": "public-release-ready",
        "outputDir": str(output),
        "installerExe": str(output / "DarkInstaller.exe") if not args.skip_publish else None,
        "payloadAssetToUpload": str(payload_out),
        "payloadUrl": args.payload_url,
        "payloadSha256": expected_payload_hash,
        "allowedHosts": allowed_hosts,
        "privateKeyPath": str(key_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        raise SystemExit(f"No se pudo preparar el release público: {error}")
