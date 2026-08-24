#!/usr/bin/env python3
"""Safely unpack a legacy Android boot image and concatenated kernel DTBs.

The tool is intentionally read-only with respect to the input. It supports the
legacy boot header used by leo's Android 7 stock image and refuses malformed
section boundaries instead of guessing.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path


BOOT_MAGIC = b"ANDROID!"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"
HEADER_SIZE = 1632


def align(value: int, page_size: int) -> int:
    return (value + page_size - 1) // page_size * page_size


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def c_string(data: bytes) -> str:
    return data.split(b"\0", 1)[0].decode("utf-8", errors="replace")


def decode_os_version(encoded: int) -> dict[str, str | int]:
    version = encoded >> 11
    patch = encoded & 0x7FF
    major = (version >> 14) & 0x7F
    minor = (version >> 7) & 0x7F
    patch_level = version & 0x7F
    year = (patch >> 4) + 2000 if patch else 0
    month = patch & 0x0F
    return {
        "encoded": encoded,
        "version": f"{major}.{minor}.{patch_level}",
        "patch_level": f"{year:04d}-{month:02d}" if patch else "unset",
    }


def find_concatenated_dtbs(kernel: bytes) -> tuple[int, list[tuple[int, int]]]:
    """Return a validated DTB chain that ends exactly at the kernel section."""
    candidates: list[tuple[int, list[tuple[int, int]]]] = []
    cursor = 0
    while True:
        start = kernel.find(FDT_MAGIC, cursor)
        if start < 0:
            break
        chain: list[tuple[int, int]] = []
        offset = start
        while offset + 8 <= len(kernel) and kernel[offset:offset + 4] == FDT_MAGIC:
            size = struct.unpack_from(">I", kernel, offset + 4)[0]
            if size < 40 or offset + size > len(kernel):
                chain = []
                break
            chain.append((offset, size))
            offset += size
        if chain and offset == len(kernel):
            candidates.append((start, chain))
        cursor = start + 1

    if not candidates:
        return len(kernel), []
    # Prefer the longest chain; the offset tie-break keeps output deterministic.
    return max(candidates, key=lambda item: (len(item[1]), -item[0]))


def ensure_output_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if any(path.iterdir()):
        raise ValueError(f"output directory is not empty: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    boot_path = args.boot.resolve()
    if not boot_path.is_file():
        parser.error(f"boot image does not exist: {boot_path}")

    image = boot_path.read_bytes()
    if len(image) < HEADER_SIZE or image[:8] != BOOT_MAGIC:
        parser.error("input is not a supported legacy Android boot image")

    fields = struct.unpack_from("<10I", image, 8)
    keys = (
        "kernel_size", "kernel_addr", "ramdisk_size", "ramdisk_addr",
        "second_size", "second_addr", "tags_addr", "page_size",
        "dt_size", "os_version_encoded",
    )
    header = dict(zip(keys, fields))
    page_size = header["page_size"]
    if page_size < 512 or page_size & (page_size - 1):
        parser.error(f"invalid page size: {page_size}")

    kernel_offset = page_size
    ramdisk_offset = align(kernel_offset + header["kernel_size"], page_size)
    second_offset = align(ramdisk_offset + header["ramdisk_size"], page_size)
    dt_offset = align(second_offset + header["second_size"], page_size)
    final_end = dt_offset + header["dt_size"]
    if final_end > len(image):
        parser.error("declared boot sections exceed input size")

    kernel = image[kernel_offset:kernel_offset + header["kernel_size"]]
    ramdisk = image[ramdisk_offset:ramdisk_offset + header["ramdisk_size"]]
    second = image[second_offset:second_offset + header["second_size"]]
    header_dt = image[dt_offset:dt_offset + header["dt_size"]]
    kernel_payload_end, dtbs = find_concatenated_dtbs(kernel)
    kernel_payload = kernel[:kernel_payload_end]

    output = args.output.resolve()
    try:
        ensure_output_directory(output)
    except ValueError as error:
        parser.error(str(error))

    (output / "kernel-section.bin").write_bytes(kernel)
    (output / "kernel-payload.bin").write_bytes(kernel_payload)
    (output / "ramdisk.bin").write_bytes(ramdisk)
    if second:
        (output / "second.bin").write_bytes(second)
    if header_dt:
        (output / "header-dt.bin").write_bytes(header_dt)

    kernel_format = "unknown"
    kernel_image: bytes | None = None
    if kernel_payload.startswith(b"\x1f\x8b\x08"):
        kernel_format = "gzip"
        kernel_image = gzip.decompress(kernel_payload)
        (output / "kernel-image.bin").write_bytes(kernel_image)

    ramdisk_format = "unknown"
    if ramdisk.startswith(b"\x1f\x8b\x08"):
        ramdisk_format = "gzip-cpio"
        (output / "ramdisk.cpio").write_bytes(gzip.decompress(ramdisk))

    dtb_dir = output / "dtbs"
    if dtbs:
        dtb_dir.mkdir()
    dtb_metadata: list[dict[str, int | str]] = []
    for index, (offset, size) in enumerate(dtbs):
        blob = kernel[offset:offset + size]
        filename = f"{index:02d}.dtb"
        (dtb_dir / filename).write_bytes(blob)
        dtb_metadata.append({
            "index": index,
            "filename": filename,
            "kernel_offset": offset,
            "size": size,
            "sha256": sha256(blob),
        })

    metadata = {
        "input": str(boot_path),
        "input_size": len(image),
        "input_sha256": sha256(image),
        "header_kind": "legacy-v0-compatible",
        "name": c_string(image[48:64]),
        "cmdline": c_string(image[64:576]) + c_string(image[608:1632]),
        "os_version": decode_os_version(header["os_version_encoded"]),
        "header": header,
        "offsets": {
            "kernel": kernel_offset,
            "ramdisk": ramdisk_offset,
            "second": second_offset,
            "header_dt": dt_offset,
        },
        "sections": {
            "kernel_sha256": sha256(kernel),
            "kernel_payload_size": len(kernel_payload),
            "kernel_payload_sha256": sha256(kernel_payload),
            "kernel_payload_format": kernel_format,
            "kernel_image_size": len(kernel_image) if kernel_image else None,
            "kernel_image_sha256": sha256(kernel_image) if kernel_image else None,
            "ramdisk_format": ramdisk_format,
            "ramdisk_sha256": sha256(ramdisk),
            "second_sha256": sha256(second) if second else None,
            "header_dt_sha256": sha256(header_dt) if header_dt else None,
        },
        "appended_dtb_count": len(dtbs),
        "appended_dtbs": dtb_metadata,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"boot_sha256={metadata['input_sha256']}")
    print(f"kernel_payload_size={len(kernel_payload)}")
    print(f"kernel_payload_format={kernel_format}")
    print(f"appended_dtb_count={len(dtbs)}")
    print(f"ramdisk_format={ramdisk_format}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
