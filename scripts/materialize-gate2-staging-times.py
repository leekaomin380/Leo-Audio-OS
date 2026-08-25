#!/usr/bin/env python3
"""Apply Gate 1 mtime values to a verified Gate 2 staging tree."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


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

    applied = 0
    for line in args.entries.read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        relative = entry["path_utf8"].removeprefix("/")
        path = args.staging / relative
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            os.utime(path, ns=(entry["mtime_ns"], entry["mtime_ns"]), follow_symlinks=False)
        else:
            os.utime(path, ns=(entry["mtime_ns"], entry["mtime_ns"]))
        observed = path.lstat().st_mtime_ns
        if observed != entry["mtime_ns"]:
            fail(f"mtime did not persist for {entry['path_utf8']}: {observed}")
        applied += 1

    args.report.write_text(
        json.dumps({"staging_mtimes_valid": True, "applied_entries": applied}, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
