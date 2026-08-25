#!/usr/bin/env python3
"""Build an offline leo project boot by replacing only ramdisk /verity_key.

The stock kernel section, addresses, command line, DTBs, and all cpio metadata
remain unchanged.  The resulting image receives a valid Android
BootSignature v1 SHA256withRSA footer and is independently inspected before it
is accepted as a development probe.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path


BOOT_MAGIC = b"ANDROID!"
HEADER_SIZE = 1632
SHA256_WITH_RSA_OID = bytes.fromhex("2a864886f70d01010b")
DEFAULT_BUILDER = "sha256:1dcbf603cec7f3546fb3edc3712142f1bb498cdc950404f76fa9edcdfdbdf935"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def der_length(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    encoded = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(encoded)]) + encoded


def der(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + der_length(len(value)) + value


def der_integer(value: int) -> bytes:
    encoded = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if encoded[0] & 0x80:
        encoded = b"\0" + encoded
    return der(0x02, encoded)


def der_sequence(*items: bytes) -> bytes:
    return der(0x30, b"".join(items))


def cpio_replace_same_size(archive: bytes, target: str, replacement: bytes) -> tuple[bytes, dict[str, object]]:
    result = bytearray(archive)
    cursor = 0
    matches: list[dict[str, object]] = []
    entries = 0
    while True:
        if cursor + 110 > len(archive):
            raise ValueError("truncated newc header")
        header = archive[cursor:cursor + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError(f"unsupported cpio magic at offset {cursor}")
        try:
            fields = [int(header[6 + index * 8:14 + index * 8], 16) for index in range(13)]
        except ValueError as error:
            raise ValueError(f"invalid newc numeric field at offset {cursor}") from error
        file_size = fields[6]
        name_size = fields[11]
        if name_size < 1:
            raise ValueError("cpio entry has empty name field")
        name_start = cursor + 110
        name_end = name_start + name_size
        if name_end > len(archive) or archive[name_end - 1] != 0:
            raise ValueError("truncated or unterminated cpio name")
        try:
            name = archive[name_start:name_end - 1].decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError("non-UTF-8 cpio name") from error
        data_start = align(name_end, 4)
        data_end = data_start + file_size
        if data_end > len(archive):
            raise ValueError("cpio payload exceeds archive")
        entries += 1
        if name in (target, f"./{target}"):
            if file_size != len(replacement):
                raise ValueError(
                    f"{name} size {file_size} does not match replacement size {len(replacement)}"
                )
            original = archive[data_start:data_end]
            result[data_start:data_end] = replacement
            matches.append({
                "name": name,
                "payload_offset": data_start,
                "size": file_size,
                "original_sha256": sha256(original),
                "replacement_sha256": sha256(replacement),
            })
        cursor = align(data_end, 4)
        if name == "TRAILER!!!":
            break
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {target!r} entry, found {len(matches)}")
    if len(result) != len(archive):
        raise ValueError("cpio replacement changed archive length")
    return bytes(result), {"entries": entries, "replacement": matches[0]}


def run(command: list[str], *, input_data: bytes | None = None) -> bytes:
    completed = subprocess.run(
        command,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return completed.stdout


def docker_image_id(docker: str, requested: str) -> str:
    return run([docker, "image", "inspect", requested, "--format", "{{.Id}}"]).decode().strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_formal_key_gate(
    manifest_path: Path,
    remount_report_path: Path,
    private_key: Path,
    verity_key: Path,
    certificate: Path,
    passphrase_environment: str,
) -> dict[str, object]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    remount = json.loads(remount_report_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "phase4_formal_release_keys_encrypted":
        raise ValueError("unexpected formal key manifest classification")
    if manifest.get("device_write_authorized") is not False:
        raise ValueError("formal key manifest must not authorize device writes")
    expected = manifest["files"]
    for path in (private_key, verity_key, certificate):
        member = expected.get(path.name)
        if not member or path.stat().st_size != member["size"] or sha256_file(path) != member["sha256"]:
            raise ValueError(f"formal key member differs from manifest: {path}")
    identity = manifest["public_identity"]
    if sha256_file(verity_key) != identity["verity_mincrypt_sha256"]:
        raise ValueError("formal verity public identity mismatch")
    if sha256_file(certificate) != identity["boot_certificate_der_sha256"]:
        raise ValueError("formal boot certificate identity mismatch")
    if remount.get("classification") != "phase4_release_key_remount_verification":
        raise ValueError("unexpected release-key remount report classification")
    if remount.get("key_manifest_sha256") != sha256_file(manifest_path):
        raise ValueError("remount report is not bound to this key manifest")
    if not all((
        remount.get("independent_physical_disks"),
        remount.get("all_expected_members_match"),
        remount.get("remount_readback_verified"),
        remount.get("keychain_decrypt_verified", {}).get("verity"),
        remount.get("keychain_decrypt_verified", {}).get("boot"),
    )):
        raise ValueError("formal release-key remount gate is incomplete")
    if remount.get("device_write_authorized") is not False:
        raise ValueError("remount report must not authorize device writes")
    if not passphrase_environment or not os.environ.get(passphrase_environment):
        raise ValueError("formal signing passphrase environment is absent")
    return {
        "key_ids": manifest["key_ids"],
        "key_manifest_sha256": sha256_file(manifest_path),
        "remount_report_sha256": sha256_file(remount_report_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock-boot", required=True, type=Path)
    parser.add_argument("--verity-key", required=True, type=Path)
    parser.add_argument("--boot-private-key", required=True, type=Path)
    parser.add_argument("--boot-certificate-der", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-stock-sha256", required=True)
    parser.add_argument("--builder-image", default=DEFAULT_BUILDER)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--development-probe", action="store_true")
    mode.add_argument("--formal-release", action="store_true")
    parser.add_argument("--key-manifest", type=Path)
    parser.add_argument("--remount-report", type=Path)
    parser.add_argument("--private-key-passphrase-env")
    args = parser.parse_args()

    stock_path = args.stock_boot.resolve()
    verity_key_path = args.verity_key.resolve()
    private_key_path = args.boot_private_key.resolve()
    certificate_path = args.boot_certificate_der.resolve()
    for required in (stock_path, verity_key_path, private_key_path, certificate_path):
        if not required.is_file():
            parser.error(f"required input does not exist: {required}")
    replacement_key = verity_key_path.read_bytes()
    if len(replacement_key) != 524:
        parser.error(f"verity_key must be exactly 524 bytes, found {len(replacement_key)}")
    formal_gate: dict[str, object] | None = None
    if args.formal_release:
        if not args.key_manifest or not args.remount_report or not args.private_key_passphrase_env:
            parser.error("formal release requires key manifest, remount report, and passphrase environment")
        try:
            formal_gate = validate_formal_key_gate(
                args.key_manifest.resolve(), args.remount_report.resolve(), private_key_path,
                verity_key_path, certificate_path, args.private_key_passphrase_env,
            )
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            parser.error(str(error))
    elif args.key_manifest or args.remount_report or args.private_key_passphrase_env:
        parser.error("formal key gate options are forbidden in development-probe mode")

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")

    docker = shutil.which("docker")
    openssl = shutil.which("openssl")
    if not docker or not openssl:
        parser.error("docker and openssl are required")

    try:
        stock = stock_path.read_bytes()
        if sha256(stock) != args.expected_stock_sha256.lower():
            raise ValueError("stock boot SHA-256 does not match the pinned input")
        if len(stock) < HEADER_SIZE or stock[:8] != BOOT_MAGIC:
            raise ValueError("stock input is not a supported legacy boot image")
        fields = struct.unpack_from("<10I", stock, 8)
        kernel_size, _, ramdisk_size, _, second_size, _, _, page_size, dt_size, _ = fields
        if page_size != 4096 or second_size != 0 or dt_size != 0:
            raise ValueError("stock boot geometry differs from the pinned leo profile")
        kernel_offset = page_size
        ramdisk_offset = align(kernel_offset + kernel_size, page_size)
        signable_size = align(ramdisk_offset + ramdisk_size, page_size)
        if signable_size >= len(stock):
            raise ValueError("stock boot is missing its expected signature footer")
        header_page = bytearray(stock[:page_size])
        kernel = stock[kernel_offset:kernel_offset + kernel_size]
        kernel_pages = stock[kernel_offset:ramdisk_offset]
        stock_ramdisk = stock[ramdisk_offset:ramdisk_offset + ramdisk_size]
        if stock_ramdisk[:3] != b"\x1f\x8b\x08":
            raise ValueError("stock ramdisk is not gzip compressed")

        stock_cpio = gzip.decompress(stock_ramdisk)
        project_cpio, cpio_report = cpio_replace_same_size(
            stock_cpio, "verity_key", replacement_key
        )
        (output / "ramdisk.cpio").write_bytes(project_cpio)

        requested_image = args.builder_image
        actual_image = docker_image_id(docker, requested_image)
        if requested_image.startswith("sha256:") and actual_image != requested_image:
            raise ValueError(f"builder image mismatch: requested {requested_image}, got {actual_image}")
        run([
            docker, "run", "--rm",
            "-v", f"{output}:/work",
            "--entrypoint", "sh", requested_image,
            "-lc", "gzip -n -6 -c /work/ramdisk.cpio > /work/ramdisk.bin",
        ])
        project_ramdisk = (output / "ramdisk.bin").read_bytes()

        struct.pack_into("<I", header_page, 16, len(project_ramdisk))
        digest = hashlib.sha1()
        digest.update(kernel)
        digest.update(struct.pack("<I", len(kernel)))
        digest.update(project_ramdisk)
        digest.update(struct.pack("<I", len(project_ramdisk)))
        digest.update(struct.pack("<I", 0))
        header_page[576:608] = digest.digest().ljust(32, b"\0")

        signable = bytes(header_page) + kernel_pages + project_ramdisk
        signable += b"\0" * (align(len(signable), page_size) - len(signable))
        expected_signable_size = page_size + align(kernel_size, page_size) + align(
            len(project_ramdisk), page_size
        )
        if len(signable) != expected_signable_size:
            raise ValueError("rebuilt boot boundary does not match legacy geometry")
        (output / "boot.signable.img").write_bytes(signable)

        attributes = der_sequence(der(0x13, b"/boot"), der_integer(len(signable)))
        signed_data_path = output / "boot.signed-data.bin"
        signature_path = output / "boot.signature.bin"
        signed_data_path.write_bytes(signable + attributes)
        sign_command = [
            openssl, "dgst", "-sha256", "-sign", str(private_key_path),
        ]
        if args.formal_release:
            sign_command += ["-passin", f"env:{args.private_key_passphrase_env}"]
        sign_command += ["-out", str(signature_path), str(signed_data_path)]
        run(sign_command)
        signature = signature_path.read_bytes()
        if len(signature) != 256:
            raise ValueError(f"unexpected RSA-2048 signature size: {len(signature)}")
        certificate_der = certificate_path.read_bytes()
        algorithm = der_sequence(der(0x06, SHA256_WITH_RSA_OID))
        footer = der_sequence(
            der_integer(1), certificate_der, algorithm, attributes, der(0x04, signature)
        )
        project_boot = signable + footer
        project_boot_path = output / (
            "boot-project-release.img" if args.formal_release else "boot-project-probe.img"
        )
        project_boot_path.write_bytes(project_boot)

        verifier_path = Path(__file__).with_name("inspect-legacy-boot-signature.py")
        verifier_report = output / "boot-signature-verification.json"
        run([
            sys.executable, os.fspath(verifier_path),
            "--boot", str(project_boot_path),
            "--expected-target", "/boot",
            "--output", str(verifier_report),
        ])
        verification = json.loads(verifier_report.read_text(encoding="utf-8"))
        if not verification.get("signature_valid"):
            raise ValueError("independent BootSignature verification failed")

        changed_cpio = sum(a != b for a, b in zip(stock_cpio, project_cpio))
        if changed_cpio == 0:
            raise ValueError("project verity_key unexpectedly matches stock")
        report = {
            "schema": 1,
            "classification": (
                "phase4-formal-release-candidate-boot"
                if args.formal_release else "development-probe-not-for-device-release"
            ),
            "device_write_authorized": False,
            "formal_key_gate": formal_gate,
            "builder_image_requested": requested_image,
            "builder_image_id": actual_image,
            "stock": {
                "path": str(stock_path),
                "size": len(stock),
                "sha256": sha256(stock),
                "kernel_sha256": sha256(kernel),
                "ramdisk_sha256": sha256(stock_ramdisk),
                "cpio_sha256": sha256(stock_cpio),
            },
            "project": {
                "boot_size": len(project_boot),
                "boot_sha256": sha256(project_boot),
                "signable_size": len(signable),
                "signable_sha256": sha256(signable),
                "kernel_sha256": sha256(kernel),
                "ramdisk_size": len(project_ramdisk),
                "ramdisk_sha256": sha256(project_ramdisk),
                "cpio_sha256": sha256(project_cpio),
                "cpio_changed_byte_count": changed_cpio,
                "verity_key_sha256": sha256(replacement_key),
                "cpio": cpio_report,
                "boot_signature_footer_sha256": sha256(footer),
                "boot_signature_valid": True,
                "boot_signature_target": "/boot",
                "boot_signature_algorithm": "sha256WithRSAEncryption",
                "certificate_der_sha256": sha256(certificate_der),
            },
            "invariants": {
                "kernel_section_unchanged": True,
                "kernel_dtb_cmdline_addresses_unchanged": True,
                "cpio_length_unchanged": len(project_cpio) == len(stock_cpio),
                "only_cpio_verity_key_payload_changed": True,
                "independent_boot_signature_verification": True,
            },
        }
        (output / "build-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
