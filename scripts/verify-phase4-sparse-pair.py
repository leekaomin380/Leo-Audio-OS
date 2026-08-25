#!/usr/bin/env python3
"""Build two Android sparse system images and verify an exact raw round trip.

The output directory must be empty.  This is an offline container-format gate;
it has no device interface and never edits either raw input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path


SPARSE_HEADER = struct.Struct("<IHHHHIIII")
SPARSE_MAGIC = 0xED26FF3A
BLOCK_SIZE = 4096
PARTITION_BLOCKS = 425984
PARTITION_SIZE = BLOCK_SIZE * PARTITION_BLOCKS
CHUNK = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def geometry(path: Path) -> dict[str, int]:
    with path.open("rb") as source:
        header = source.read(SPARSE_HEADER.size)
    if len(header) != SPARSE_HEADER.size:
        raise ValueError("sparse image has a truncated header")
    magic, major, minor, file_header, chunk_header, block_size, blocks, chunks, checksum = (
        SPARSE_HEADER.unpack(header)
    )
    if magic != SPARSE_MAGIC or major != 1:
        raise ValueError("output is not Android sparse v1")
    if block_size != BLOCK_SIZE or blocks != PARTITION_BLOCKS:
        raise ValueError("sparse output does not match the pinned leo system geometry")
    return {
        "major": major,
        "minor": minor,
        "file_header_size": file_header,
        "chunk_header_size": chunk_header,
        "block_size": block_size,
        "total_blocks": blocks,
        "total_chunks": chunks,
        "image_checksum": checksum,
    }


def run(command: list[str]) -> None:
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-a", required=True, type=Path)
    parser.add_argument("--raw-b", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-raw-sha256", required=True)
    parser.add_argument("--img2simg", default="img2simg")
    parser.add_argument("--simg2img", default="simg2img")
    args = parser.parse_args()

    raw_a = args.raw_a.resolve()
    raw_b = args.raw_b.resolve()
    if not raw_a.is_file() or not raw_b.is_file():
        parser.error("both raw inputs are required")
    if raw_a.stat().st_size != PARTITION_SIZE or raw_b.stat().st_size != PARTITION_SIZE:
        parser.error("raw inputs do not match the pinned leo system partition size")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    required_free = PARTITION_SIZE + 3 * 1024 * 1024 * 1024
    free = shutil.disk_usage(output).free
    if free < required_free:
        parser.error(f"insufficient free space: need {required_free}, have {free}")

    img2simg = shutil.which(args.img2simg)
    simg2img = shutil.which(args.simg2img)
    if not img2simg or not simg2img:
        parser.error("img2simg and simg2img are required")
    img2simg_path = Path(img2simg).resolve()
    simg2img_path = Path(simg2img).resolve()

    sparse_a = output / "system-a.img"
    sparse_b = output / "system-b.img"
    roundtrip = output / "system-a.roundtrip.raw"
    try:
        hash_a = sha256(raw_a)
        hash_b = sha256(raw_b)
        expected = args.expected_raw_sha256.lower()
        if hash_a != expected or hash_b != expected:
            raise ValueError("raw pair does not match the expected verified-system hash")
        run([str(img2simg_path), str(raw_a), str(sparse_a)])
        run([str(img2simg_path), str(raw_b), str(sparse_b)])
        sparse_hash_a = sha256(sparse_a)
        sparse_hash_b = sha256(sparse_b)
        sparse_cmp = subprocess.run(
            ["/usr/bin/cmp", "-s", str(sparse_a), str(sparse_b)], check=False
        )
        if sparse_hash_a != sparse_hash_b or sparse_cmp.returncode != 0:
            raise ValueError("two sparse builds are not byte-for-byte reproducible")
        sparse_geometry = geometry(sparse_a)
        run([str(simg2img_path), str(sparse_a), str(roundtrip)])
        roundtrip_hash = sha256(roundtrip)
        if roundtrip.stat().st_size != PARTITION_SIZE or roundtrip_hash != expected:
            raise ValueError("sparse to raw round trip changed the verified system bytes")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    report = {
        "schema": 1,
        "classification": "phase4-development-pair-sparse-roundtrip",
        "device_interface_available": False,
        "raw": {"size": PARTITION_SIZE, "sha256": expected, "pair_identical": True},
        "sparse": {
            "size": sparse_a.stat().st_size,
            "sha256": sparse_hash_a,
            "pair_identical": True,
            "geometry": sparse_geometry,
        },
        "roundtrip": {
            "size": roundtrip.stat().st_size,
            "sha256": roundtrip_hash,
            "matches_raw": True,
        },
        "tools": {
            "img2simg": {"path": str(img2simg_path), "sha256": sha256(img2simg_path)},
            "simg2img": {"path": str(simg2img_path), "sha256": sha256(simg2img_path)},
        },
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
