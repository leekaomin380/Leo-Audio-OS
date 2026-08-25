#!/usr/bin/env python3
"""Audit Gate 3's two-path addition without confusing ext4 inode allocation for file semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ADDED = ("/app/LeoShell", "/app/LeoShell/LeoShell.apk")


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def load(path: Path) -> dict[str, dict[str, object]]:
    records = [json.loads(line) for line in path.read_bytes().splitlines()]
    result = {record["path_utf8"]: record for record in records}
    if len(result) != len(records):
        fail(f"duplicate paths in {path}")
    return result


def comparable(record: dict[str, object]) -> dict[str, object]:
    # ext4 inode numbers are allocator addresses. Adding two files changes
    # subsequent addresses even though every contract-level file property is
    # unchanged. Directory link count is retained and checked separately.
    return {key: value for key, value in record.items() if key != "inode"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-entries", required=True, type=Path)
    parser.add_argument("--expected-entries", required=True, type=Path)
    parser.add_argument("--candidate-entries", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        fail(f"output already exists: {args.output}")
    base = load(args.base_entries)
    expected = load(args.expected_entries)
    candidate = load(args.candidate_entries)
    if len(base) != 3923 or len(expected) != 3925 or len(candidate) != 3925:
        fail("Gate 3 requires 3923 base records and 3925 expected/candidate records")
    if set(expected) - set(base) != set(ADDED) or set(base) - set(expected):
        fail("expected input is not exactly the approved two-path overlay")
    if set(candidate) != set(expected):
        fail("candidate path set differs from the approved Gate 3 input")

    inode_changed = 0
    for path, prior in base.items():
        actual = candidate[path]
        before = comparable(prior)
        after = comparable(actual)
        if path == "/app":
            if after.get("nlink") != before.get("nlink", 0) + 1:
                fail("/app link count must increase by exactly one for LeoShell")
            before["nlink"] = after["nlink"]
        if before != after:
            fail(f"original semantic record changed: {path}")
        if prior.get("inode") != actual.get("inode"):
            inode_changed += 1

    for path in ADDED:
        wanted = comparable(expected[path])
        actual = comparable(candidate[path])
        if wanted != actual:
            fail(f"new path differs from Gate 3 contract: {path}")

    report = {
        "schema": 1,
        "valid": True,
        "base_entries": len(base),
        "candidate_entries": len(candidate),
        "approved_added_paths": list(ADDED),
        "original_semantic_records_unchanged": len(base),
        "physical_inode_numbers_changed": inode_changed,
        "directory_link_count_change": {"/app": {"before": base["/app"]["nlink"], "after": candidate["/app"]["nlink"]}},
        "comparison_rule": "all fields exact except physical inode addresses; /app nlink must increase by one",
        "candidate_entries_sha256": hashlib.sha256(args.candidate_entries.read_bytes()).hexdigest(),
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
