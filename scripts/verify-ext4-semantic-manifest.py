#!/usr/bin/env python3
"""Validate a private direct-ext4 semantic manifest without reading file content."""

from __future__ import annotations

import argparse
import base64
import collections
import csv
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--audio-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--audio-output", type=Path)
    args = parser.parse_args()

    entries = [json.loads(line) for line in args.entries.read_text(encoding="utf-8").splitlines()]
    if not entries:
        fail("semantic manifest is empty")
    path_bytes: list[bytes] = []
    by_path: dict[str, dict[str, object]] = {}
    inodes: set[int] = set()
    for entry in entries:
        for required in ("path_b64", "path_utf8", "inode", "type", "mode_octal", "uid", "gid", "xattrs"):
            if required not in entry:
                fail(f"entry lacks required field: {required}")
        decoded = base64.b64decode(entry["path_b64"], validate=True)
        if decoded.decode("utf-8") != entry["path_utf8"]:
            fail(f"path encoding mismatch: {entry['path_utf8']!r}")
        if not decoded.startswith(b"/"):
            fail("non-absolute path in manifest")
        if entry["path_utf8"] in by_path:
            fail(f"duplicate path: {entry['path_utf8']}")
        if entry["type"] == "regular" and "content_sha256" not in entry:
            fail(f"regular file lacks content hash: {entry['path_utf8']}")
        if entry["type"] == "symlink" and "symlink_target_b64" not in entry:
            fail(f"symlink lacks target: {entry['path_utf8']}")
        for value in dict(entry["xattrs"]).values():
            base64.b64decode(value, validate=True)
        path_bytes.append(decoded)
        by_path[str(entry["path_utf8"])] = entry
        inodes.add(int(entry["inode"]))
    if path_bytes != sorted(path_bytes):
        fail("entries are not in canonical raw-path order")

    with args.audio_manifest.open(encoding="utf-8", newline="") as source:
        required_audio = list(csv.DictReader(source, delimiter="\t"))
    for row in required_audio:
        path = "/" + row["path"]
        entry = by_path.get(path)
        if entry is None:
            fail(f"audio compatibility path missing: {path}")
        if entry["type"] != "regular":
            fail(f"audio compatibility path is not a regular file: {path}")
        if entry["content_sha256"] != row["sha256"]:
            fail(f"audio compatibility hash mismatch: {path}")

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    type_counts = collections.Counter(str(entry["type"]) for entry in entries)
    if summary.get("entry_count") != len(entries):
        fail("summary entry count disagrees with entries")
    if summary.get("unique_inode_count") != len(inodes):
        fail("summary inode count disagrees with entries")
    if summary.get("type_counts") != dict(sorted(type_counts.items())):
        fail("summary type counts disagree with entries")

    verdict = {
        "schema": 1,
        "valid": True,
        "entry_count": len(entries),
        "unique_inode_count": len(inodes),
        "audio_manifest_entries_verified": len(required_audio),
        "sample_paths": {
            "/build.prop": by_path["/build.prop"]["content_sha256"],
            "/bin/acpi": by_path["/bin/acpi"]["symlink_target_b64"],
            "/bin/run-as": by_path["/bin/run-as"].get("capability_hex"),
        },
    }
    args.output.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.audio_output:
        audio_verdict = {
            "schema": 1,
            "valid": True,
            "verified_entries": [
                {
                    "component_id": row["component_id"],
                    "path": "/" + row["path"],
                    "sha256": row["sha256"],
                }
                for row in required_audio
            ],
        }
        args.audio_output.write_text(
            json.dumps(audio_verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
