#!/usr/bin/env python3
"""Append only the contract-approved Gate 3 overlay to Gate 2 semantics."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


EPOCH_NS = 1230739200 * 1_000_000_000
LABEL = "u:object_r:system_file:s0"
EXPECTED_PATHS = ("/app/LeoShell", "/app/LeoShell/LeoShell.apk")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def entry(path: str, manifest_entry: dict[str, object]) -> dict[str, object]:
    item: dict[str, object] = {
        "gid": 0,
        "inode": 0,
        "mode_octal": manifest_entry["mode_octal"],
        "mtime_ns": EPOCH_NS,
        "nlink": 2 if manifest_entry["type"] == "directory" else 1,
        "path_b64": base64.b64encode(path.encode()).decode(),
        "path_utf8": path,
        "selinux_label": LABEL,
        "type": manifest_entry["type"],
        "uid": 0,
        "xattrs": {"security.selinux": base64.b64encode((LABEL + "\0").encode()).decode()},
    }
    if item["type"] == "regular":
        item["content_sha256"] = manifest_entry["content_sha256"]
        item["size"] = manifest_entry["size_bytes"]
    else:
        # e2fsdroid materializes the new ext4 directory as one 4096-byte
        # directory block.  Carry that observable semantic field into the
        # expected manifest so candidate auditing is exact rather than
        # treating a missing field as an implicit wildcard.
        item["size"] = 4096
    return item


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-entries", required=True, type=Path)
    parser.add_argument("--overlay-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    base = args.base_entries.resolve()
    overlay_dir = args.overlay_dir.resolve()
    output = args.output.resolve()
    manifest_path = overlay_dir / "overlay-manifest.json"
    apk = overlay_dir / "tree/app/LeoShell/LeoShell.apk"
    if not base.is_file() or not manifest_path.is_file() or not apk.is_file():
        fail("base entries, overlay manifest and verified APK must all exist")
    if output.exists():
        fail(f"output already exists: {output}")

    base_bytes = base.read_bytes()
    records = [json.loads(line) for line in base_bytes.splitlines()]
    if len(records) != 3923:
        fail(f"Gate 2 base must contain 3923 entries, got {len(records)}")
    base_paths = [record["path_utf8"] for record in records]
    if base_paths != sorted(base_paths, key=lambda value: value.encode()):
        fail("base entries are not canonically byte-sorted")
    if any(path in base_paths for path in EXPECTED_PATHS):
        fail("Gate 2 base already contains a Gate 3 overlay path")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "development-unverified" or manifest.get("mtime_epoch") != 1230739200:
        fail("overlay classification or fixed mtime differs from contract")
    overlay_entries = manifest.get("entries")
    if not isinstance(overlay_entries, list) or [item.get("path") for item in overlay_entries] != list(EXPECTED_PATHS):
        fail("overlay manifest must contain exactly the two contract paths in order")
    expected_apk_hash = overlay_entries[1].get("content_sha256")
    if expected_apk_hash != sha256(apk):
        fail("overlay APK hash differs from its manifest")
    if overlay_entries[0].get("type") != "directory" or overlay_entries[1].get("type") != "regular":
        fail("overlay path types differ from contract")
    for item in overlay_entries:
        if item.get("uid") != 0 or item.get("gid") != 0 or item.get("selinux_label") != LABEL:
            fail("overlay ownership or SELinux label differs from contract")
    if overlay_entries[0].get("mode_octal") != "040755" or overlay_entries[1].get("mode_octal") != "100644":
        fail("overlay modes differ from contract")
    if overlay_entries[1].get("size_bytes") != apk.stat().st_size:
        fail("overlay APK size differs from its manifest")

    combined = records + [entry(path, item) for path, item in zip(EXPECTED_PATHS, overlay_entries)]
    combined.sort(key=lambda item: base64.b64decode(item["path_b64"], validate=True))
    encoded = b"".join(
        json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        for item in combined
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)
    report = {
        "schema": 1,
        "base_entries": len(records),
        "combined_entries": len(combined),
        "base_entries_sha256": hashlib.sha256(base_bytes).hexdigest(),
        "combined_entries_sha256": hashlib.sha256(encoded).hexdigest(),
        "allowed_added_paths": list(EXPECTED_PATHS),
        "unchanged_base_path_count": len(records),
        "overlay_apk_sha256": expected_apk_hash,
    }
    report_path = output.with_suffix(output.suffix + ".summary.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    print("OK: Gate 3 semantic input adds exactly the two approved paths")


if __name__ == "__main__":
    main()
