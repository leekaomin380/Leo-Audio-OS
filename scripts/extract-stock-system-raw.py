#!/usr/bin/env python3
"""Extract a verified stock sparse system image to a private raw ext4 work file."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile


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
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--simg2img", default="simg2img")
    args = parser.parse_args()

    rom = args.rom.resolve()
    work_dir = args.work_dir.resolve()
    if not rom.is_file():
        fail(f"ROM does not exist: {rom}")
    if work_dir.exists() and any(work_dir.iterdir()):
        fail(f"work directory must be empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    simg2img = shutil.which(args.simg2img)
    if not simg2img:
        fail("simg2img must already be installed")
    inspect_script = Path(__file__).with_name("inspect-stock-fastboot-rom.py")
    subprocess.run([sys.executable, str(inspect_script), "--rom", str(rom)], check=True)

    sparse_path = work_dir / "source-system.sparse.img"
    raw_path = work_dir / "system.raw.img"
    report_path = work_dir / "input-extraction.json"
    with tarfile.open(rom, "r:gz") as archive:
        matches = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/images/system.img")
        ]
        if len(matches) != 1:
            fail(f"expected one system.img member, found {len(matches)}")
        required_free = matches[0].size + 1744830464 + 512 * 1024 * 1024
        free_bytes = shutil.disk_usage(work_dir).free
        if free_bytes < required_free:
            fail(f"insufficient free space: need {required_free}, have {free_bytes}")
        source = archive.extractfile(matches[0])
        if source is None:
            fail("cannot read system.img")
        digest = hashlib.sha256()
        with sparse_path.open("wb") as target:
            while True:
                block = source.read(8 * 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                target.write(block)

    subprocess.run([simg2img, str(sparse_path), str(raw_path)], check=True)
    report = {
        "schema": 1,
        "scope": "verified stock input extraction; no mount or filesystem modification",
        "source_sparse": {
            "size_bytes": sparse_path.stat().st_size,
            "sha256": digest.hexdigest(),
        },
        "raw_system": {
            "size_bytes": raw_path.stat().st_size,
            "sha256": sha256(raw_path),
        },
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    sparse_path.unlink()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print("OK: verified sparse system extracted to raw ext4; sparse temporary removed")


if __name__ == "__main__":
    main()
