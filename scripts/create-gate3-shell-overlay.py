#!/usr/bin/env python3
"""Create the exact two-path private overlay accepted by the Gate 3 contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


EPOCH = 1230739200
PACKAGE_PATH = Path("app/LeoShell/LeoShell.apk")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--expected-cert-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--aapt2")
    parser.add_argument("--apksigner")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    apk = args.apk.resolve()
    output = args.output_dir.resolve()
    if not apk.is_file():
        fail(f"APK does not exist: {apk}")
    if output.exists():
        fail(f"overlay output must not already exist: {output}")

    verifier = root / "scripts/verify-gate3-shell-apk.py"
    command = [
        sys.executable, str(verifier), "--apk", str(apk),
        "--expected-cert-sha256", args.expected_cert_sha256,
    ]
    if args.aapt2:
        command.extend(("--aapt2", args.aapt2))
    if args.apksigner:
        command.extend(("--apksigner", args.apksigner))
    subprocess.run(command, check=True)

    destination = output / "tree" / PACKAGE_PATH
    destination.parent.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(apk, destination)
    os.chmod(destination.parent, 0o755)
    os.chmod(destination, 0o644)
    os.utime(destination.parent, (EPOCH, EPOCH), follow_symlinks=False)
    os.utime(destination, (EPOCH, EPOCH), follow_symlinks=False)
    manifest = {
        "schema": 1,
        "classification": "development-unverified",
        "source_apk_sha256": sha256(apk),
        "mtime_epoch": EPOCH,
        "entries": [
            {
                "path": "/app/LeoShell",
                "type": "directory",
                "uid": 0,
                "gid": 0,
                "mode_octal": "040755",
                "selinux_label": "u:object_r:system_file:s0",
            },
            {
                "path": "/app/LeoShell/LeoShell.apk",
                "type": "regular",
                "uid": 0,
                "gid": 0,
                "mode_octal": "100644",
                "selinux_label": "u:object_r:system_file:s0",
                "content_sha256": sha256(destination),
                "size_bytes": destination.stat().st_size,
            },
        ],
    }
    (output / "overlay-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    print("OK: verified Gate 3 APK copied into the exact two-path overlay")


if __name__ == "__main__":
    main()
