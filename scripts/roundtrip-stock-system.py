#!/usr/bin/env python3
"""Gate 0 sparse-container round trip; never mounts or edits system contents."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct
import tarfile


SPARSE_HEADER = struct.Struct("<IHHHHIIII")

def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--simg2img", default="simg2img")
    parser.add_argument("--img2simg", default="img2simg")
    args = parser.parse_args()

    rom = args.rom.resolve()
    work_dir = args.work_dir.resolve()
    if not rom.is_file():
        fail(f"ROM does not exist: {rom}")
    if work_dir.exists() and any(work_dir.iterdir()):
        fail(f"work directory must be empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    simg2img = shutil.which(args.simg2img)
    img2simg = shutil.which(args.img2simg)
    if not simg2img or not img2simg:
        fail("simg2img and img2simg must already be installed")

    inspect_script = Path(__file__).with_name("inspect-stock-fastboot-rom.py")
    run([str(inspect_script), "--rom", str(rom)])

    source_sparse = work_dir / "source-system.sparse.img"
    source_raw = work_dir / "source-system.raw.img"
    roundtrip_sparse = work_dir / "roundtrip-system.sparse.img"
    roundtrip_raw = work_dir / "roundtrip-system.raw.img"
    report_path = work_dir / "gate0-roundtrip.json"

    with tarfile.open(rom, "r:gz") as archive:
        matches = [
            member
            for member in archive.getmembers()
            if member.name.endswith("/images/system.img")
        ]
        if len(matches) != 1:
            fail(f"expected one system.img member, found {len(matches)}")
        source = archive.extractfile(matches[0])
        if source is None:
            fail("cannot read system.img")
        sparse_header = source.read(SPARSE_HEADER.size)
        if len(sparse_header) != SPARSE_HEADER.size:
            fail("system.img sparse header is truncated")
        sparse_fields = SPARSE_HEADER.unpack(sparse_header)
        raw_bytes = sparse_fields[5] * sparse_fields[6]
        required_free = matches[0].size + raw_bytes * 3 + 512 * 1024 * 1024
        free_bytes = shutil.disk_usage(work_dir).free
        if free_bytes < required_free:
            fail(f"insufficient free space: need {required_free}, have {free_bytes}")
        with source_sparse.open("wb") as target:
            target.write(sparse_header)
            shutil.copyfileobj(source, target, length=8 * 1024 * 1024)

    run([simg2img, str(source_sparse), str(source_raw)])
    run([img2simg, str(source_raw), str(roundtrip_sparse)])
    run([simg2img, str(roundtrip_sparse), str(roundtrip_raw)])

    source_raw_hash = sha256(source_raw)
    roundtrip_raw_hash = sha256(roundtrip_raw)
    if source_raw_hash != roundtrip_raw_hash:
        fail("raw system bytes changed across sparse container round trip")

    report = {
        "schema": 1,
        "scope": "Android sparse container only; no filesystem-level rebuild",
        "source_sparse": {
            "size_bytes": source_sparse.stat().st_size,
            "sha256": sha256(source_sparse),
        },
        "source_raw": {
            "size_bytes": source_raw.stat().st_size,
            "sha256": source_raw_hash,
        },
        "roundtrip_sparse": {
            "size_bytes": roundtrip_sparse.stat().st_size,
            "sha256": sha256(roundtrip_sparse),
        },
        "roundtrip_raw": {
            "size_bytes": roundtrip_raw.stat().st_size,
            "sha256": roundtrip_raw_hash,
        },
        "raw_bytes_equal": True,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print("OK: sparse -> raw -> sparse -> raw preserves every raw system byte")


if __name__ == "__main__":
    main()
