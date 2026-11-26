"""Prepare a signed, offline Tester bundle from the verified local app candidate."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANDIDATE = ROOT / ".output/release/dark-app-payload-candidate-20261123-privacy-v30"
DEFAULT_BUNDLE = ROOT / ".output/release/dark-tester-bundle"
DEFAULT_PRIVATE = ROOT / ".output/release/dark-tester-private"
PAYLOAD_NAME = "dark-app-payload-candidate.zip"
NOTICE_NAME = "THIRD-PARTY-NOTICES.md"
SOURCE_HOST = "tester-bundle.dark.invalid"
TERMS_HOST = "terms.tester.dark.invalid"


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
            raise ValueError("La llave privada de prueba debe ser ECDSA P-256.")
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


def verify_candidate(candidate: Path, terms_file: Path) -> tuple[Path, Path, dict[str, object], bytes]:
    inventory_path = candidate / "candidate-inventory.json"
    payload_source = candidate / PAYLOAD_NAME
    notice_source = candidate / "app" / NOTICE_NAME
    if not inventory_path.is_file() or not payload_source.is_file() or not notice_source.is_file():
        raise FileNotFoundError("El candidato debe incluir inventory, ZIP y avisos del layout.")
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    if inventory.get("status") != "unsigned-local-candidate-not-for-release":
        raise ValueError("Solo se puede preparar un bundle Tester desde un candidato local sin firma.")
    if not isinstance(inventory.get("installedBytes"), int) or inventory["installedBytes"] <= 0:
        raise ValueError("El inventario del candidato no declara el tamaño expandido.")
    terms_bytes = terms_file.read_bytes()
    terms_text = terms_bytes.decode("utf-8-sig").lower()
    if "borrador" in terms_text or "[pendiente]" in terms_text:
        raise ValueError("El aviso de prueba contiene marcas de borrador o campos pendientes.")
    with zipfile.ZipFile(payload_source, "r") as archive:
        corrupt = archive.testzip()
        if corrupt is not None:
            raise zipfile.BadZipFile(f"El payload candidato tiene una entrada dañada: {corrupt}")
        if archive.namelist().count(NOTICE_NAME) != 1 or archive.read(NOTICE_NAME) != notice_source.read_bytes():
            raise ValueError("El aviso incluido en el payload no coincide exactamente con el del layout.")
    return inventory_path, payload_source, inventory, terms_bytes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument("--terms", type=Path, default=ROOT / "docs/installer/CONDICIONES_TESTER_PRIVADO.md")
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    bundle = args.bundle.resolve()
    private_dir = args.private_dir.resolve()
    terms_file = args.terms.resolve()
    key_path = private_dir / "manifest-test-private.pem"
    if bundle == private_dir or bundle in private_dir.parents or private_dir in bundle.parents:
        raise ValueError("La llave privada debe permanecer fuera de la carpeta que se distribuirá.")

    _, payload_source, inventory, terms_bytes = verify_candidate(candidate, terms_file)
    bundle.mkdir(parents=True, exist_ok=True)
    payload = bundle / PAYLOAD_NAME
    expected_payload_hash = sha256_file(payload_source)
    if payload.exists():
        if sha256_file(payload) != expected_payload_hash:
            raise FileExistsError("El bundle ya contiene un payload distinto; no se sobrescribió.")
    else:
        shutil.copyfile(payload_source, payload)

    private_key = get_or_create_signing_key(key_path)
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    terms_hash = hashlib.sha256(terms_bytes).hexdigest()
    payload_data = {
        "schemaVersion": 1,
        "issuedAtUtc": now.isoformat().replace("+00:00", "Z"),
        "expiresAtUtc": "9999-12-31T23:59:59Z",
        "artifacts": [{
            "id": "dark-app",
            "kind": "runtime",
            "version": "tester-v1",
            "architecture": "win-x64",
            "sourceUri": f"https://{SOURCE_HOST}/{PAYLOAD_NAME}",
            "relativePath": PAYLOAD_NAME,
            "sizeBytes": payload.stat().st_size,
            "sha256": expected_payload_hash,
            "licenseId": "DARK-TESTER-PRIVATE-v1",
            "licenseUri": f"https://{TERMS_HOST}/conditions",
            "installAction": "extractZip",
            "installTargetPath": ".",
            "estimatedInstalledBytes": inventory["installedBytes"],
            "optional": False,
            "displayName": "D.A.R.K. — Build privado Tester",
            "description": "Versión privada de evaluación. El payload se incluye en este bundle y se verifica antes de instalar.",
            "publisher": "S2",
            "allowedExitCodes": [],
            "dependsOn": [],
        }],
        "models": [],
        "termsVersion": "tester-v1",
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
    manifest_path = bundle / "release-manifest.signed.json"
    manifest_path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (bundle / "release-source-hosts.txt").write_text(SOURCE_HOST + "\n", encoding="ascii")
    public_key_path = bundle / "manifest-test-public.pem"
    public_key_path.write_bytes(public_key)

    print(json.dumps({
        "status": "tester-bundle-metadata-prepared",
        "bundle": str(bundle),
        "payloadBytes": payload.stat().st_size,
        "payloadSha256": expected_payload_hash,
        "termsVersion": payload_data["termsVersion"],
        "termsSha256": terms_hash,
        "manifest": str(manifest_path),
        "publicKey": str(public_key_path),
        "privateKeyRetainedOutsideBundle": str(key_path),
        "host": SOURCE_HOST,
        "networkAccessForPayload": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as error:
        raise SystemExit(f"No se pudo preparar el bundle Tester: {error}")
