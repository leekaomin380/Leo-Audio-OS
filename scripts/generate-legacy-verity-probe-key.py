#!/usr/bin/env python3
"""Generate a disposable RSA-2048 Android legacy verity probe key.

This script deliberately cannot create a release key.  Its unencrypted private
material is suitable only for the ignored Phase 4 toolchain probe directory and
must be replaced by an offline key ceremony before any device release.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path


RSA_WORDS = 64
RSA_BITS = 2048


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Tlv:
    tag: int
    start: int
    value_start: int
    end: int

    def value(self, data: bytes) -> bytes:
        return data[self.value_start:self.end]


def read_tlv(data: bytes, offset: int) -> Tlv:
    if offset + 2 > len(data):
        raise ValueError("truncated DER")
    tag = data[offset]
    first = data[offset + 1]
    cursor = offset + 2
    if first < 0x80:
        length = first
    else:
        count = first & 0x7F
        if count == 0 or count > 4 or cursor + count > len(data):
            raise ValueError("unsupported DER length")
        length = int.from_bytes(data[cursor:cursor + count], "big")
        cursor += count
    end = cursor + length
    if end > len(data):
        raise ValueError("DER value exceeds input")
    return Tlv(tag, offset, cursor, end)


def children(data: bytes, parent: Tlv) -> list[Tlv]:
    if parent.tag != 0x30:
        raise ValueError("expected DER SEQUENCE")
    result: list[Tlv] = []
    cursor = parent.value_start
    while cursor < parent.end:
        item = read_tlv(data, cursor)
        if item.end > parent.end:
            raise ValueError("DER child exceeds parent")
        result.append(item)
        cursor = item.end
    if cursor != parent.end:
        raise ValueError("DER sequence does not close")
    return result


def positive_integer(data: bytes, item: Tlv) -> int:
    if item.tag != 0x02:
        raise ValueError("expected DER INTEGER")
    encoded = item.value(data)
    if not encoded or encoded[0] & 0x80:
        raise ValueError("invalid RSA INTEGER")
    return int.from_bytes(encoded, "big")


def parse_spki_rsa(spki: bytes) -> tuple[int, int]:
    outer = read_tlv(spki, 0)
    if outer.tag != 0x30 or outer.end != len(spki):
        raise ValueError("public key is not one exact SubjectPublicKeyInfo")
    fields = children(spki, outer)
    if len(fields) != 2 or fields[1].tag != 0x03:
        raise ValueError("unexpected SubjectPublicKeyInfo structure")
    bit_string = fields[1].value(spki)
    if not bit_string or bit_string[0] != 0:
        raise ValueError("RSA public key BIT STRING has unused bits")
    rsa = bit_string[1:]
    rsa_outer = read_tlv(rsa, 0)
    rsa_fields = children(rsa, rsa_outer)
    if rsa_outer.end != len(rsa) or len(rsa_fields) != 2:
        raise ValueError("unexpected RSAPublicKey structure")
    return positive_integer(rsa, rsa_fields[0]), positive_integer(rsa, rsa_fields[1])


def build_mincrypt_key(modulus: int, exponent: int) -> bytes:
    if modulus.bit_length() != RSA_BITS or exponent != 65537:
        raise ValueError("probe key must be RSA-2048 with exponent 65537")
    radix = 1 << 32
    n0inv = (-pow(modulus % radix, -1, radix)) % radix
    rr = pow(2, RSA_WORDS * 32 * 2, modulus)
    modulus_words = [(modulus >> (32 * index)) & 0xFFFFFFFF for index in range(RSA_WORDS)]
    rr_words = [(rr >> (32 * index)) & 0xFFFFFFFF for index in range(RSA_WORDS)]
    return struct.pack(
        "<131I", RSA_WORDS, n0inv, *modulus_words, *rr_words, exponent
    )


def pem_public_key(spki: bytes) -> bytes:
    encoded = base64.b64encode(spki).decode("ascii")
    lines = [encoded[index:index + 64] for index in range(0, len(encoded), 64)]
    return (
        "-----BEGIN PUBLIC KEY-----\n"
        + "\n".join(lines)
        + "\n-----END PUBLIC KEY-----\n"
    ).encode("ascii")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--key-id", default="leo-verity-development-probe-v1")
    parser.add_argument("--development-probe", action="store_true", required=True)
    args = parser.parse_args()

    openssl = shutil.which("openssl")
    if not openssl:
        parser.error("openssl is required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    os.chmod(output, 0o700)

    private_pem = output / "verity-private.pem"
    private_pk8 = output / "verity.pk8"
    public_der = output / "verity-public.spki.der"
    public_pem = output / "verity-public.pem"
    mincrypt_key = output / "verity_key"

    try:
        run([
            openssl, "genpkey", "-algorithm", "RSA",
            "-pkeyopt", f"rsa_keygen_bits:{RSA_BITS}",
            "-pkeyopt", "rsa_keygen_pubexp:65537",
            "-out", str(private_pem),
        ])
        run([
            openssl, "pkcs8", "-topk8", "-nocrypt", "-in", str(private_pem),
            "-outform", "DER", "-out", str(private_pk8),
        ])
        run([
            openssl, "pkey", "-in", str(private_pem), "-pubout", "-outform", "DER",
            "-out", str(public_der),
        ])
        spki = public_der.read_bytes()
        modulus, exponent = parse_spki_rsa(spki)
        android_key = build_mincrypt_key(modulus, exponent)
        public_pem.write_bytes(pem_public_key(spki))
        mincrypt_key.write_bytes(android_key)
        for private_file in (private_pem, private_pk8):
            os.chmod(private_file, 0o600)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    manifest = {
        "schema": 1,
        "classification": "development_probe_only_not_for_device_release",
        "key_id": args.key_id,
        "algorithm": "RSA-2048",
        "exponent": exponent,
        "metadata_signature": "SHA256withRSA PKCS1 v1.5",
        "private_key_encrypted": False,
        "release_use_allowed": False,
        "files": {
            "private_pem": {"name": private_pem.name, "sha256": sha256(private_pem.read_bytes())},
            "private_pkcs8_der": {"name": private_pk8.name, "sha256": sha256(private_pk8.read_bytes())},
            "public_spki_der": {"name": public_der.name, "sha256": sha256(spki)},
            "public_pem": {"name": public_pem.name, "sha256": sha256(public_pem.read_bytes())},
            "android_mincrypt_public": {
                "name": mincrypt_key.name,
                "size": len(android_key),
                "sha256": sha256(android_key),
            },
        },
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
