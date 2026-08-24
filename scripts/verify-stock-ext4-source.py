#!/usr/bin/env python3
"""Classify the one locked stock ext4 source deviation without modifying it."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import uuid


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unpack(fmt: str, data: bytes, offset: int) -> int:
    return struct.unpack_from(fmt, data, offset)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--e2fsck-report", required=True, type=Path)
    parser.add_argument("--e2fsck-status", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    raw = args.raw.resolve()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    expected_raw = profile["raw_system"]
    expected_ext4 = profile["ext4"]
    deviation = profile["source_only_known_deviation"]

    if raw.stat().st_size != expected_raw["size_bytes"]:
        fail("raw size does not match locked stock profile")
    raw_hash = sha256(raw)
    if raw_hash != expected_raw["sha256"]:
        fail("raw SHA-256 does not match locked stock profile")

    with raw.open("rb") as source:
        source.seek(1024)
        superblock = source.read(1024)
    if len(superblock) != 1024 or unpack("<H", superblock, 56) != 0xEF53:
        fail("ext4 superblock magic is invalid")

    block_size = 1024 << unpack("<I", superblock, 24)
    feature_fields = [
        (
            unpack("<I", superblock, 92),
            {0x0004: "has_journal", 0x0008: "ext_attr", 0x0010: "resize_inode"},
            "compat",
        ),
        (
            unpack("<I", superblock, 96),
            {0x0002: "filetype", 0x0040: "extent"},
            "incompat",
        ),
        (
            unpack("<I", superblock, 100),
            {0x0001: "sparse_super", 0x0002: "large_file", 0x0010: "uninit_bg"},
            "ro_compat",
        ),
    ]
    features: list[str] = []
    for mask, names, namespace in feature_fields:
        known_mask = 0
        for bit, name in names.items():
            known_mask |= bit
            if mask & bit:
                features.append(name)
        if mask & ~known_mask:
            fail(f"unrecognized {namespace} feature bits: 0x{mask & ~known_mask:x}")
    geometry = {
        "block_count": unpack("<I", superblock, 4),
        "block_size": block_size,
        "features": features,
        "inode_count": unpack("<I", superblock, 0),
        "inode_size": unpack("<H", superblock, 88),
        "inodes_per_group": unpack("<I", superblock, 40),
        "label": superblock[120:136].split(b"\0", 1)[0].decode("ascii"),
        "uuid": str(uuid.UUID(bytes=superblock[104:120])),
    }
    for key, expected in expected_ext4.items():
        if geometry.get(key) != expected:
            fail(f"ext4 {key} does not match profile: {geometry.get(key)!r}")

    first_data_block = unpack("<I", superblock, 20)
    blocks_per_group = unpack("<I", superblock, 32)
    group_count = math.ceil((geometry["block_count"] - first_data_block) / blocks_per_group)
    descriptor_size = max(32, unpack("<H", superblock, 254))
    descriptor_table_offset = (2 if block_size == 1024 else 1) * block_size
    with raw.open("rb") as source:
        source.seek(descriptor_table_offset)
        descriptors = source.read(group_count * descriptor_size)
    if len(descriptors) != group_count * descriptor_size:
        fail("cannot read complete ext4 group descriptor table")
    active_groups: list[int] = []
    inode_bitmap_blocks: list[int] = []
    for group in range(group_count):
        descriptor = descriptors[group * descriptor_size : (group + 1) * descriptor_size]
        inode_bitmap_blocks.append(unpack("<I", descriptor, 4))
        if not (unpack("<H", descriptor, 18) & 0x0001):
            active_groups.append(group)
    if active_groups != [0]:
        fail(f"unexpected initialized inode groups: {active_groups}")

    status_match = re.fullmatch(
        r"e2fsck_exit=([0-9]+)\s*", args.e2fsck_status.read_text(encoding="utf-8")
    )
    if not status_match:
        fail("cannot parse e2fsck status")
    e2fsck_exit = int(status_match.group(1))
    if e2fsck_exit != deviation["e2fsck_exit"]:
        fail(f"unexpected e2fsck exit: {e2fsck_exit}")

    report_lines = [
        line
        for line in args.e2fsck_report.read_text(encoding="utf-8").splitlines()
        if line
    ]
    expected_lines = [
        "e2fsck 1.47.0 (5-Feb-2023)",
        "Pass 1: Checking inodes, blocks, and sizes",
        "Pass 2: Checking directory structure",
        "Pass 3: Checking directory connectivity",
        "Pass 4: Checking reference counts",
        "Pass 5: Checking group summary information",
        deviation["message"] + " Fix? no",
        "system: ********** WARNING: Filesystem still has errors **********",
        "system: 3932/104832 files (0.0% non-contiguous), 333913/419329 blocks",
    ]
    if report_lines != expected_lines:
        fail("e2fsck report contains an unrecognized or additional finding")

    active_bitmap_block = deviation["active_inode_bitmap_block"]
    if inode_bitmap_blocks[0] != active_bitmap_block:
        fail("profile inode bitmap block disagrees with group descriptor")
    valid_bytes = deviation["valid_bytes"]
    zero_padding_bytes = deviation["zero_padding_bytes"]
    if valid_bytes != (geometry["inodes_per_group"] + 7) // 8:
        fail("profile valid inode bitmap length disagrees with geometry")
    if valid_bytes + zero_padding_bytes != block_size:
        fail("profile inode bitmap padding length disagrees with block size")
    with raw.open("rb") as source:
        source.seek(active_bitmap_block * block_size + valid_bytes)
        padding = source.read(zero_padding_bytes)
    if len(padding) != zero_padding_bytes or any(padding):
        fail("stock inode bitmap padding does not match the ruled zero pattern")

    verdict = {
        "schema": 1,
        "classification": "accepted_source_deviation",
        "reason": deviation["classification"],
        "raw_sha256": raw_hash,
        "e2fsck_exit": e2fsck_exit,
        "filesystem_clean": False,
        "source_semantic_audit_may_continue": True,
        "gate2_output_may_reproduce": False,
        "verified_geometry": geometry,
        "verified_padding": {
            "active_groups": active_groups,
            "bitmap_block": active_bitmap_block,
            "group_count": group_count,
            "valid_bytes": valid_bytes,
            "zero_padding_bytes": zero_padding_bytes,
        },
    }
    args.output.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
