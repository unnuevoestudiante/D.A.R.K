"""Create a private one-off tester code and its non-secret build verifier."""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
from pathlib import Path

ITERATIONS = 600_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-dir", type=Path, default=Path(".output/release/dark-tester-private"))
    args = parser.parse_args()
    private_dir = args.private_dir.resolve()
    code_path = private_dir / "access-code.txt"
    verifier_path = private_dir / "access-code-verifier.json"
    if code_path.exists() or verifier_path.exists():
        raise FileExistsError("Ya existe un código de tester en esa carpeta; no se reemplazó para no invalidar uno compartido.")

    private_dir.mkdir(parents=True, exist_ok=True)
    code = secrets.token_urlsafe(24)
    salt = secrets.token_bytes(16)
    import hashlib
    verifier = hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, ITERATIONS, dklen=32)

    with code_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(code + "\n")
    with verifier_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({
            "schemaVersion": 1,
            "algorithm": "PBKDF2-HMAC-SHA256",
            "iterations": ITERATIONS,
            "saltBase64": base64.b64encode(salt).decode("ascii"),
            "verifierBase64": base64.b64encode(verifier).decode("ascii"),
            "expires": None,
            "bundleOnly": True,
        }, stream, indent=2)
        stream.write("\n")

    try:
        os.chmod(code_path, 0o600)
        os.chmod(verifier_path, 0o600)
    except OSError:
        pass
    print(json.dumps({
        "status": "tester-code-created",
        "secretFile": str(code_path),
        "buildVerifierFile": str(verifier_path),
        "expires": None,
        "includeSecretFileInBundle": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"No se pudo crear el código local de tester: {error}")
