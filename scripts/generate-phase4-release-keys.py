#!/usr/bin/env python3
"""Generate encrypted Phase 4 verity/boot release keys on two USB media.

The two backup targets must be distinct writable external physical disks.  The
script never deletes or overwrites an existing path.  Random passphrases are
stored only in the macOS login Keychain; USB media receive encrypted private
keys and public material, never plaintext passphrases.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import json
import os
import plistlib
import secrets
import shutil
import struct
import subprocess
from pathlib import Path


RSA_WORDS = 64
RSA_BITS = 2048
BACKUP_NAME = "release-keys-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    command: list[str],
    *,
    environment: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=check,
    )


def media_info(diskutil: str, volume: Path) -> dict[str, object]:
    completed = run([diskutil, "info", "-plist", str(volume)])
    info = plistlib.loads(completed.stdout)
    required = ("MountPoint", "ParentWholeDisk", "VolumeUUID", "FilesystemType")
    if any(key not in info for key in required):
        raise ValueError(f"incomplete disk identity for {volume}")
    if info.get("Internal") or not info.get("RemovableMediaOrExternalDevice"):
        raise ValueError(f"backup target is not external removable media: {volume}")
    if not info.get("Writable") or not info.get("WritableVolume"):
        raise ValueError(f"backup target is not writable: {volume}")
    if Path(str(info["MountPoint"])).resolve() != volume.resolve():
        raise ValueError(f"mount-point identity changed for {volume}")
    return info


def read_tlv(data: bytes, offset: int) -> tuple[int, int, int]:
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
    return tag, cursor, end


def sequence_children(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    result: list[tuple[int, int, int]] = []
    cursor = start
    while cursor < end:
        tag, value_start, item_end = read_tlv(data, cursor)
        if item_end > end:
            raise ValueError("DER child exceeds sequence")
        result.append((tag, value_start, item_end))
        cursor = item_end
    if cursor != end:
        raise ValueError("DER sequence does not close")
    return result


def der_integer(data: bytes, item: tuple[int, int, int]) -> int:
    tag, start, end = item
    encoded = data[start:end]
    if tag != 0x02 or not encoded or encoded[0] & 0x80:
        raise ValueError("invalid positive DER integer")
    return int.from_bytes(encoded, "big")


def parse_spki_rsa(spki: bytes) -> tuple[int, int]:
    tag, start, end = read_tlv(spki, 0)
    if tag != 0x30 or end != len(spki):
        raise ValueError("public key is not one SubjectPublicKeyInfo")
    fields = sequence_children(spki, start, end)
    if len(fields) != 2 or fields[1][0] != 0x03:
        raise ValueError("unexpected SubjectPublicKeyInfo structure")
    bit_string = spki[fields[1][1]:fields[1][2]]
    if not bit_string or bit_string[0] != 0:
        raise ValueError("RSA public key BIT STRING has unused bits")
    rsa = bit_string[1:]
    rsa_tag, rsa_start, rsa_end = read_tlv(rsa, 0)
    if rsa_tag != 0x30 or rsa_end != len(rsa):
        raise ValueError("invalid RSAPublicKey structure")
    rsa_fields = sequence_children(rsa, rsa_start, rsa_end)
    if len(rsa_fields) != 2:
        raise ValueError("unexpected RSAPublicKey field count")
    return der_integer(rsa, rsa_fields[0]), der_integer(rsa, rsa_fields[1])


def mincrypt_key(modulus: int, exponent: int) -> bytes:
    if modulus.bit_length() != RSA_BITS or exponent != 65537:
        raise ValueError("release key must be RSA-2048 with exponent 65537")
    radix = 1 << 32
    n0inv = (-pow(modulus % radix, -1, radix)) % radix
    rr = pow(2, RSA_WORDS * 64, modulus)
    modulus_words = [(modulus >> (32 * index)) & 0xFFFFFFFF for index in range(RSA_WORDS)]
    rr_words = [(rr >> (32 * index)) & 0xFFFFFFFF for index in range(RSA_WORDS)]
    return struct.pack("<131I", RSA_WORDS, n0inv, *modulus_words, *rr_words, exponent)


def public_pem(spki: bytes) -> bytes:
    encoded = base64.b64encode(spki).decode("ascii")
    body = "\n".join(encoded[index:index + 64] for index in range(0, len(encoded), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{body}\n-----END PUBLIC KEY-----\n".encode("ascii")


def keychain_exists(security: str, account: str, service: str) -> bool:
    completed = run(
        [security, "find-generic-password", "-a", account, "-s", service], check=False
    )
    return completed.returncode == 0


def keychain_add(security: str, account: str, service: str, label: str, password: str) -> None:
    run([
        security, "add-generic-password", "-a", account, "-s", service,
        "-l", label, "-w", password,
    ])


def keychain_read(security: str, account: str, service: str) -> str:
    return run([
        security, "find-generic-password", "-a", account, "-s", service, "-w",
    ]).stdout.decode("utf-8").rstrip("\n")


def openssl_environment(password: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment["LEO_KEY_PASSPHRASE"] = password
    return environment


def encrypted_rsa(openssl: str, output: Path, password: str) -> None:
    run([
        openssl, "genpkey", "-algorithm", "RSA", "-aes-256-cbc",
        "-pass", "env:LEO_KEY_PASSPHRASE",
        "-pkeyopt", f"rsa_keygen_bits:{RSA_BITS}",
        "-pkeyopt", "rsa_keygen_pubexp:65537", "-out", str(output),
    ], environment=openssl_environment(password))
    os.chmod(output, 0o600)


def copy_and_verify(
    source: Path,
    destination: Path,
    expected_names: list[str],
    *,
    allow_existing: bool = False,
) -> dict[str, object]:
    if destination.exists() and not allow_existing:
        raise ValueError(f"refusing to overwrite existing backup: {destination}")
    destination.mkdir(parents=True, exist_ok=allow_existing)
    hashes: dict[str, str] = {}
    for name in expected_names:
        source_file = source / name
        destination_file = destination / name
        if not source_file.is_file():
            raise ValueError(f"local key member is missing: {source_file}")
        source_hash = sha256(source_file)
        if destination_file.exists():
            if not allow_existing:
                raise ValueError(f"refusing to overwrite existing backup member: {destination_file}")
            if sha256(destination_file) != source_hash:
                raise ValueError(f"existing backup member differs: {destination_file}")
        else:
            shutil.copy2(source_file, destination_file)
        if sha256(destination_file) != source_hash:
            raise ValueError(f"backup readback differs: {destination_file}")
        hashes[name] = source_hash
    return {"file_count": len(expected_names), "files": hashes}


def complete_backups(
    openssl: str,
    security: str,
    account: str,
    output: Path,
    primary_target: Path,
    secondary_target: Path,
    *,
    allow_existing: bool,
) -> dict[str, object]:
    manifest_path = output / "key-manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"key manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "phase4_formal_release_keys_encrypted":
        raise ValueError("local key manifest has an unexpected classification")
    services = manifest["keychain"]["services"]
    if manifest["keychain"]["account"] != account:
        raise ValueError("Keychain account differs from the key manifest")
    passwords = {
        name: keychain_read(security, account, service)
        for name, service in services.items()
    }
    private_files = {
        "verity": output / "leo-verity-v1-private.encrypted.pem",
        "boot": output / "leo-boot-v1-private.encrypted.pem",
    }
    for name, private_file in private_files.items():
        run([
            openssl, "pkey", "-in", str(private_file),
            "-passin", "env:LEO_KEY_PASSPHRASE", "-noout",
        ], environment=openssl_environment(passwords[name]))

    expected_names = sorted(manifest["files"]) + ["key-manifest.json"]
    primary_report = copy_and_verify(
        output, primary_target, expected_names, allow_existing=allow_existing
    )
    secondary_report = copy_and_verify(
        output, secondary_target, expected_names, allow_existing=allow_existing
    )
    ceremony = {
        **manifest,
        "local_output": str(output),
        "backup_readback": {"primary": primary_report, "secondary": secondary_report},
    }
    (output / "ceremony-report.json").write_text(
        json.dumps(ceremony, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-volume", required=True, type=Path)
    parser.add_argument("--secondary-volume", required=True, type=Path)
    parser.add_argument("--local-output", required=True, type=Path)
    parser.add_argument("--backup-parent", default="Leo-Audio-OS-Phase4-Key-Backup-v1")
    parser.add_argument("--account", default=getpass.getuser())
    parser.add_argument("--resume-existing", action="store_true")
    args = parser.parse_args()

    openssl = shutil.which("openssl")
    security = shutil.which("security")
    diskutil = shutil.which("diskutil")
    if not openssl or not security or not diskutil:
        parser.error("openssl, security, and diskutil are required")

    primary = args.primary_volume.resolve()
    secondary = args.secondary_volume.resolve()
    output = args.local_output.resolve()
    try:
        primary_info = media_info(diskutil, primary)
        secondary_info = media_info(diskutil, secondary)
        if primary_info["ParentWholeDisk"] == secondary_info["ParentWholeDisk"]:
            raise ValueError("backup targets are not independent physical disks")
        primary_target = primary / args.backup_parent / BACKUP_NAME
        secondary_target = secondary / args.backup_parent / BACKUP_NAME
        if output.exists():
            if not args.resume_existing:
                raise ValueError(f"refusing to overwrite local key directory: {output}")
            manifest = complete_backups(
                openssl, security, args.account, output, primary_target, secondary_target,
                allow_existing=True,
            )
            public_result = {
                "schema": 1,
                "classification": "phase4_formal_release_keys_generated",
                "verity_mincrypt_sha256": manifest["public_identity"]["verity_mincrypt_sha256"],
                "boot_certificate_der_sha256": manifest["public_identity"]["boot_certificate_der_sha256"],
                "independent_physical_disks": True,
                "initial_copy_readback_verified": True,
                "remount_readback_verified": False,
                "device_write_authorized": False,
            }
            print(json.dumps(public_result, ensure_ascii=False, indent=2))
            return 0
        if primary_target.exists() or secondary_target.exists():
            raise ValueError("one or more release-key backup targets already exist")

        services = {
            "verity": "leo-audio-os.phase4.leo-verity-v1",
            "boot": "leo-audio-os.phase4.leo-boot-v1",
        }
        for service in services.values():
            if keychain_exists(security, args.account, service):
                raise ValueError(f"Keychain item already exists: {service}")

        output.mkdir(parents=True, mode=0o700)
        os.chmod(output, 0o700)
        passwords = {name: secrets.token_hex(32) for name in services}
        keychain_add(
            security, args.account, services["verity"], "Leo Audio OS verity v1", passwords["verity"]
        )
        keychain_add(
            security, args.account, services["boot"], "Leo Audio OS boot v1", passwords["boot"]
        )
        for name, service in services.items():
            if keychain_read(security, args.account, service) != passwords[name]:
                raise ValueError(f"Keychain readback failed: {service}")

        verity_private = output / "leo-verity-v1-private.encrypted.pem"
        verity_spki = output / "leo-verity-v1-public.spki.der"
        verity_public = output / "leo-verity-v1-public.pem"
        verity_mincrypt = output / "verity_key"
        boot_private = output / "leo-boot-v1-private.encrypted.pem"
        boot_public = output / "leo-boot-v1-public.pem"
        boot_certificate = output / "leo-boot-v1-certificate.pem"
        boot_certificate_der = output / "leo-boot-v1-certificate.der"

        encrypted_rsa(openssl, verity_private, passwords["verity"])
        run([
            openssl, "pkey", "-in", str(verity_private),
            "-passin", "env:LEO_KEY_PASSPHRASE", "-pubout", "-outform", "DER",
            "-out", str(verity_spki),
        ], environment=openssl_environment(passwords["verity"]))
        spki = verity_spki.read_bytes()
        modulus, exponent = parse_spki_rsa(spki)
        verity_public.write_bytes(public_pem(spki))
        verity_mincrypt.write_bytes(mincrypt_key(modulus, exponent))

        encrypted_rsa(openssl, boot_private, passwords["boot"])
        run([
            openssl, "pkey", "-in", str(boot_private),
            "-passin", "env:LEO_KEY_PASSPHRASE", "-pubout", "-out", str(boot_public),
        ], environment=openssl_environment(passwords["boot"]))
        run([
            openssl, "req", "-new", "-x509", "-sha256", "-key", str(boot_private),
            "-passin", "env:LEO_KEY_PASSPHRASE",
            "-subj", "/CN=Leo Audio OS Boot v1/", "-days", "7300",
            "-set_serial", "0x4c454f10", "-out", str(boot_certificate),
        ], environment=openssl_environment(passwords["boot"]))
        run([
            openssl, "x509", "-in", str(boot_certificate), "-outform", "DER",
            "-out", str(boot_certificate_der),
        ])

        file_manifest = {
            path.name: {"size": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(output.iterdir()) if path.is_file()
        }
        manifest = {
            "schema": 1,
            "classification": "phase4_formal_release_keys_encrypted",
            "key_ids": {"verity": "leo-verity-v1", "boot": "leo-boot-v1"},
            "algorithms": {
                "verity": "RSA-2048 SHA256withRSA PKCS1 v1.5",
                "boot": "RSA-2048 Android BootSignature v1 SHA256withRSA /boot",
                "private_key_encryption": "PKCS8 PEM AES-256-CBC",
            },
            "public_identity": {
                "verity_mincrypt_sha256": sha256(verity_mincrypt),
                "verity_spki_sha256": sha256(verity_spki),
                "boot_certificate_der_sha256": sha256(boot_certificate_der),
            },
            "keychain": {
                "account": args.account,
                "services": services,
                "immediate_readback_verified": True,
                "passphrases_exported_to_usb": False,
            },
            "media": {
                "primary": {
                    "volume_uuid": primary_info["VolumeUUID"],
                    "whole_disk": primary_info["ParentWholeDisk"],
                },
                "secondary": {
                    "volume_uuid": secondary_info["VolumeUUID"],
                    "whole_disk": secondary_info["ParentWholeDisk"],
                },
                "independent_physical_disks": True,
                "initial_copy_readback_verified": True,
                "remount_readback_verified": False,
            },
            "files": file_manifest,
            "device_write_authorized": False,
        }
        manifest_path = output / "key-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        manifest = complete_backups(
            openssl, security, args.account, output, primary_target, secondary_target,
            allow_existing=False,
        )
    except (OSError, ValueError, KeyError, plistlib.InvalidFileException, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    public_result = {
        "schema": 1,
        "classification": "phase4_formal_release_keys_generated",
        "verity_mincrypt_sha256": manifest["public_identity"]["verity_mincrypt_sha256"],
        "boot_certificate_der_sha256": manifest["public_identity"]["boot_certificate_der_sha256"],
        "independent_physical_disks": True,
        "initial_copy_readback_verified": True,
        "remount_readback_verified": False,
        "device_write_authorized": False,
    }
    print(json.dumps(public_result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
