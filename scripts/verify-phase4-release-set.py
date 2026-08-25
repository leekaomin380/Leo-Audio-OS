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
import shutil
import struct
import subprocess
import sys
import tempfile
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
    parser.add_argument("--stock-system-sparse", type=Path)
    parser.add_argument("--stock-system-raw", type=Path)
    parser.add_argument("--stock-system-report", type=Path)
    parser.add_argument("--development-boot-fallback", required=True, type=Path)
    parser.add_argument("--system-report", required=True, type=Path)
    parser.add_argument("--boot-report", required=True, type=Path)
    parser.add_argument("--sparse-report", required=True, type=Path)
    parser.add_argument("--fault-report", required=True, type=Path)
    parser.add_argument("--key-manifest", type=Path)
    parser.add_argument("--remount-report", type=Path)
    parser.add_argument("--system-build-report-a", type=Path)
    parser.add_argument("--system-build-report-b", type=Path)
    parser.add_argument("--boot-build-report-a", type=Path)
    parser.add_argument("--boot-build-report-b", type=Path)
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
    if args.stock_system_sparse:
        named_paths["stock_system_sparse"] = args.stock_system_sparse
    if args.stock_system_raw:
        named_paths["stock_system_raw"] = args.stock_system_raw
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
        classification = manifest["classification"]
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

        formal_evidence_valid = False
        if classification == "phase4_release_set":
            formal_options = {
                "key_manifest": args.key_manifest,
                "remount_report": args.remount_report,
                "system_build_report_a": args.system_build_report_a,
                "system_build_report_b": args.system_build_report_b,
                "boot_build_report_a": args.boot_build_report_a,
                "boot_build_report_b": args.boot_build_report_b,
                "system_verification": args.system_report,
                "boot_verification": args.boot_report,
                "sparse_report": args.sparse_report,
                "pair_fault_report": args.fault_report,
                "stock_system_verification": args.stock_system_report,
            }
            require(args.stock_system_sparse is not None, "formal stock system sparse is missing")
            require(args.stock_system_raw is not None, "formal stock system raw is missing")
            require(all(formal_options.values()), "formal release evidence path is missing")
            formal_paths = {name: path.resolve() for name, path in formal_options.items() if path}
            require(all(path.is_file() for path in formal_paths.values()), "formal release evidence file is missing")
            evidence = manifest["evidence"]
            for name, path in formal_paths.items():
                expected = evidence[name]
                require(path.stat().st_size == expected["size"], f"{name} evidence size mismatch")
                require(sha256(path) == expected["sha256"], f"{name} evidence SHA-256 mismatch")

            key_manifest = json.loads(formal_paths["key_manifest"].read_text(encoding="utf-8"))
            remount_report = json.loads(formal_paths["remount_report"].read_text(encoding="utf-8"))
            require(
                key_manifest.get("classification") == "phase4_formal_release_keys_encrypted",
                "formal key manifest classification mismatch",
            )
            require(key_manifest.get("device_write_authorized") is False, "key manifest authorizes writes")
            require(
                key_manifest["public_identity"]["verity_mincrypt_sha256"]
                == artifacts["verity_public_key"]["sha256"],
                "key manifest verity identity mismatch",
            )
            require(
                key_manifest["public_identity"]["boot_certificate_der_sha256"]
                == artifacts["boot_certificate"]["sha256"],
                "key manifest boot identity mismatch",
            )
            require(
                remount_report.get("classification") == "phase4_release_key_remount_verification",
                "release-key remount report classification mismatch",
            )
            require(
                remount_report.get("key_manifest_sha256") == sha256(formal_paths["key_manifest"]),
                "remount report is not bound to the formal key manifest",
            )
            require(
                all((
                    remount_report.get("independent_physical_disks"),
                    remount_report.get("all_expected_members_match"),
                    remount_report.get("remount_readback_verified"),
                    remount_report.get("keychain_decrypt_verified", {}).get("verity"),
                    remount_report.get("keychain_decrypt_verified", {}).get("boot"),
                )),
                "formal release-key remount evidence is incomplete",
            )
            require(remount_report.get("device_write_authorized") is False, "remount report authorizes writes")

            system_builds = [
                json.loads(formal_paths[name].read_text(encoding="utf-8"))
                for name in ("system_build_report_a", "system_build_report_b")
            ]
            boot_builds = [
                json.loads(formal_paths[name].read_text(encoding="utf-8"))
                for name in ("boot_build_report_a", "boot_build_report_b")
            ]
            key_manifest_hash = sha256(formal_paths["key_manifest"])
            remount_hash = sha256(formal_paths["remount_report"])
            for report in system_builds:
                require(
                    report.get("classification") == "phase4-formal-release-candidate-system",
                    "system build report is not formal",
                )
                require(report.get("device_write_authorized") is False, "system builder authorizes writes")
                require(report["input"]["sha256"] == artifacts["gate3_ext4"]["sha256"], "system input mismatch")
                require(report["partition"]["sha256"] == artifacts["system_raw"]["sha256"], "system build mismatch")
                require(report["verity"]["metadata_signature_valid"], "system build signature gate failed")
                require(report["formal_key_gate"]["key_manifest_sha256"] == key_manifest_hash, "system key gate mismatch")
                require(report["formal_key_gate"]["remount_report_sha256"] == remount_hash, "system remount gate mismatch")
            for report in boot_builds:
                require(
                    report.get("classification") == "phase4-formal-release-candidate-boot",
                    "boot build report is not formal",
                )
                require(report.get("device_write_authorized") is False, "boot builder authorizes writes")
                require(report["project"]["boot_sha256"] == artifacts["project_boot"]["sha256"], "boot build mismatch")
                require(report["project"]["verity_key_sha256"] == artifacts["verity_public_key"]["sha256"], "boot verity key mismatch")
                require(report["project"]["certificate_der_sha256"] == artifacts["boot_certificate"]["sha256"], "boot certificate mismatch")
                require(report["project"]["boot_signature_valid"], "boot build signature gate failed")
                require(report["formal_key_gate"]["key_manifest_sha256"] == key_manifest_hash, "boot key gate mismatch")
                require(report["formal_key_gate"]["remount_report_sha256"] == remount_hash, "boot remount gate mismatch")

            stock_system_report = json.loads(
                formal_paths["stock_system_verification"].read_text(encoding="utf-8")
            )
            require(
                stock_system_report["input_sha256"] == artifacts["stock_system_raw"]["sha256"],
                "stock system verification is not bound to rollback raw",
            )
            require(stock_system_report["metadata"]["signature_valid"], "stock system metadata signature failed")
            require(
                stock_system_report["hash_tree"]["verification"]["tree_bytes_match"],
                "stock system verity tree is not exact",
            )
            simg2img = shutil.which("simg2img")
            require(bool(simg2img), "simg2img is required for stock rollback verification")
            with tempfile.TemporaryDirectory(prefix="leo-stock-system-roundtrip-") as temporary:
                expanded = Path(temporary) / "stock-system.raw"
                run([str(simg2img), str(resolved["stock_system_sparse"]), str(expanded)])
                require(
                    expanded.stat().st_size == artifacts["stock_system_raw"]["size"]
                    and sha256(expanded) == artifacts["stock_system_raw"]["sha256"],
                    "stock system sparse does not expand to the bound rollback raw",
                )
            formal_evidence_valid = True

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

        ceremony = manifest.get("key_ceremony", {})
        release_key_gate = bool(
            ceremony.get("formal_release_keys")
            and ceremony.get("independent_offline_copies", 0) >= 2
            and ceremony.get("recovery_readback_verified")
            and formal_evidence_valid
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
        "formal_evidence_valid": formal_evidence_valid,
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
