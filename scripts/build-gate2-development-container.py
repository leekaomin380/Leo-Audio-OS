#!/usr/bin/env python3
"""Build and verify Gate 2's development-only Android sparse container.

This never contacts a device.  It deliberately does not reuse the stock
dm-verity/FEC tail: the ext4 candidate occupies the start of the exact stock
system partition and the remaining blocks are logically zero-filled.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess


BLOCK_SIZE = 4096
PARTITION_BLOCKS = 425984
EXT4_BLOCKS = 419329
PARTITION_BYTES = BLOCK_SIZE * PARTITION_BLOCKS
EXT4_BYTES = BLOCK_SIZE * EXT4_BLOCKS
TAIL_BLOCKS = PARTITION_BLOCKS - EXT4_BLOCKS
TAIL_BYTES = BLOCK_SIZE * TAIL_BLOCKS
SPARSE_HEADER = struct.Struct("<IHHHHIIII")
SPARSE_MAGIC = 0xED26FF3A
CHUNK_BYTES = 8 * 1024 * 1024


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path, *, offset: int = 0, size: int | None = None) -> str:
    digest = hashlib.sha256()
    remaining = size
    with path.open("rb") as source:
        source.seek(offset)
        while remaining is None or remaining:
            block = source.read(CHUNK_BYTES if remaining is None else min(CHUNK_BYTES, remaining))
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    if remaining not in (None, 0):
        fail(f"short read while hashing {path}")
    return digest.hexdigest()


def zero_sha256(size: int) -> str:
    digest = hashlib.sha256()
    block = b"\0" * min(CHUNK_BYTES, size)
    remaining = size
    while remaining:
        current = min(len(block), remaining)
        digest.update(block[:current])
        remaining -= current
    return digest.hexdigest()


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def sparse_geometry(path: Path) -> dict[str, int]:
    with path.open("rb") as source:
        header = source.read(SPARSE_HEADER.size)
    if len(header) != SPARSE_HEADER.size:
        fail("sparse output header is truncated")
    magic, major, minor, file_header, chunk_header, block_size, total_blocks, total_chunks, checksum = SPARSE_HEADER.unpack(header)
    if magic != SPARSE_MAGIC or major != 1:
        fail("output is not Android sparse v1")
    if block_size != BLOCK_SIZE or total_blocks != PARTITION_BLOCKS:
        fail(f"sparse geometry mismatch: block_size={block_size}, blocks={total_blocks}")
    return {
        "major": major,
        "minor": minor,
        "file_header_size": file_header,
        "chunk_header_size": chunk_header,
        "block_size": block_size,
        "total_blocks": total_blocks,
        "total_chunks": total_chunks,
        "image_checksum": checksum,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ext4-raw", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--img2simg", default="img2simg")
    parser.add_argument("--simg2img", default="simg2img")
    args = parser.parse_args()

    ext4_raw = args.ext4_raw.resolve()
    work_dir = args.work_dir.resolve()
    if not ext4_raw.is_file():
        fail(f"ext4 raw input does not exist: {ext4_raw}")
    if ext4_raw.stat().st_size != EXT4_BYTES:
        fail(f"ext4 raw size must be {EXT4_BYTES}, got {ext4_raw.stat().st_size}")
    if work_dir.exists() and any(work_dir.iterdir()):
        fail(f"work directory must be empty: {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)

    img2simg = shutil.which(args.img2simg)
    simg2img = shutil.which(args.simg2img)
    if not img2simg or not simg2img:
        fail("img2simg and simg2img must already be installed")
    required_free = PARTITION_BYTES * 3 + 512 * 1024 * 1024
    free_bytes = shutil.disk_usage(work_dir).free
    if free_bytes < required_free:
        fail(f"insufficient free space: need {required_free}, have {free_bytes}")

    partition_raw = work_dir / "system.partition.raw"
    sparse_image = work_dir / "system.img"
    roundtrip_raw = work_dir / "system.partition.roundtrip.raw"
    report_path = work_dir / "gate2-development-container.json"

    # Materialize all blocks, then overwrite the ext4 prefix.  This is a
    # development partition image only: stock verity/FEC blocks are never read.
    with partition_raw.open("wb") as target:
        zero_block = b"\0" * CHUNK_BYTES
        remaining = PARTITION_BYTES
        while remaining:
            chunk = min(len(zero_block), remaining)
            target.write(zero_block[:chunk])
            remaining -= chunk
    with ext4_raw.open("rb") as source, partition_raw.open("r+b") as target:
        shutil.copyfileobj(source, target, length=CHUNK_BYTES)

    ext4_hash = sha256(ext4_raw)
    prefix_hash = sha256(partition_raw, size=EXT4_BYTES)
    expected_tail_hash = zero_sha256(TAIL_BYTES)
    tail_hash = sha256(partition_raw, offset=EXT4_BYTES, size=TAIL_BYTES)
    if partition_raw.stat().st_size != PARTITION_BYTES:
        fail("partition raw size differs from the locked stock geometry")
    if prefix_hash != ext4_hash:
        fail("partition raw ext4 prefix differs from the verified candidate")
    if tail_hash != expected_tail_hash:
        fail("development partition tail is not zero-filled")

    run([img2simg, str(partition_raw), str(sparse_image)])
    geometry = sparse_geometry(sparse_image)
    run([simg2img, str(sparse_image), str(roundtrip_raw)])
    if roundtrip_raw.stat().st_size != PARTITION_BYTES:
        fail("expanded sparse image differs from the locked stock geometry")

    partition_hash = sha256(partition_raw)
    roundtrip_hash = sha256(roundtrip_raw)
    if roundtrip_hash != partition_hash:
        fail("sparse -> raw round trip changed development partition bytes")
    if sha256(roundtrip_raw, size=EXT4_BYTES) != ext4_hash:
        fail("expanded sparse prefix differs from the verified ext4 candidate")
    if sha256(roundtrip_raw, offset=EXT4_BYTES, size=TAIL_BYTES) != expected_tail_hash:
        fail("expanded sparse tail is not zero-filled")

    report = {
        "schema": 1,
        "scope": "development-unverified container only; no device operation; stock verity/FEC tail is not reused",
        "geometry": {
            "block_size": BLOCK_SIZE,
            "partition_blocks": PARTITION_BLOCKS,
            "partition_bytes": PARTITION_BYTES,
            "ext4_blocks": EXT4_BLOCKS,
            "ext4_bytes": EXT4_BYTES,
            "zero_tail_blocks": TAIL_BLOCKS,
            "zero_tail_bytes": TAIL_BYTES,
        },
        "input_ext4_raw": {"path": str(ext4_raw), "sha256": ext4_hash},
        "partition_raw": {"path": str(partition_raw), "sha256": partition_hash},
        "sparse_image": {
            "path": str(sparse_image),
            "size_bytes": sparse_image.stat().st_size,
            "sha256": sha256(sparse_image),
            "header": geometry,
        },
        "roundtrip_raw": {"path": str(roundtrip_raw), "sha256": roundtrip_hash},
        "prefix_matches_ext4": True,
        "tail_is_zero_filled": True,
        "raw_bytes_equal_after_sparse_roundtrip": True,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print("OK: development partition is zero-tailed and sparse round trip preserves every byte")


if __name__ == "__main__":
    main()
