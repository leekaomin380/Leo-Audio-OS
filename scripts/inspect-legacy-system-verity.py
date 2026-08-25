#!/usr/bin/env python3
"""Verify leo's legacy Android 7 dm-verity metadata, tree, and FEC footer.

The verifier operates on a raw system partition image and the 524-byte
Android mincrypt public key extracted from the matching boot ramdisk.  It does
not mount or modify the image and has no device interface.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path


BLOCK_SIZE = 4096
SHA256_SIZE = 32
VERITY_MAGIC = 0xB001B001
VERITY_VERSION = 0
VERITY_METADATA_SIZE = 8 * BLOCK_SIZE
VERITY_HEADER_SIZE = 4 + 4 + 256 + 4
FEC_MAGIC = 0xFECFECFE
FEC_VERSION = 0
FEC_HEADER_SIZE = 64
MINCRYPT_WORDS = 64
MINCRYPT_KEY_SIZE = (2 + MINCRYPT_WORDS + MINCRYPT_WORDS + 1) * 4


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file_region(file_handle, offset: int, size: int) -> str:
    digest = hashlib.sha256()
    file_handle.seek(offset)
    remaining = size
    while remaining:
        chunk = file_handle.read(min(4 * 1024 * 1024, remaining))
        if not chunk:
            raise ValueError("unexpected end of image while hashing a region")
        digest.update(chunk)
        remaining -= len(chunk)
    return digest.hexdigest()


def div_round_up(value: int, divisor: int) -> int:
    return (value + divisor - 1) // divisor


def verity_level_blocks(data_blocks: int) -> list[int]:
    hashes_per_block = BLOCK_SIZE // SHA256_SIZE
    result: list[int] = []
    blocks = data_blocks
    while True:
        blocks = div_round_up(blocks, hashes_per_block)
        result.append(blocks)
        if blocks == 1:
            return result


def der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def der_item(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + der_length(len(value)) + value


def der_integer(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative DER integer is unsupported")
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:
        encoded = b"\0" + encoded
    return der_item(0x02, encoded)


def mincrypt_public_key_to_spki(key: bytes) -> tuple[bytes, dict[str, int | str]]:
    if len(key) != MINCRYPT_KEY_SIZE:
        raise ValueError(
            f"Android mincrypt key must be {MINCRYPT_KEY_SIZE} bytes, found {len(key)}"
        )
    words = struct.unpack("<131I", key)
    length, n0inv = words[:2]
    modulus_words = words[2:2 + MINCRYPT_WORDS]
    rr_words = words[2 + MINCRYPT_WORDS:2 + MINCRYPT_WORDS * 2]
    exponent = words[-1]
    if length != MINCRYPT_WORDS:
        raise ValueError(f"unexpected mincrypt RSA word count: {length}")
    if exponent not in (3, 65537):
        raise ValueError(f"unexpected mincrypt RSA exponent: {exponent}")
    modulus = sum(word << (32 * index) for index, word in enumerate(modulus_words))
    if modulus.bit_length() != 2048:
        raise ValueError(f"unexpected mincrypt RSA modulus size: {modulus.bit_length()} bits")
    if not n0inv or not any(rr_words):
        raise ValueError("mincrypt Montgomery parameters are empty")

    rsa_public_key = der_item(0x30, der_integer(modulus) + der_integer(exponent))
    rsa_encryption_oid = bytes.fromhex("06092a864886f70d010101")
    algorithm_identifier = der_item(0x30, rsa_encryption_oid + b"\x05\x00")
    spki = der_item(0x30, algorithm_identifier + der_item(0x03, b"\0" + rsa_public_key))
    return spki, {
        "format": "android_mincrypt_rsa_public_key",
        "size": len(key),
        "words": length,
        "modulus_bits": modulus.bit_length(),
        "exponent": exponent,
        "sha256": sha256(key),
    }


def pem_public_key(spki: bytes) -> bytes:
    encoded = base64.b64encode(spki).decode("ascii")
    lines = [encoded[index:index + 64] for index in range(0, len(encoded), 64)]
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        + "\n".join(lines)
        + "\n-----END PUBLIC KEY-----\n"
    ).encode("ascii")


def verify_metadata_signature(table: bytes, signature: bytes, spki: bytes) -> bool:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("openssl is required for verity signature verification")
    with tempfile.TemporaryDirectory(prefix="leo-verity-") as directory:
        root = Path(directory)
        public_key = root / "verity-public.pem"
        table_file = root / "verity-table"
        signature_file = root / "verity-signature"
        public_key.write_bytes(pem_public_key(spki))
        table_file.write_bytes(table)
        signature_file.write_bytes(signature)
        completed = subprocess.run(
            [
                openssl, "dgst", "-sha256", "-verify", str(public_key),
                "-signature", str(signature_file), str(table_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    return completed.returncode == 0 and b"Verified OK" in completed.stdout


def parse_ext4_geometry(file_handle) -> tuple[int, int]:
    file_handle.seek(1024)
    superblock = file_handle.read(1024)
    if len(superblock) != 1024 or struct.unpack_from("<H", superblock, 56)[0] != 0xEF53:
        raise ValueError("input does not start with a supported ext4 filesystem")
    blocks_lo = struct.unpack_from("<I", superblock, 4)[0]
    log_block_size = struct.unpack_from("<I", superblock, 24)[0]
    block_size = 1024 << log_block_size
    if block_size != BLOCK_SIZE:
        raise ValueError(f"unsupported ext4 block size: {block_size}")
    return blocks_lo, block_size


def parse_fec_header(data: bytes) -> dict[str, int | bytes]:
    if len(data) != FEC_HEADER_SIZE:
        raise ValueError("invalid FEC header size")
    magic, version, size, roots, fec_size = struct.unpack_from("<5I", data, 0)
    inp_size = struct.unpack_from("<Q", data, 24)[0]
    payload_hash = data[32:64]
    return {
        "magic": magic,
        "version": version,
        "size": size,
        "roots": roots,
        "fec_size": fec_size,
        "inp_size": inp_size,
        "payload_hash": payload_hash,
    }


def build_and_verify_tree(
    file_handle,
    data_blocks: int,
    salt: bytes,
    stored_tree: bytes,
    expected_root: bytes,
) -> dict[str, object]:
    level_counts = verity_level_blocks(data_blocks)
    bottom = bytearray(level_counts[0] * BLOCK_SIZE)
    file_handle.seek(0)
    cursor = 0
    for _ in range(data_blocks):
        block = file_handle.read(BLOCK_SIZE)
        if len(block) != BLOCK_SIZE:
            raise ValueError("unexpected end of ext4 data while rebuilding verity tree")
        digest = hashlib.sha256(salt + block).digest()
        bottom[cursor:cursor + SHA256_SIZE] = digest
        cursor += SHA256_SIZE

    levels = [bytes(bottom)]
    current = levels[0]
    for expected_blocks in level_counts[1:]:
        output = bytearray(expected_blocks * BLOCK_SIZE)
        cursor = 0
        for offset in range(0, len(current), BLOCK_SIZE):
            digest = hashlib.sha256(salt + current[offset:offset + BLOCK_SIZE]).digest()
            output[cursor:cursor + SHA256_SIZE] = digest
            cursor += SHA256_SIZE
        current = bytes(output)
        levels.append(current)
    calculated_root = hashlib.sha256(salt + levels[-1]).digest()
    calculated_tree = b"".join(reversed(levels))
    return {
        "level_blocks_bottom_to_top": level_counts,
        "calculated_root_hash": calculated_root.hex(),
        "root_hash_matches": calculated_root == expected_root,
        "calculated_tree_sha256": sha256(calculated_tree),
        "stored_tree_sha256": sha256(stored_tree),
        "tree_bytes_match": calculated_tree == stored_tree,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, type=Path, help="raw system partition image")
    parser.add_argument("--verity-key", required=True, type=Path, help="524-byte boot ramdisk verity_key")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    parser.add_argument("--skip-tree", action="store_true", help="parse signatures and FEC but skip full Merkle rebuild")
    args = parser.parse_args()

    system = args.system.resolve()
    verity_key = args.verity_key.resolve()
    if not system.is_file() or not verity_key.is_file():
        parser.error("system image or verity key does not exist")

    try:
        partition_size = system.stat().st_size
        if partition_size % BLOCK_SIZE:
            raise ValueError("system partition size is not block aligned")
        key_data = verity_key.read_bytes()
        spki, key_report = mincrypt_public_key_to_spki(key_data)

        with system.open("rb") as file_handle:
            data_blocks, block_size = parse_ext4_geometry(file_handle)
            level_counts = verity_level_blocks(data_blocks)
            tree_blocks = sum(level_counts)
            tree_offset = data_blocks * BLOCK_SIZE
            tree_size = tree_blocks * BLOCK_SIZE
            metadata_offset = tree_offset + tree_size
            file_handle.seek(tree_offset)
            stored_tree = file_handle.read(tree_size)
            file_handle.seek(metadata_offset)
            metadata = file_handle.read(VERITY_METADATA_SIZE)
            if len(stored_tree) != tree_size or len(metadata) != VERITY_METADATA_SIZE:
                raise ValueError("system image ends before the verity tree or metadata")

            magic, version = struct.unpack_from("<II", metadata, 0)
            signature = metadata[8:264]
            table_length = struct.unpack_from("<I", metadata, 264)[0]
            if magic != VERITY_MAGIC or version != VERITY_VERSION:
                raise ValueError("unexpected verity metadata magic or version")
            if not 1 <= table_length <= VERITY_METADATA_SIZE - VERITY_HEADER_SIZE:
                raise ValueError("invalid verity table length")
            table = metadata[VERITY_HEADER_SIZE:VERITY_HEADER_SIZE + table_length]
            if any(metadata[VERITY_HEADER_SIZE + table_length:]):
                raise ValueError("verity metadata padding is not all zeroes")
            try:
                table_text = table.decode("ascii")
            except UnicodeDecodeError as error:
                raise ValueError("verity table is not ASCII") from error
            fields = table_text.split(" ")
            if len(fields) != 10:
                raise ValueError(f"unexpected verity table field count: {len(fields)}")
            table_version, data_device, hash_device = fields[:3]
            data_block_size, hash_block_size, table_data_blocks, hash_start = map(int, fields[3:7])
            algorithm, root_hash_hex, salt_hex = fields[7:]
            if table_version != "1" or algorithm != "sha256":
                raise ValueError("unsupported verity table version or hash algorithm")
            if data_block_size != BLOCK_SIZE or hash_block_size != BLOCK_SIZE:
                raise ValueError("unexpected verity table block size")
            if table_data_blocks != data_blocks or hash_start != data_blocks:
                raise ValueError("verity table geometry does not match ext4")
            if data_device != hash_device:
                raise ValueError("verity table data and hash devices differ")
            root_hash = bytes.fromhex(root_hash_hex)
            salt = bytes.fromhex(salt_hex)
            if len(root_hash) != SHA256_SIZE or len(salt) != SHA256_SIZE:
                raise ValueError("verity root hash or salt is not 32 bytes")
            signature_valid = verify_metadata_signature(table, signature, spki)
            if not signature_valid:
                raise ValueError("verity metadata signature is invalid for the supplied boot key")

            file_handle.seek(partition_size - BLOCK_SIZE)
            fec_footer_block = file_handle.read(BLOCK_SIZE)
            fec_header_start = parse_fec_header(fec_footer_block[:FEC_HEADER_SIZE])
            fec_header_end = parse_fec_header(fec_footer_block[-FEC_HEADER_SIZE:])
            if fec_header_start != fec_header_end:
                raise ValueError("FEC header copies at both ends of the footer block differ")
            fec = fec_header_start
            if (
                fec["magic"] != FEC_MAGIC
                or fec["version"] != FEC_VERSION
                or fec["size"] != FEC_HEADER_SIZE
            ):
                raise ValueError("unexpected FEC magic, version, or header size")
            fec_input_size = metadata_offset + VERITY_METADATA_SIZE
            if fec["inp_size"] != fec_input_size:
                raise ValueError("FEC input size does not close at the end of verity metadata")
            fec_size = int(fec["fec_size"])
            if fec_input_size + fec_size + BLOCK_SIZE != partition_size:
                raise ValueError("FEC payload and footer do not close the system partition")
            fec_payload_sha256 = sha256_file_region(file_handle, fec_input_size, fec_size)
            payload_hash = fec["payload_hash"]
            assert isinstance(payload_hash, bytes)
            if fec_payload_sha256 != payload_hash.hex():
                raise ValueError("FEC payload SHA-256 does not match its footer")

            tree_report: dict[str, object] | None = None
            if not args.skip_tree:
                tree_report = build_and_verify_tree(
                    file_handle, data_blocks, salt, stored_tree, root_hash
                )
                if not tree_report["root_hash_matches"] or not tree_report["tree_bytes_match"]:
                    raise ValueError("rebuilt verity tree or root hash does not match the image")
    except (OSError, ValueError, struct.error, subprocess.SubprocessError) as error:
        parser.error(str(error))

    with system.open("rb") as file_handle:
        input_sha256 = sha256_file_region(file_handle, 0, partition_size)

    report = {
        "schema": 1,
        "classification": "android_legacy_dm_verity_fec",
        "input": str(system),
        "input_size": partition_size,
        "input_sha256": input_sha256,
        "block_size": block_size,
        "partition_blocks": partition_size // BLOCK_SIZE,
        "ext4": {
            "blocks": data_blocks,
            "size": data_blocks * BLOCK_SIZE,
        },
        "hash_tree": {
            "offset": tree_offset,
            "blocks": tree_blocks,
            "size": tree_size,
            "stored_sha256": sha256(stored_tree),
            "verification": tree_report,
        },
        "metadata": {
            "offset": metadata_offset,
            "size": VERITY_METADATA_SIZE,
            "magic": f"0x{magic:08x}",
            "version": version,
            "table_length": table_length,
            "table": table_text,
            "block_device": data_device,
            "root_hash": root_hash_hex,
            "salt": salt_hex,
            "signature_sha256": sha256(signature),
            "signature_valid": signature_valid,
        },
        "verity_key": key_report,
        "fec": {
            "magic": f"0x{int(fec['magic']):08x}",
            "version": fec["version"],
            "header_size": fec["size"],
            "roots": fec["roots"],
            "input_size": fec["inp_size"],
            "payload_offset": fec_input_size,
            "payload_size": fec_size,
            "payload_sha256": fec_payload_sha256,
            "footer_offset": partition_size - BLOCK_SIZE,
            "footer_copies_identical": True,
        },
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
