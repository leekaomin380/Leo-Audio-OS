#!/usr/bin/env python3
"""Verify one complete Phase 4 system/boot/recovery artifact tuple.

The verifier is offline and cannot authorize a flash.  Development-probe
manifests may pass artifact integrity while remaining explicitly not ready for
device write.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import struct
import subprocess
import sys
from pathlib import Path


CHUNK = 8 * 1024 * 1024


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def align(value: int, boundary: int) -> int:
    return (value + boundary - 1) // boundary * boundary


def cpio_payload(archive: bytes, wanted: str) -> bytes:
    cursor = 0
    matches: list[bytes] = []
    while True:
        if cursor + 110 > len(archive):
            raise ValueError("truncated newc archive")
        header = archive[cursor:cursor + 110]
        if header[:6] not in (b"070701", b"070702"):
            raise ValueError("unsupported cpio format")
        fields = [int(header[6 + index * 8:14 + index * 8], 16) for index in range(13)]
        size = fields[6]
        name_size = fields[11]
        name_start = cursor + 110
        name_end = name_start + name_size
        if name_end > len(archive) or archive[name_end - 1] != 0:
            raise ValueError("invalid cpio name")
        name = archive[name_start:name_end - 1].decode("utf-8")
        data_start = align(name_end, 4)
        data_end = data_start + size
        if data_end > len(archive):
            raise ValueError("invalid cpio payload boundary")
        if name in (wanted, f"./{wanted}"):
            matches.append(archive[data_start:data_end])
        cursor = align(data_end, 4)
        if name == "TRAILER!!!":
            break
    if len(matches) != 1:
        raise ValueError(f"expected one {wanted!r} cpio entry, found {len(matches)}")
    return matches[0]


def boot_verity_key(path: Path) -> bytes:
    image = path.read_bytes()
    if len(image) < 1632 or image[:8] != b"ANDROID!":
        raise ValueError("project boot is not a legacy Android boot image")
    fields = struct.unpack_from("<10I", image, 8)
    kernel_size, _, ramdisk_size, _, _, _, _, page_size, _, _ = fields
    ramdisk_offset = align(page_size + kernel_size, page_size)
    ramdisk = image[ramdisk_offset:ramdisk_offset + ramdisk_size]
    return cpio_payload(gzip.decompress(ramdisk), "verity_key")


def run(command: list[str]) -> None:
    subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--gate3-ext4", required=True, type=Path)
    parser.add_argument("--system", required=True, type=Path)
    parser.add_argument("--sparse", required=True, type=Path)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--verity-key", required=True, type=Path)
    parser.add_argument("--boot-certificate", required=True, type=Path)
    parser.add_argument("--stock-boot", required=True, type=Path)
    parser.add_argument("--stock-recovery", required=True, type=Path)
    parser.add_argument("--development-boot-fallback", required=True, type=Path)
    parser.add_argument("--system-report", required=True, type=Path)
    parser.add_argument("--boot-report", required=True, type=Path)
    parser.add_argument("--sparse-report", required=True, type=Path)
    parser.add_argument("--fault-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    named_paths = {
        "gate3_ext4": args.gate3_ext4,
        "system_raw": args.system,
        "system_sparse": args.sparse,
        "project_boot": args.boot,
        "verity_public_key": args.verity_key,
        "boot_certificate": args.boot_certificate,
        "stock_boot": args.stock_boot,
        "stock_recovery": args.stock_recovery,
        "development_boot_fallback": args.development_boot_fallback,
    }
    manifest_path = args.manifest.resolve()
    report_paths = [
        args.system_report, args.boot_report, args.sparse_report, args.fault_report,
    ]
    if not manifest_path.is_file() or not all(path.resolve().is_file() for path in report_paths):
        parser.error("manifest or evidence report is missing")
    resolved = {name: path.resolve() for name, path in named_paths.items()}
    if not all(path.is_file() for path in resolved.values()):
        parser.error("one or more release-set artifacts are missing")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts = manifest["artifacts"]
        observed: dict[str, dict[str, object]] = {}
        for name, path in resolved.items():
            expected = artifacts[name]
            actual_size = path.stat().st_size
            require(actual_size == expected["size"], f"{name} size mismatch")
        for name, path in resolved.items():
            expected = artifacts[name]
            actual_hash = sha256(path)
            actual_size = path.stat().st_size
            require(actual_hash == expected["sha256"], f"{name} SHA-256 mismatch")
            observed[name] = {"size": actual_size, "sha256": actual_hash}

        system_report = json.loads(args.system_report.resolve().read_text(encoding="utf-8"))
        boot_report = json.loads(args.boot_report.resolve().read_text(encoding="utf-8"))
        sparse_report = json.loads(args.sparse_report.resolve().read_text(encoding="utf-8"))
        fault_report = json.loads(args.fault_report.resolve().read_text(encoding="utf-8"))
        require(system_report["input_sha256"] == artifacts["system_raw"]["sha256"], "system report mismatch")
        require(system_report["metadata"]["signature_valid"], "system metadata signature is not valid")
        require(system_report["hash_tree"]["verification"]["tree_bytes_match"], "system tree is not exact")
        require(boot_report["input_sha256"] == artifacts["project_boot"]["sha256"], "boot report mismatch")
        require(boot_report["target"] == "/boot" and boot_report["signature_valid"], "boot signature gate failed")
        require(
            boot_report["certificate_der_sha256"] == artifacts["boot_certificate"]["sha256"],
            "boot certificate binding mismatch",
        )
        require(sparse_report["raw"]["sha256"] == artifacts["system_raw"]["sha256"], "sparse raw binding mismatch")
        require(sparse_report["sparse"]["sha256"] == artifacts["system_sparse"]["sha256"], "sparse hash binding mismatch")
        require(sparse_report["sparse"]["pair_identical"], "sparse pair is not reproducible")
        require(sparse_report["roundtrip"]["matches_raw"], "sparse round trip failed")
        require(fault_report["all_faults_rejected"] and fault_report["fault_count"] >= 8, "fault gate failed")
        double_build = manifest["double_build"]
        require(double_build["system_raw_identical"], "system raw double-build proof is missing")
        require(double_build["project_boot_identical"], "project boot double-build proof is missing")
        require(double_build["system_sparse_identical"], "system sparse double-build proof is missing")

        key = resolved["verity_public_key"].read_bytes()
        embedded_key = boot_verity_key(resolved["project_boot"])
        require(key == embedded_key, "project boot does not embed the paired system verity key")
        require(sha256(resolved["verity_public_key"]) == system_report["verity_key"]["sha256"], "system key mismatch")

        system_verifier = Path(__file__).with_name("inspect-legacy-system-verity.py")
        boot_verifier = Path(__file__).with_name("inspect-legacy-boot-signature.py")
        run([sys.executable, str(system_verifier), "--system", str(resolved["system_raw"]), "--verity-key", str(resolved["verity_public_key"])])
        run([sys.executable, str(boot_verifier), "--boot", str(resolved["project_boot"]), "--expected-target", "/boot"])
        run([sys.executable, str(boot_verifier), "--boot", str(resolved["stock_boot"]), "--expected-target", "/boot"])
        run([sys.executable, str(boot_verifier), "--boot", str(resolved["stock_recovery"]), "--expected-target", "/recovery"])

        classification = manifest["classification"]
        ceremony = manifest.get("key_ceremony", {})
        release_key_gate = bool(
            ceremony.get("formal_release_keys")
            and ceremony.get("independent_offline_copies", 0) >= 2
            and ceremony.get("recovery_readback_verified")
        )
        device_write_ready = bool(
            classification == "phase4_release_set"
            and manifest.get("device_write_authorized")
            and release_key_gate
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    report = {
        "schema": 1,
        "classification": "phase4-release-set-verification",
        "artifact_integrity_valid": True,
        "pair_cryptographically_valid": True,
        "rollback_artifacts_present": True,
        "release_key_gate": release_key_gate,
        "device_write_ready": device_write_ready,
        "device_write_authorized_by_verifier": False,
        "manifest_classification": classification,
        "artifacts": observed,
    }
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
