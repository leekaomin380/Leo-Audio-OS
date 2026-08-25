#!/usr/bin/env python3
"""Verify Phase 4 release-key backups after both USB media were remounted.

The verifier is read-only with respect to both USB volumes.  It checks the
recorded volume identities, physical-disk independence, every manifest member,
and local encrypted-key recovery through the macOS login Keychain.  It never
prints a passphrase or private-key content.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(4 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def run(
    command: list[str], *, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        check=True,
    )


def volume_info(diskutil: str, volume: Path) -> dict[str, object]:
    info = plistlib.loads(run([diskutil, "info", "-plist", str(volume)]).stdout)
    if info.get("Internal") or not info.get("RemovableMediaOrExternalDevice"):
        raise ValueError(f"volume is not external removable media: {volume}")
    if info.get("FilesystemType") != "exfat":
        raise ValueError(f"volume is not the expected ExFAT filesystem: {volume}")
    if Path(str(info.get("MountPoint", ""))).resolve() != volume.resolve():
        raise ValueError(f"mount point changed during verification: {volume}")
    if not info.get("ParentWholeDisk") or not info.get("VolumeUUID"):
        raise ValueError(f"volume identity is incomplete: {volume}")
    return info


def keychain_read(security: str, account: str, service: str) -> str:
    return run([
        security, "find-generic-password", "-a", account, "-s", service, "-w",
    ]).stdout.decode("utf-8").rstrip("\n")


def verify_backup(
    local: Path, backup: Path, expected: dict[str, dict[str, object]]
) -> dict[str, object]:
    names = sorted(expected) + ["key-manifest.json"]
    files: dict[str, dict[str, object]] = {}
    for name in names:
        local_file = local / name
        backup_file = backup / name
        if not local_file.is_file() or not backup_file.is_file():
            raise ValueError(f"backup member is missing: {backup_file}")
        local_hash = sha256(local_file)
        backup_hash = sha256(backup_file)
        if name != "key-manifest.json":
            member = expected[name]
            if local_file.stat().st_size != member["size"] or local_hash != member["sha256"]:
                raise ValueError(f"local key member differs from manifest: {local_file}")
        if backup_file.stat().st_size != local_file.stat().st_size or backup_hash != local_hash:
            raise ValueError(f"backup readback differs from local member: {backup_file}")
        files[name] = {"size": backup_file.stat().st_size, "sha256": backup_hash}
    return {"member_count": len(names), "all_members_match": True, "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-keys", required=True, type=Path)
    parser.add_argument("--primary-volume", required=True, type=Path)
    parser.add_argument("--secondary-volume", required=True, type=Path)
    parser.add_argument("--backup-parent", default="Leo-Audio-OS-Phase4-Key-Backup-v1")
    parser.add_argument("--account", default=getpass.getuser())
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    diskutil = shutil.which("diskutil")
    security = shutil.which("security")
    openssl = shutil.which("openssl")
    if not diskutil or not security or not openssl:
        parser.error("diskutil, security, and openssl are required")

    local = args.local_keys.resolve()
    manifest_path = local / "key-manifest.json"
    primary = args.primary_volume.resolve()
    secondary = args.secondary_volume.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("classification") != "phase4_formal_release_keys_encrypted":
            raise ValueError("unexpected release-key manifest classification")
        if manifest.get("device_write_authorized") is not False:
            raise ValueError("key manifest must not authorize device writes")
        primary_info = volume_info(diskutil, primary)
        secondary_info = volume_info(diskutil, secondary)
        recorded = manifest["media"]
        for role, info in (("primary", primary_info), ("secondary", secondary_info)):
            if info["VolumeUUID"] != recorded[role]["volume_uuid"]:
                raise ValueError(f"{role} volume UUID differs from the key ceremony")
        if primary_info["ParentWholeDisk"] == secondary_info["ParentWholeDisk"]:
            raise ValueError("backup targets resolve to the same physical disk")

        backup_name = "release-keys-v1"
        primary_report = verify_backup(
            local, primary / args.backup_parent / backup_name, manifest["files"]
        )
        secondary_report = verify_backup(
            local, secondary / args.backup_parent / backup_name, manifest["files"]
        )

        decrypt: dict[str, bool] = {}
        private_files = {
            "verity": local / "leo-verity-v1-private.encrypted.pem",
            "boot": local / "leo-boot-v1-private.encrypted.pem",
        }
        if manifest["keychain"]["account"] != args.account:
            raise ValueError("Keychain account differs from key manifest")
        for role, private_key in private_files.items():
            password = keychain_read(
                security, args.account, manifest["keychain"]["services"][role]
            )
            environment = dict(os.environ)
            environment["LEO_KEY_PASSPHRASE"] = password
            run([
                openssl, "pkey", "-in", str(private_key),
                "-passin", "env:LEO_KEY_PASSPHRASE", "-noout",
            ], environment=environment)
            password = ""
            environment.pop("LEO_KEY_PASSPHRASE", None)
            decrypt[role] = True

        report = {
            "schema": 1,
            "classification": "phase4_release_key_remount_verification",
            "key_manifest_sha256": sha256(manifest_path),
            "key_ids": manifest["key_ids"],
            "volumes": {
                "primary": {
                    "volume_uuid": primary_info["VolumeUUID"],
                    "whole_disk": primary_info["ParentWholeDisk"],
                    "readback": primary_report,
                },
                "secondary": {
                    "volume_uuid": secondary_info["VolumeUUID"],
                    "whole_disk": secondary_info["ParentWholeDisk"],
                    "readback": secondary_report,
                },
            },
            "independent_physical_disks": True,
            "all_expected_members_match": True,
            "keychain_decrypt_verified": decrypt,
            "remount_readback_verified": True,
            "device_write_authorized": False,
        }
    except (
        OSError, ValueError, KeyError, TypeError, json.JSONDecodeError,
        plistlib.InvalidFileException, subprocess.CalledProcessError,
    ) as error:
        parser.error(str(error))

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "classification": report["classification"],
        "independent_physical_disks": True,
        "all_expected_members_match": True,
        "keychain_decrypt_verified": decrypt,
        "remount_readback_verified": True,
        "device_write_authorized": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
