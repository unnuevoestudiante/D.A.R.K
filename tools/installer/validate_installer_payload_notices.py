"""Fail closed when embedded installer notices do not match its payload ZIP."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pathlib import Path
from typing import Any


NOTICE_MEMBER = "THIRD-PARTY-NOTICES.md"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest_payload(path: Path, public_key_path: Path) -> dict[str, Any]:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if envelope.get("schemaVersion") != 1 or envelope.get("algorithm") != "ECDSA_P256_SHA256":
        raise ValueError("El manifiesto no usa el contenedor/algoritmo esperado.")
    try:
        payload_bytes = base64.b64decode(envelope["payloadBase64"], validate=True)
        signature = base64.b64decode(envelope["signatureBase64"], validate=True)
    except (KeyError, ValueError) as error:
        raise ValueError("El manifiesto no contiene un payload o firma Base64 válidos.") from error
    public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
    if not isinstance(public_key, ec.EllipticCurvePublicKey) or public_key.curve.name != "secp256r1":
        raise ValueError("La clave pública del manifiesto debe ser ECDSA P-256.")
    try:
        public_key.verify(signature, payload_bytes, ec.ECDSA(hashes.SHA256()))
    except Exception as error:
        raise ValueError("La firma ECDSA del manifiesto no es válida para la clave pública indicada.") from error
    payload = json.loads(payload_bytes.decode("utf-8"))
    if payload.get("schemaVersion") != 1 or not isinstance(payload.get("artifacts"), list):
        raise ValueError("El payload del manifiesto no tiene un catálogo de artefactos válido.")
    return payload


def validate(manifest_path: Path, public_key_path: Path, archive_path: Path, notice_path: Path,
             terms_path: Path, terms_version: str) -> dict[str, Any]:
    for label, path in (("manifiesto", manifest_path), ("clave pública", public_key_path),
                        ("payload", archive_path), ("avisos", notice_path), ("condiciones", terms_path)):
        if not path.is_file():
            raise FileNotFoundError(f"No existe el archivo de {label}: {path}")
    normalized_terms_version = terms_version.strip()
    terms_bytes = terms_path.read_bytes()
    terms_text = terms_bytes.decode("utf-8-sig")
    if not normalized_terms_version or "draft" in normalized_terms_version.lower():
        raise ValueError("La versión de condiciones sigue en borrador o está vacía.")
    if "borrador" in terms_text.lower() or "[pendiente]" in terms_text.lower():
        raise ValueError("El texto de condiciones contiene marcas de borrador o campos pendientes.")

    archive_hash = sha256_file(archive_path)
    payload = read_manifest_payload(manifest_path, public_key_path)
    if payload.get("termsVersion") != normalized_terms_version:
        raise ValueError("La versión de condiciones no coincide con la versión incluida en el manifiesto firmado.")
    terms_hash = sha256_bytes(terms_bytes)
    if str(payload.get("termsSha256", "")).lower() != terms_hash:
        raise ValueError("El SHA-256 del texto de condiciones no coincide con el valor firmado en el manifiesto.")
    matching_artifacts = [
        item for item in payload["artifacts"]
        if str(item.get("sha256", "")).lower() == archive_hash
        and str(item.get("relativePath", "")).lower().endswith(".zip")
    ]
    if len(matching_artifacts) != 1:
        raise ValueError(
            "El ZIP debe coincidir con el SHA-256 de exactamente un artefacto ZIP del manifiesto firmado; "
            f"coincidencias: {len(matching_artifacts)}."
        )

    with zipfile.ZipFile(archive_path, "r") as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise zipfile.BadZipFile(f"El payload tiene una entrada ZIP dañada: {corrupt_member}")
        if archive.namelist().count(NOTICE_MEMBER) != 1:
            raise ValueError(f"El payload debe incluir una sola copia de {NOTICE_MEMBER} en su raíz.")
        try:
            packaged_notices = archive.read(NOTICE_MEMBER)
        except KeyError as error:
            raise ValueError(f"El payload no contiene {NOTICE_MEMBER} en su raíz.") from error

    source_notices = notice_path.read_bytes()
    packaged_hash = sha256_bytes(packaged_notices)
    source_hash = sha256_bytes(source_notices)
    if packaged_hash != source_hash:
        raise ValueError(
            "Los avisos que se van a embeber no corresponden byte por byte a los del payload: "
            f"payload={packaged_hash}, instalador={source_hash}."
        )

    return {
        "status": "payload-notice-pair-verified",
        "manifestArtifactId": matching_artifacts[0].get("id"),
        "payloadArchive": archive_path.name,
        "payloadSha256": archive_hash,
        "noticeMember": NOTICE_MEMBER,
        "noticeSha256": packaged_hash,
        "termsVersion": normalized_terms_version,
        "termsSha256": terms_hash,
        "manifestSignature": "verified with the supplied ECDSA P-256 release public key",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--public-key", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--notices", type=Path, required=True)
    parser.add_argument("--terms-file", type=Path, required=True)
    parser.add_argument("--terms-version", required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.manifest, args.public_key, args.payload, args.notices,
        args.terms_file, args.terms_version), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
