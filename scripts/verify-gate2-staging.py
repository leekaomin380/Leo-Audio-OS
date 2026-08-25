#!/usr/bin/env python3
"""Verify a content-only Gate 2 staging tree against Gate 1 semantics."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def type_name(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "unsupported"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", required=True, type=Path)
    parser.add_argument("--staging", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()

    if not args.staging.is_dir():
        fail(f"staging is not a directory: {args.staging}")
    if args.report.exists():
        fail(f"report already exists: {args.report}")

    expected: dict[str, dict[str, object]] = {}
    for line in args.entries.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        raw_path = entry["path_utf8"]
        if not isinstance(raw_path, str) or not raw_path.startswith("/"):
            fail(f"invalid source path: {raw_path!r}")
        relative = raw_path.removeprefix("/")
        if relative in expected:
            fail(f"duplicate source path: {raw_path}")
        expected[relative] = entry

    observed: set[str] = set()
    pending = [""]
    checked_regular = 0
    checked_symlink = 0
    while pending:
        relative = pending.pop()
        path = args.staging / relative
        info = path.lstat()
        observed.add(relative)
        entry = expected.get(relative)
        if entry is None:
            fail(f"unexpected staging path: /{relative}" if relative else "unexpected staging root")
        actual_type = type_name(info.st_mode)
        if actual_type != entry["type"]:
            fail(f"type mismatch: /{relative}: {actual_type} != {entry['type']}")
        if actual_type == "directory":
            with os.scandir(path) as children:
                pending.extend(child.name if not relative else f"{relative}/{child.name}" for child in children)
        elif actual_type == "regular":
            if sha256_file(path) != entry["content_sha256"]:
                fail(f"content hash mismatch: /{relative}")
            checked_regular += 1
        elif actual_type == "symlink":
            target = os.fsencode(os.readlink(path))
            if target != base64.b64decode(entry["symlink_target_b64"], validate=True):
                fail(f"symlink target mismatch: /{relative}")
            checked_symlink += 1

    missing = set(expected) - observed
    if missing:
        fail(f"missing staging paths: {len(missing)}")
    summary = {
        "staging_content_valid": True,
        "expected_entries": len(expected),
        "observed_entries": len(observed),
        "checked_regular_files": checked_regular,
        "checked_symlinks": checked_symlink,
    }
    args.report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
