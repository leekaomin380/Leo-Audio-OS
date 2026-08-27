#!/usr/bin/env python3
"""Verify and inventory a MoKee recovery ZIP without expanding its images."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import zipfile


TEXT_EVIDENCE = {
    "META-INF/com/android/metadata",
    "META-INF/com/google/android/updater-script",
    "system.transfer.list",
    "system.patch.dat",
    "vendor.transfer.list",
    "vendor.patch.dat",
}


def digest(path: Path, algorithm: str) -> str:
    hasher = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("report_dir", type=Path)
    parser.add_argument("--expected-size", type=int)
    parser.add_argument("--expected-md5")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rom = args.rom.resolve()
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)

    actual_size = rom.stat().st_size
    actual_md5 = digest(rom, "md5")
    actual_sha256 = digest(rom, "sha256")
    size_ok = args.expected_size is None or actual_size == args.expected_size
    md5_ok = args.expected_md5 is None or actual_md5 == args.expected_md5.lower()

    top_level: dict[str, dict[str, int]] = {}
    rows: list[dict[str, object]] = []
    evidence: dict[str, str] = {}

    with zipfile.ZipFile(rom) as archive:
        first_bad_entry = archive.testzip()
        for item in archive.infolist():
            top = item.filename.split("/", 1)[0]
            summary = top_level.setdefault(top, {"entries": 0, "compressed": 0, "uncompressed": 0})
            summary["entries"] += 1
            summary["compressed"] += item.compress_size
            summary["uncompressed"] += item.file_size
            rows.append(
                {
                    "path": item.filename,
                    "compressed_bytes": item.compress_size,
                    "uncompressed_bytes": item.file_size,
                    "crc32": f"{item.CRC:08x}",
                    "compression": item.compress_type,
                }
            )
            if item.filename in TEXT_EVIDENCE and item.file_size <= 2 * 1024 * 1024:
                evidence[item.filename] = archive.read(item).decode("utf-8", errors="replace")

    rows.sort(key=lambda row: str(row["path"]))
    with (report_dir / "zip-inventory.tsv").open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys(), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    evidence_dir = report_dir / "zip-metadata"
    for name, content in evidence.items():
        target = evidence_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    large_entries = sorted(rows, key=lambda row: int(row["uncompressed_bytes"]), reverse=True)[:30]
    report = {
        "schema": 1,
        "rom": os.fspath(rom),
        "filename": rom.name,
        "size_bytes": actual_size,
        "expected_size_bytes": args.expected_size,
        "size_matches": size_ok,
        "md5": actual_md5,
        "expected_md5": args.expected_md5,
        "md5_matches": md5_ok,
        "sha256": actual_sha256,
        "zip_first_bad_entry": first_bad_entry,
        "zip_entry_count": len(rows),
        "zip_total_uncompressed_bytes": sum(int(row["uncompressed_bytes"]) for row in rows),
        "top_level": top_level,
        "large_entries": large_entries,
        "text_evidence_entries": sorted(evidence),
        "verification_passed": size_ok and md5_ok and first_bad_entry is None,
    }
    (report_dir / "rom-identity.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
