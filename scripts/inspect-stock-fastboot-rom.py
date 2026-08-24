#!/usr/bin/env python3
"""Read-only Gate 0 audit for the exact stock leo fastboot ROM."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import tarfile
import xml.etree.ElementTree as ET


SPARSE_MAGIC = 0xED26FF3A
SPARSE_HEADER = struct.Struct("<IHHHHIIII")
REQUIRED_SUFFIXES = (
    "/images/system.img",
    "/images/boot.img",
    "/images/recovery.img",
    "/images/rawprogram0.xml",
    "/flash_all.sh",
    "/flash_all_except_data_storage.sh",
)


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def locked_rom(lock_path: Path) -> tuple[str, str]:
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split("|")
        if len(fields) >= 3 and fields[0] == "stock-fastboot-rom":
            return fields[1], fields[2]
    fail("stock-fastboot-rom is missing from the private input lock")


def safe_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts:
        fail(f"unsafe tar member path: {name}")


def unique_suffix(members: dict[str, tarfile.TarInfo], suffix: str) -> tarfile.TarInfo:
    matches = [member for name, member in members.items() if name.endswith(suffix)]
    if len(matches) != 1:
        fail(f"expected exactly one {suffix}, found {len(matches)}")
    return matches[0]


def inspect(rom_path: Path, lock_path: Path) -> dict[str, object]:
    if not rom_path.is_file():
        fail(f"ROM does not exist: {rom_path}")
    if not lock_path.is_file():
        fail(f"lock file does not exist: {lock_path}")

    expected_name, expected_hash = locked_rom(lock_path)
    if rom_path.name != expected_name:
        fail(f"ROM filename mismatch: expected {expected_name}, got {rom_path.name}")
    actual_hash = sha256(rom_path)
    if actual_hash != expected_hash:
        fail(f"ROM SHA-256 mismatch: expected {expected_hash}, got {actual_hash}")

    with tarfile.open(rom_path, "r:gz") as archive:
        tar_members = archive.getmembers()
        for member in tar_members:
            safe_member_name(member.name)
        members = {member.name: member for member in tar_members}
        required = {suffix: unique_suffix(members, suffix) for suffix in REQUIRED_SUFFIXES}

        system_member = required["/images/system.img"]
        system_stream = archive.extractfile(system_member)
        if system_stream is None:
            fail("cannot read system.img")
        header_bytes = system_stream.read(SPARSE_HEADER.size)
        if len(header_bytes) != SPARSE_HEADER.size:
            fail("system.img sparse header is truncated")
        (
            magic,
            major,
            minor,
            file_header_size,
            chunk_header_size,
            block_size,
            total_blocks,
            total_chunks,
            image_checksum,
        ) = SPARSE_HEADER.unpack(header_bytes)
        if magic != SPARSE_MAGIC:
            fail(f"system.img is not Android sparse: magic=0x{magic:08x}")
        if major != 1 or file_header_size < SPARSE_HEADER.size or chunk_header_size < 12:
            fail("unsupported Android sparse header")

        rawprogram_member = required["/images/rawprogram0.xml"]
        rawprogram_stream = archive.extractfile(rawprogram_member)
        if rawprogram_stream is None:
            fail("cannot read rawprogram0.xml")
        rawprogram = ET.fromstring(rawprogram_stream.read())
        programs = {
            node.attrib.get("label", ""): node.attrib
            for node in rawprogram.findall("program")
        }
        for label in ("system", "boot", "recovery", "persist"):
            if label not in programs:
                fail(f"rawprogram0.xml is missing partition {label}")

    expanded_bytes = block_size * total_blocks
    system_partition_bytes = int(programs["system"]["num_partition_sectors"]) * int(
        programs["system"]["SECTOR_SIZE_IN_BYTES"]
    )
    if expanded_bytes != system_partition_bytes:
        fail(
            "sparse expanded size does not match system partition: "
            f"{expanded_bytes} != {system_partition_bytes}"
        )
    if programs["system"].get("filename") != "system.img":
        fail("system partition does not point to system.img")
    if programs["persist"].get("filename"):
        fail("stock rawprogram unexpectedly assigns an image to persist")

    return {
        "schema": 1,
        "rom": {
            "filename": rom_path.name,
            "size_bytes": rom_path.stat().st_size,
            "sha256": actual_hash,
        },
        "system_sparse": {
            "member_size_bytes": system_member.size,
            "major": major,
            "minor": minor,
            "file_header_size": file_header_size,
            "chunk_header_size": chunk_header_size,
            "block_size": block_size,
            "total_blocks": total_blocks,
            "total_chunks": total_chunks,
            "expanded_bytes": expanded_bytes,
            "image_checksum": image_checksum,
        },
        "partitions": {
            label: {
                "size_kib": int(float(programs[label]["size_in_KB"])),
                "filename": programs[label].get("filename", ""),
                "start_sector": int(programs[label]["start_sector"]),
                "num_partition_sectors": int(programs[label]["num_partition_sectors"]),
            }
            for label in ("system", "boot", "recovery", "persist")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", required=True, type=Path)
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "resources/private-inputs.lock",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = inspect(args.rom.resolve(), args.lock.resolve())
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    print("OK: stock ROM identity, sparse header, partition size, and persist boundary match")


if __name__ == "__main__":
    main()
