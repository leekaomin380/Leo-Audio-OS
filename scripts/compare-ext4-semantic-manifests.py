#!/usr/bin/env python3
"""Require byte-for-byte equality of the two canonical Gate 1 manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", required=True, type=Path)
    parser.add_argument("--kernel", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    primary_entries = args.primary / "entries.jsonl"
    kernel_entries = args.kernel / "entries.jsonl"
    primary_hardlinks = args.primary / "hardlinks.json"
    kernel_hardlinks = args.kernel / "hardlinks.json"
    for path in (primary_entries, kernel_entries, primary_hardlinks, kernel_hardlinks):
        if not path.is_file():
            fail(f"missing semantic evidence: {path}")
    if primary_entries.read_bytes() != kernel_entries.read_bytes():
        fail("primary and kernel semantic entries differ")
    if primary_hardlinks.read_bytes() != kernel_hardlinks.read_bytes():
        fail("primary and kernel hardlink groups differ")
    summary = json.loads((args.primary / "audit-summary.json").read_text(encoding="utf-8"))
    verdict = {
        "schema": 1,
        "valid": True,
        "comparison": "canonical-byte-equality",
        "entry_count": summary["entry_count"],
        "primary_entries_sha256": sha256(primary_entries),
        "kernel_entries_sha256": sha256(kernel_entries),
        "hardlinks_sha256": sha256(primary_hardlinks),
    }
    args.output.write_text(
        json.dumps(verdict, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(verdict, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
