#!/usr/bin/env python3
"""Inspect and cryptographically verify an Android BootSignature v1 footer.

This intentionally supports only the legacy v0-compatible boot layout used by
Xiaomi leo.  It rejects unsigned, truncated, non-DER, or structurally ambiguous
inputs instead of guessing where the signed image ends.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


BOOT_MAGIC = b"ANDROID!"
LEGACY_HEADER_SIZE = 1632

SIGNATURE_ALGORITHMS = {
    "1.2.840.113549.1.1.5": ("sha1WithRSAEncryption", "-sha1"),
    "1.2.840.113549.1.1.11": ("sha256WithRSAEncryption", "-sha256"),
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def align(value: int, page_size: int) -> int:
    return (value + page_size - 1) // page_size * page_size


@dataclass(frozen=True)
class Tlv:
    tag: int
    start: int
    value_start: int
    end: int

    def raw(self, data: bytes) -> bytes:
        return data[self.start:self.end]

    def value(self, data: bytes) -> bytes:
        return data[self.value_start:self.end]


def read_tlv(data: bytes, offset: int) -> Tlv:
    if offset + 2 > len(data):
        raise ValueError("truncated DER header")
    tag = data[offset]
    first_length = data[offset + 1]
    cursor = offset + 2
    if first_length < 0x80:
        length = first_length
    else:
        length_bytes = first_length & 0x7F
        if length_bytes == 0 or length_bytes > 4 or cursor + length_bytes > len(data):
            raise ValueError("unsupported or truncated DER length")
        encoded = data[cursor:cursor + length_bytes]
        if encoded[0] == 0:
            raise ValueError("non-minimal DER length")
        length = int.from_bytes(encoded, "big")
        if length < 0x80:
            raise ValueError("non-minimal long-form DER length")
        cursor += length_bytes
    end = cursor + length
    if end > len(data):
        raise ValueError("DER value exceeds input")
    return Tlv(tag=tag, start=offset, value_start=cursor, end=end)


def children(data: bytes, sequence: Tlv) -> list[Tlv]:
    if sequence.tag != 0x30:
        raise ValueError("expected DER SEQUENCE")
    result: list[Tlv] = []
    cursor = sequence.value_start
    while cursor < sequence.end:
        child = read_tlv(data, cursor)
        if child.end > sequence.end:
            raise ValueError("DER child exceeds parent")
        result.append(child)
        cursor = child.end
    if cursor != sequence.end:
        raise ValueError("DER children do not close parent")
    return result


def positive_integer(data: bytes, item: Tlv) -> int:
    if item.tag != 0x02:
        raise ValueError("expected DER INTEGER")
    value = item.value(data)
    if not value or value[0] & 0x80:
        raise ValueError("negative or empty DER INTEGER is unsupported")
    if len(value) > 1 and value[0] == 0 and not value[1] & 0x80:
        raise ValueError("non-minimal DER INTEGER")
    return int.from_bytes(value, "big")


def decode_oid(data: bytes, item: Tlv) -> str:
    if item.tag != 0x06:
        raise ValueError("expected DER OBJECT IDENTIFIER")
    encoded = item.value(data)
    if not encoded:
        raise ValueError("empty DER OBJECT IDENTIFIER")
    arcs = [encoded[0] // 40, encoded[0] % 40]
    value = 0
    for byte in encoded[1:]:
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            arcs.append(value)
            value = 0
    if encoded[-1] & 0x80:
        raise ValueError("truncated DER OBJECT IDENTIFIER")
    return ".".join(str(arc) for arc in arcs)


def legacy_signable_size(image: bytes) -> tuple[int, dict[str, int]]:
    if len(image) < LEGACY_HEADER_SIZE or image[:8] != BOOT_MAGIC:
        raise ValueError("not a supported legacy Android boot image")
    fields = struct.unpack_from("<10I", image, 8)
    kernel_size, _, ramdisk_size, _, second_size, _, _, page_size, dt_size, _ = fields
    if page_size < 512 or page_size & (page_size - 1):
        raise ValueError(f"invalid boot page size: {page_size}")
    if dt_size != 0:
        raise ValueError("legacy header dt_size is non-zero; refusing ambiguous footer boundary")
    size = page_size
    size += align(kernel_size, page_size)
    size += align(ramdisk_size, page_size)
    size += align(second_size, page_size)
    size = align(size, page_size)
    if size >= len(image):
        raise ValueError("boot image has no BootSignature footer")
    return size, {
        "kernel_size": kernel_size,
        "ramdisk_size": ramdisk_size,
        "second_size": second_size,
        "page_size": page_size,
        "dt_size": dt_size,
    }


def parse_boot_signature(footer: bytes) -> dict[str, object]:
    outer = read_tlv(footer, 0)
    if outer.tag != 0x30 or outer.end != len(footer):
        raise ValueError("footer is not one exact DER SEQUENCE")
    fields = children(footer, outer)
    if len(fields) != 5:
        raise ValueError(f"BootSignature must contain 5 fields, found {len(fields)}")

    version = positive_integer(footer, fields[0])
    if version != 1:
        raise ValueError(f"unsupported BootSignature format version: {version}")

    certificate = fields[1]
    if certificate.tag != 0x30:
        raise ValueError("BootSignature certificate is not a DER SEQUENCE")

    algorithm_fields = children(footer, fields[2])
    if not algorithm_fields:
        raise ValueError("empty BootSignature algorithm identifier")
    algorithm_oid = decode_oid(footer, algorithm_fields[0])
    if algorithm_oid not in SIGNATURE_ALGORITHMS:
        raise ValueError(f"unsupported BootSignature algorithm: {algorithm_oid}")

    attributes = fields[3]
    attribute_fields = children(footer, attributes)
    if len(attribute_fields) != 2 or attribute_fields[0].tag != 0x13:
        raise ValueError("unexpected BootSignature authenticated attributes")
    try:
        target = attribute_fields[0].value(footer).decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("BootSignature target is not ASCII") from error
    authenticated_length = positive_integer(footer, attribute_fields[1])

    signature = fields[4]
    if signature.tag != 0x04:
        raise ValueError("BootSignature signature is not an OCTET STRING")

    return {
        "format_version": version,
        "certificate_der": certificate.raw(footer),
        "algorithm_oid": algorithm_oid,
        "algorithm_name": SIGNATURE_ALGORITHMS[algorithm_oid][0],
        "openssl_digest_flag": SIGNATURE_ALGORITHMS[algorithm_oid][1],
        "authenticated_attributes_der": attributes.raw(footer),
        "target": target,
        "authenticated_length": authenticated_length,
        "signature": signature.value(footer),
    }


def run_checked(command: list[str], *, input_data: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def verify_with_openssl(
    image: bytes,
    signable_size: int,
    parsed: dict[str, object],
) -> tuple[bool, list[str], list[str]]:
    openssl = shutil.which("openssl")
    if not openssl:
        raise ValueError("openssl is required for BootSignature verification")

    certificate = parsed["certificate_der"]
    attributes = parsed["authenticated_attributes_der"]
    signature = parsed["signature"]
    assert isinstance(certificate, bytes)
    assert isinstance(attributes, bytes)
    assert isinstance(signature, bytes)

    with tempfile.TemporaryDirectory(prefix="leo-bootsig-") as directory:
        root = Path(directory)
        cert_path = root / "certificate.der"
        public_key_path = root / "public-key.pem"
        signature_path = root / "signature.bin"
        signed_data_path = root / "signed-data.bin"
        cert_path.write_bytes(certificate)
        signature_path.write_bytes(signature)
        signed_data_path.write_bytes(image[:signable_size] + attributes)

        public_key = run_checked([
            openssl, "x509", "-inform", "DER", "-in", str(cert_path), "-pubkey", "-noout",
        ]).stdout
        public_key_path.write_bytes(public_key)
        certificate_summary = run_checked([
            openssl, "x509", "-inform", "DER", "-in", str(cert_path), "-noout",
            "-subject", "-issuer", "-serial", "-fingerprint", "-sha256",
        ]).stdout.decode("utf-8", errors="replace").strip().splitlines()

        matches: list[str] = []
        for algorithm_name, candidate_flag in SIGNATURE_ALGORITHMS.values():
            completed = subprocess.run(
                [
                    openssl, "dgst", candidate_flag, "-verify", str(public_key_path),
                    "-signature", str(signature_path), str(signed_data_path),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if completed.returncode == 0 and b"Verified OK" in completed.stdout:
                matches.append(algorithm_name)
        valid = parsed["algorithm_name"] in matches
        return valid, certificate_summary, matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    parser.add_argument("--expected-target", default="/boot")
    parser.add_argument(
        "--allow-invalid-signature",
        action="store_true",
        help="emit an inspection report but do not accept the image as verified",
    )
    args = parser.parse_args()

    boot = args.boot.resolve()
    if not boot.is_file():
        parser.error(f"boot image does not exist: {boot}")

    try:
        image = boot.read_bytes()
        signable_size, header = legacy_signable_size(image)
        footer = image[signable_size:]
        parsed = parse_boot_signature(footer)
        if parsed["target"] != args.expected_target:
            raise ValueError(
                f"unexpected BootSignature target: {parsed['target']!r}; "
                f"expected {args.expected_target!r}"
            )
        if parsed["authenticated_length"] != signable_size:
            raise ValueError(
                "BootSignature authenticated length does not match the boot image boundary"
            )
        valid, certificate_summary, matching_algorithms = verify_with_openssl(
            image, signable_size, parsed
        )
        if not valid and not args.allow_invalid_signature:
            raise ValueError("BootSignature cryptographic verification failed")
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    certificate = parsed["certificate_der"]
    signature = parsed["signature"]
    assert isinstance(certificate, bytes)
    assert isinstance(signature, bytes)
    report = {
        "schema": 1,
        "classification": "android_boot_signature_v1",
        "input": str(boot),
        "input_size": len(image),
        "input_sha256": sha256(image),
        "legacy_header": header,
        "signable_size": signable_size,
        "footer_size": len(footer),
        "footer_sha256": sha256(footer),
        "format_version": parsed["format_version"],
        "target": parsed["target"],
        "authenticated_length": parsed["authenticated_length"],
        "signature_algorithm_oid": parsed["algorithm_oid"],
        "signature_algorithm": parsed["algorithm_name"],
        "signature_size": len(signature),
        "certificate_der_sha256": sha256(certificate),
        "certificate_summary": certificate_summary,
        "cryptographic_matching_algorithms": matching_algorithms,
        "signature_valid": valid,
    }
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
