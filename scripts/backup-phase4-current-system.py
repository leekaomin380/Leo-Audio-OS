#!/usr/bin/env python3
"""Read the current leo system block device into two new external-media copies.

The script never writes to the phone and refuses to overwrite any destination.
Both copies are streamed in one pass, fsynced, then independently read back and
hashed before a manifest is accepted.  Failed partial files are deliberately
left in place for inspection rather than silently deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


CHUNK = 4 * 1024 * 1024
REPORT_INTERVAL = 256 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def volume_info(diskutil: str, volume: Path, expected_uuid: str) -> dict[str, object]:
    info = plistlib.loads(run([diskutil, "info", "-plist", str(volume)]).stdout)
    if info.get("Internal") or not info.get("RemovableMediaOrExternalDevice"):
        raise ValueError(f"destination is not external removable media: {volume}")
    if info.get("VolumeUUID") != expected_uuid:
        raise ValueError(f"volume UUID mismatch: {volume}")
    if info.get("FilesystemType") != "exfat" or not info.get("WritableVolume"):
        raise ValueError(f"destination is not writable ExFAT: {volume}")
    if Path(str(info.get("MountPoint", ""))).resolve() != volume.resolve():
        raise ValueError(f"mount identity changed: {volume}")
    return info


def adb_gate(adb: str) -> None:
    lines = run([adb, "devices"]).stdout.decode("utf-8").splitlines()[1:]
    devices = [line for line in lines if line.strip() and line.split()[1] == "device"]
    if len(devices) != 1:
        raise ValueError(f"expected one authorized ADB device, found {len(devices)}")
    product = run([adb, "shell", "getprop", "ro.product.device"]).stdout.decode().strip()
    completed = run([adb, "shell", "getprop", "sys.boot_completed"]).stdout.decode().strip()
    root = run([adb, "shell", "su", "-c", "id"]).stdout.decode("utf-8")
    if product != "leo" or completed != "1" or "uid=0(root)" not in root:
        raise ValueError("ADB identity, boot-complete, or root gate failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary-volume", required=True, type=Path)
    parser.add_argument("--primary-uuid", required=True)
    parser.add_argument("--secondary-volume", required=True, type=Path)
    parser.add_argument("--secondary-uuid", required=True)
    parser.add_argument("--backup-parent", default="Leo-Audio-OS-Phase4-Device-Backup-v1")
    parser.add_argument("--backup-id", required=True)
    parser.add_argument("--expected-size", required=True, type=int)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--stock-sha256", required=True)
    parser.add_argument("--local-manifest", required=True, type=Path)
    args = parser.parse_args()

    adb = shutil.which("adb")
    diskutil = shutil.which("diskutil")
    if not adb or not diskutil:
        parser.error("adb and diskutil are required")

    primary = args.primary_volume.resolve()
    secondary = args.secondary_volume.resolve()
    expected_hash = args.expected_sha256.lower()
    try:
        adb_gate(adb)
        primary_info = volume_info(diskutil, primary, args.primary_uuid)
        secondary_info = volume_info(diskutil, secondary, args.secondary_uuid)
        if primary_info["ParentWholeDisk"] == secondary_info["ParentWholeDisk"]:
            raise ValueError("backup destinations are not independent physical disks")
        required_free = args.expected_size + 512 * 1024 * 1024
        for volume in (primary, secondary):
            if shutil.disk_usage(volume).free < required_free:
                raise ValueError(f"insufficient free space on {volume}")

        roots = [
            volume / args.backup_parent / args.backup_id
            for volume in (primary, secondary)
        ]
        for root in roots:
            if root.exists():
                raise ValueError(f"refusing to overwrite existing backup directory: {root}")
            root.mkdir(parents=True)
        final_paths = [root / "current-system.partition.raw" for root in roots]
        partial_paths = [root / "current-system.partition.raw.partial" for root in roots]

        command = [
            adb, "exec-out", "su", "-c",
            "/system/xbin/busybox cat /dev/block/bootdevice/by-name/system",
        ]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if process.stdout is None or process.stderr is None:
            raise ValueError("failed to establish ADB stream")
        digest = hashlib.sha256()
        written = 0
        next_report = REPORT_INTERVAL
        handles = [path.open("xb") for path in partial_paths]
        try:
            while block := process.stdout.read(CHUNK):
                written += len(block)
                if written > args.expected_size:
                    raise ValueError("device stream exceeds expected system partition size")
                digest.update(block)
                for handle in handles:
                    handle.write(block)
                if written >= next_report:
                    print(f"STREAMED_BYTES={written}", flush=True)
                    next_report += REPORT_INTERVAL
            for handle in handles:
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            for handle in handles:
                handle.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace").strip()
        return_code = process.wait()
        if return_code != 0:
            raise ValueError(f"ADB block stream failed with exit {return_code}: {stderr}")
        observed_hash = digest.hexdigest()
        if written != args.expected_size or observed_hash != expected_hash:
            raise ValueError(
                f"stream identity mismatch: size={written}, sha256={observed_hash}"
            )
        for partial, final in zip(partial_paths, final_paths):
            if final.exists():
                raise ValueError(f"refusing to overwrite final backup: {final}")
            partial.rename(final)

        readback = []
        for final in final_paths:
            observed = sha256(final)
            if final.stat().st_size != args.expected_size or observed != expected_hash:
                raise ValueError(f"physical-media readback mismatch: {final}")
            readback.append({"size": final.stat().st_size, "sha256": observed})
            print(f"READBACK_PASS={final.parent}", flush=True)

        manifest = {
            "schema": 1,
            "classification": "phase4_current_system_dual_media_backup",
            "device": "Xiaomi Mi Note Pro / leo",
            "device_serial_recorded": False,
            "source": "/dev/block/bootdevice/by-name/system",
            "size": args.expected_size,
            "sha256": expected_hash,
            "differs_from_stock": expected_hash != args.stock_sha256.lower(),
            "stock_sha256": args.stock_sha256.lower(),
            "copies": {
                "primary": {
                    "volume_uuid": args.primary_uuid,
                    "whole_disk_at_backup": primary_info["ParentWholeDisk"],
                    **readback[0],
                },
                "secondary": {
                    "volume_uuid": args.secondary_uuid,
                    "whole_disk_at_backup": secondary_info["ParentWholeDisk"],
                    **readback[1],
                },
            },
            "independent_physical_disks": True,
            "stream_hash_verified": True,
            "physical_readback_verified": True,
            "phone_write_performed": False,
            "device_write_authorized": False,
        }
        encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        local_manifest = args.local_manifest.resolve()
        local_manifest.parent.mkdir(parents=True, exist_ok=True)
        if local_manifest.exists():
            raise ValueError(f"refusing to overwrite local manifest: {local_manifest}")
        local_manifest.write_text(encoded, encoding="utf-8")
        for root in roots:
            manifest_path = root / "manifest.json"
            with manifest_path.open("x", encoding="utf-8") as output:
                output.write(encoded)
            if sha256(manifest_path) != sha256(local_manifest):
                raise ValueError(f"manifest readback mismatch: {manifest_path}")
    except (
        OSError, ValueError, KeyError, IndexError, plistlib.InvalidFileException,
        subprocess.CalledProcessError,
    ) as error:
        parser.error(str(error))

    print(json.dumps({
        "classification": manifest["classification"],
        "size": manifest["size"],
        "sha256": manifest["sha256"],
        "independent_physical_disks": True,
        "physical_readback_verified": True,
        "phone_write_performed": False,
        "device_write_authorized": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
