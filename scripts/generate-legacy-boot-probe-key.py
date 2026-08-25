#!/usr/bin/env python3
"""Generate a disposable RSA-2048 BootSignature v1 probe identity.

The generated private key is deliberately unencrypted and therefore may only
be used for ignored, offline development probes.  This tool cannot create or
label release material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-id", default="leo-boot-development-probe-v1")
    parser.add_argument("--development-probe", action="store_true", required=True)
    args = parser.parse_args()

    openssl = shutil.which("openssl")
    if not openssl:
        parser.error("openssl is required")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    os.chmod(output, 0o700)

    private_pem = output / "boot-private.pem"
    private_pk8 = output / "boot.pk8"
    certificate_pem = output / "boot-certificate.pem"
    certificate_der = output / "boot-certificate.der"
    public_pem = output / "boot-public.pem"

    try:
        run([
            openssl, "genpkey", "-algorithm", "RSA",
            "-pkeyopt", "rsa_keygen_bits:2048",
            "-pkeyopt", "rsa_keygen_pubexp:65537",
            "-out", str(private_pem),
        ])
        run([
            openssl, "pkcs8", "-topk8", "-nocrypt", "-in", str(private_pem),
            "-outform", "DER", "-out", str(private_pk8),
        ])
        run([
            openssl, "req", "-new", "-x509", "-sha256", "-key", str(private_pem),
            "-subj", "/CN=Leo Audio OS Development Boot Probe/",
            "-days", "3650", "-set_serial", "0x4c454f01",
            "-out", str(certificate_pem),
        ])
        run([
            openssl, "x509", "-in", str(certificate_pem), "-outform", "DER",
            "-out", str(certificate_der),
        ])
        run([
            openssl, "pkey", "-in", str(private_pem), "-pubout", "-out", str(public_pem),
        ])
        for private_file in (private_pem, private_pk8):
            os.chmod(private_file, 0o600)
    except (OSError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    manifest = {
        "schema": 1,
        "classification": "development_probe_only_not_for_device_release",
        "key_id": args.key_id,
        "algorithm": "RSA-2048",
        "boot_signature": "Android BootSignature v1 SHA256withRSA target /boot",
        "private_key_encrypted": False,
        "release_use_allowed": False,
        "certificate_serial": "0x4c454f01",
        "files": {
            "private_pem": {"name": private_pem.name, "sha256": sha256(private_pem)},
            "private_pkcs8_der": {"name": private_pk8.name, "sha256": sha256(private_pk8)},
            "certificate_pem": {
                "name": certificate_pem.name,
                "sha256": sha256(certificate_pem),
            },
            "certificate_der": {
                "name": certificate_der.name,
                "sha256": sha256(certificate_der),
            },
            "public_pem": {"name": public_pem.name, "sha256": sha256(public_pem)},
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
