#!/usr/bin/env python3
"""Build a legacy Android 7 dm-verity/FEC system partition offline.

The script has no device interface.  It binds one ext4 input read-only into the
pinned builder, signs the exact verity table, appends FEC, and runs the separate
read-only verifier before accepting the output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import struct
import subprocess
import sys
from pathlib import Path


BLOCK_SIZE = 4096
EXT4_BLOCKS = 419329
EXT4_SIZE = EXT4_BLOCKS * BLOCK_SIZE
PARTITION_BLOCKS = 425984
PARTITION_SIZE = PARTITION_BLOCKS * BLOCK_SIZE
METADATA_SIZE = 8 * BLOCK_SIZE
VERITY_MAGIC = 0xB001B001
VERITY_VERSION = 0
DEFAULT_SALT = "aee087a5be3b982978c923f566a94613496b417f2af592639bc80d141e34dfe7"
BLOCK_DEVICE = "/dev/block/bootdevice/by-name/system"
DEFAULT_BUILDER = "sha256:1dcbf603cec7f3546fb3edc3712142f1bb498cdc950404f76fa9edcdfdbdf935"


def sha256_file(filename: Path) -> str:
    digest = hashlib.sha256()
    with filename.open("rb") as file_handle:
        while chunk := file_handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def clone_or_copy(source: Path, destination: Path) -> str:
    if platform.system() == "Darwin":
        command = ["/bin/cp", "-c", str(source), str(destination)]
    else:
        command = ["cp", "--reflink=auto", str(source), str(destination)]
    completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if completed.returncode == 0:
        return "copy_on_write_clone_or_reflink"
    shutil.copyfile(source, destination)
    return "stream_copy_fallback"


def append_file(destination_handle, source: Path) -> None:
    with source.open("rb") as source_handle:
        while chunk := source_handle.read(4 * 1024 * 1024):
            destination_handle.write(chunk)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ext4", required=True, type=Path)
    parser.add_argument("--private-key", required=True, type=Path)
    parser.add_argument("--verity-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--builder-image", default=DEFAULT_BUILDER)
    parser.add_argument("--salt", default=DEFAULT_SALT)
    parser.add_argument("--expected-ext4-sha256")
    parser.add_argument("--development-probe", action="store_true", required=True)
    args = parser.parse_args()

    docker = shutil.which("docker")
    openssl = shutil.which("openssl")
    if not docker or not openssl:
        parser.error("docker and openssl are required")
    ext4 = args.ext4.resolve()
    private_key = args.private_key.resolve()
    verity_key = args.verity_key.resolve()
    if not ext4.is_file() or not private_key.is_file() or not verity_key.is_file():
        parser.error("ext4, private key, or verity key input is missing")
    if ext4.stat().st_size != EXT4_SIZE:
        parser.error(f"ext4 input must be exactly {EXT4_SIZE} bytes")
    try:
        salt = bytes.fromhex(args.salt)
    except ValueError as error:
        parser.error(f"invalid salt: {error}")
    if len(salt) != 32:
        parser.error("salt must be exactly 32 bytes")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")

    ext4_sha256 = sha256_file(ext4)
    if args.expected_ext4_sha256 and ext4_sha256 != args.expected_ext4_sha256:
        parser.error("ext4 SHA-256 does not match the expected candidate")

    tree = output / "verity-tree.img"
    tree_stdout = output / "verity-tree.stdout"
    metadata = output / "verity-metadata.img"
    table_file = output / "verity-table.txt"
    table_signature = output / "verity-table.sig"
    verity_plus_metadata = output / "verity-plus-metadata.img"
    fec = output / "fec.img"
    partition = output / "system.partition.raw"
    verifier_report = output / "verification.json"

    try:
        image_inspect = run(
            [docker, "image", "inspect", args.builder_image, "--format", "{{.Id}}"],
            capture=True,
        ).stdout.strip()
        tree_build = run([
            docker, "run", "--rm",
            "-v", f"{ext4}:/input/system.ext4.raw:ro",
            "-v", f"{output}:/output",
            args.builder_image,
            "-c",
            f"build_verity_tree -A {args.salt} /input/system.ext4.raw /output/verity-tree.img",
        ], capture=True)
        tree_stdout.write_text(tree_build.stdout, encoding="utf-8")
        tokens = tree_build.stdout.strip().split()
        if len(tokens) != 2 or tokens[1] != args.salt:
            raise ValueError("builder returned an unexpected verity root/salt line")
        root_hash = tokens[0]
        if len(bytes.fromhex(root_hash)) != 32:
            raise ValueError("builder returned an invalid verity root hash")

        table = (
            f"1 {BLOCK_DEVICE} {BLOCK_DEVICE} {BLOCK_SIZE} {BLOCK_SIZE} "
            f"{EXT4_BLOCKS} {EXT4_BLOCKS} sha256 {root_hash} {args.salt}"
        ).encode("ascii")
        table_file.write_bytes(table)
        run([
            openssl, "dgst", "-sha256", "-sign", str(private_key),
            "-out", str(table_signature), str(table_file),
        ])
        signature = table_signature.read_bytes()
        if len(signature) != 256:
            raise ValueError(f"verity table signature must be 256 bytes, found {len(signature)}")
        metadata_bytes = struct.pack(
            "<II256sI", VERITY_MAGIC, VERITY_VERSION, signature, len(table)
        ) + table
        if len(metadata_bytes) > METADATA_SIZE:
            raise ValueError("verity metadata exceeds its fixed 8-block region")
        metadata.write_bytes(metadata_bytes.ljust(METADATA_SIZE, b"\0"))

        shutil.copyfile(tree, verity_plus_metadata)
        with verity_plus_metadata.open("ab") as file_handle:
            append_file(file_handle, metadata)
        run([
            docker, "run", "--rm",
            "-v", f"{ext4}:/input/system.ext4.raw:ro",
            "-v", f"{output}:/output",
            args.builder_image,
            "-c",
            "fec -e -j 4 /input/system.ext4.raw /output/verity-plus-metadata.img /output/fec.img",
        ], capture=True)

        copy_strategy = clone_or_copy(ext4, partition)
        with partition.open("ab") as file_handle:
            append_file(file_handle, tree)
            append_file(file_handle, metadata)
            append_file(file_handle, fec)
        if partition.stat().st_size != PARTITION_SIZE:
            raise ValueError(
                f"verified system partition must be {PARTITION_SIZE} bytes, "
                f"found {partition.stat().st_size}"
            )

        verifier = Path(__file__).resolve().parent / "inspect-legacy-system-verity.py"
        run([
            sys.executable, str(verifier), "--system", str(partition),
            "--verity-key", str(verity_key), "--output", str(verifier_report),
        ], capture=True)
        verification = json.loads(verifier_report.read_text(encoding="utf-8"))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    report = {
        "schema": 1,
        "classification": "development-probe-not-for-device-release",
        "device_write_authorized": False,
        "builder_image_requested": args.builder_image,
        "builder_image_id": image_inspect,
        "input": {
            "ext4": str(ext4),
            "size": EXT4_SIZE,
            "sha256": ext4_sha256,
        },
        "verity": {
            "salt": args.salt,
            "root_hash": root_hash,
            "table": table.decode("ascii"),
            "tree_sha256": sha256_file(tree),
            "metadata_sha256": sha256_file(metadata),
            "metadata_signature_valid": verification["metadata"]["signature_valid"],
            "mincrypt_public_key_sha256": verification["verity_key"]["sha256"],
        },
        "fec": {
            "sha256": sha256_file(fec),
            "size": fec.stat().st_size,
            "payload_sha256": verification["fec"]["payload_sha256"],
            "roots": verification["fec"]["roots"],
        },
        "partition": {
            "size": partition.stat().st_size,
            "sha256": verification["input_sha256"],
            "copy_strategy": copy_strategy,
            "independent_verification": True,
        },
    }
    (output / "build-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
