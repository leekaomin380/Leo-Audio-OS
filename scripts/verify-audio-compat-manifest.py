#!/usr/bin/env python3
"""Verify exact stock-system inputs listed in an audio compatibility manifest."""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from pathlib import Path


REQUIRED_COLUMNS = {
    "component_id", "layer", "path", "arch", "sha256", "classification", "evidence"
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--system-root", required=True, type=Path)
    args = parser.parse_args()

    failures = 0
    checked = 0
    component_ids: set[str] = set()
    paths: set[str] = set()
    with args.manifest.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or set(reader.fieldnames) != REQUIRED_COLUMNS:
            parser.error("manifest columns do not match the required schema")
        for row in reader:
            checked += 1
            component_id = row["component_id"]
            relative_path = row["path"]
            if component_id in component_ids or relative_path in paths:
                failures += 1
                print(f"DUPLICATE\t{component_id}\t{relative_path}")
                continue
            component_ids.add(component_id)
            paths.add(relative_path)
            if not SHA256_RE.fullmatch(row["sha256"]):
                failures += 1
                print(f"INVALID-SHA256\t{component_id}\t{row['sha256']}")
                continue
            if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
                failures += 1
                print(f"INVALID-PATH\t{component_id}\t{relative_path}")
                continue
            path = args.system_root / row["path"]
            if not path.is_file():
                failures += 1
                print(f"MISSING\t{component_id}\t{path}")
                continue
            actual = sha256(path)
            if actual != row["sha256"]:
                failures += 1
                print(f"MISMATCH\t{component_id}\t{actual}\t{row['sha256']}")
            else:
                print(f"OK\t{component_id}")

    print(f"checked={checked} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
