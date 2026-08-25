#!/usr/bin/env python3
"""Fail closed over the complete private Gate 3 static evidence set."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entries(path: Path) -> dict[str, dict[str, object]]:
    result = {item["path_utf8"]: item for item in map(json.loads, path.open(encoding="utf-8"))}
    return result


def superblock(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            result[key.strip()] = value.strip()
    return result


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--private-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    project = args.project.resolve()
    private = args.private_root.resolve()
    if args.output.exists():
        fail(f"output already exists: {args.output}")

    public = load(project / "manifests/gate3-candidate-v0.1.json")
    expected_apk = public["intentional_change"]["apk_sha256"]
    expected_raw = public["filesystem"]["raw_ext4_sha256"]
    apk = private / "apk-v3/LeoShell-0.3.0-gate3.1-home-release-1.apk"
    require(apk.stat().st_size == public["intentional_change"]["apk_size_bytes"], "APK size differs")
    require(sha256(apk) == expected_apk, "APK hash differs")
    require("signed_reproducible=true" in (private / "apk-v3/verification.txt").read_text(), "signed APK is not reproducible")
    require(load(private / "apk-v3/signed-provenance-v2.json").get("valid") is True, "APK provenance failed")

    overlay = load(private / "overlay-v2/overlay-manifest.json")
    require([item["path"] for item in overlay["entries"]] == ["/app/LeoShell", "/app/LeoShell/LeoShell.apk"], "overlay paths differ")
    require(overlay["source_apk_sha256"] == expected_apk, "overlay APK hash differs")
    semantic = load(private / "semantic-input-v3/entries.jsonl.summary.json")
    require(semantic["base_entries"] == 3923 and semantic["combined_entries"] == 3925, "semantic counts differ")
    require(semantic["overlay_apk_sha256"] == expected_apk, "semantic APK hash differs")
    metadata = load(private / "metadata-v3/metadata-summary.json")
    require(metadata["entries"] == metadata["fs_config_entries"] == metadata["selinux_rules"] == 3925, "metadata counts differ")
    require(metadata["source_entries_sha256"] == semantic["combined_entries_sha256"], "metadata source hash differs")
    require(load(private / "staging-v2/semantic-verification.json").get("staging_semantic_valid") is True, "staging semantics failed")
    require(load(private / "staging-v2/timestamp-verification.json").get("applied_entries") == 3925, "staging mtimes failed")
    require("lookup_count=3925" in (private / "selinux-lookup-v4/verification.txt").read_text(), "SELinux positive lookup count differs")
    require("negative_lookup_rejected=true" in (private / "selinux-negative-v2.txt").read_text(), "SELinux negative lookup did not reject")

    candidate_entries: dict[str, dict[str, object]] | None = None
    raw_hashes: list[str] = []
    for number in (3, 4):
        root = private / f"candidate-ext4-v{number}"
        raw = root / "system.ext4.raw"
        require(raw.stat().st_size == public["filesystem"]["raw_ext4_bytes"], f"candidate v{number} size differs")
        raw_hashes.append(sha256(raw))
        require("candidate_build_valid=true" in (root / "verification.txt").read_text(), f"candidate v{number} build failed")
        require("normalization_valid=true" in (root / "normalization/verification.txt").read_text(), f"candidate v{number} normalization failed")
        require(load(root / "semantic-comparison.json").get("valid") is True, f"candidate v{number} semantic comparison failed")
        require(load(root / "semantic-verification.json").get("audio_manifest_entries_verified") == 17, f"candidate v{number} audio closure failed")
        summary = load(root / "semantic/audit-summary.json")
        require(summary["entry_count"] == 3925 and summary["capability_entries"] == 5, f"candidate v{number} summary differs")
        current_entries = entries(root / "semantic/entries.jsonl")
        if candidate_entries is None:
            candidate_entries = current_entries
        else:
            require(current_entries == candidate_entries, "candidate semantic manifests differ")
    require(raw_hashes == [expected_raw, expected_raw], "candidate raw hashes differ")

    base_entries = entries(project / "resources/private/phase3-gate2/candidate-ext4-v5/semantic/entries.jsonl")
    assert candidate_entries is not None
    launcher = "/priv-app/MiuiHome/MiuiHome.apk"
    require(base_entries[launcher] == {**candidate_entries[launcher], "inode": base_entries[launcher]["inode"]}, "MIUI Launcher changed beyond inode allocation")
    require(candidate_entries[launcher]["content_sha256"] == public["semantic_evidence"]["miui_home_apk_sha256"], "MIUI Launcher hash differs")

    base_sb = superblock(project / "resources/private/phase3-gate2/candidate-ext4-v6/normalization/superblock.txt")
    gate3_sb = superblock(private / "candidate-ext4-v3/normalization/superblock.txt")
    invariant = ("Filesystem volume name", "Filesystem UUID", "Filesystem features", "Block count", "Block size", "Inode count", "Inode size", "Total journal blocks")
    for key in invariant:
        require(base_sb.get(key) == gate3_sb.get(key), f"superblock invariant changed: {key}")
    require(int(gate3_sb["Free blocks"]) - int(base_sb["Free blocks"]) == -9, "free block delta differs")
    require(int(gate3_sb["Free inodes"]) - int(base_sb["Free inodes"]) == -2, "free inode delta differs")

    container = load(private / "development-container-v2/gate2-development-container.json")
    require(container["prefix_matches_ext4"] and container["tail_is_zero_filled"] and container["raw_bytes_equal_after_sparse_roundtrip"], "development container gate failed")
    require(container["input_ext4_raw"]["sha256"] == expected_raw, "container ext4 prefix differs")
    require(container["partition_raw"]["sha256"] == public["development_container"]["partition_raw_sha256"], "partition hash differs")
    require(container["sparse_image"]["sha256"] == public["development_container"]["sparse_sha256"], "sparse hash differs")
    require(sha256(private / "development-container-v2/system.partition.raw") == public["development_container"]["partition_raw_sha256"], "partition file hash differs")
    require(sha256(private / "development-container-v2/system.img") == public["development_container"]["sparse_sha256"], "sparse file hash differs")
    require(sha256(private / "development-container-v2/system.partition.roundtrip.raw") == public["development_container"]["partition_raw_sha256"], "round-trip raw file hash differs")

    subprocess.run(["git", "-C", str(project), "diff", "--quiet", "phase3-gate2-v0.1", "--", "tools/gate2-builder", "scripts/build-gate2-ext4-candidate.sh", "scripts/normalize-gate2-ext4.sh"], check=True)
    for protected in (private / "development-container-v2/system.img", project / "keys/leo-shell-app-v1/leo-shell-app-v1.p12"):
        subprocess.run(["git", "-C", str(project), "check-ignore", "--quiet", str(protected)], check=True)
    tracked = subprocess.check_output(["git", "-C", str(project), "ls-files"], text=True).splitlines()
    forbidden = [path for path in tracked if path.startswith(("resources/private/", "keys/")) or Path(path).suffix.lower() in {".apk", ".img", ".jks", ".keystore", ".p12"}]
    require(not forbidden, f"private artifacts are tracked: {forbidden}")

    verdict = {
        "schema": 1,
        "valid": True,
        "classification": "development-unverified",
        "apk_sha256": expected_apk,
        "candidate_raw_sha256": expected_raw,
        "candidate_count": 2,
        "semantic_entries": 3925,
        "audio_entries_verified": 17,
        "private_material_tracked": False,
        "device_write_authorized": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
