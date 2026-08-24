#!/usr/bin/env python3
"""Derive reviewable fs_config and SELinux tables from a semantic JSONL file."""

from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", required=True, type=Path)
    parser.add_argument("--fs-config-output", required=True, type=Path)
    parser.add_argument("--selinux-output", required=True, type=Path)
    args = parser.parse_args()

    entries = [json.loads(line) for line in args.entries.read_text(encoding="utf-8").splitlines()]
    paths = [base64.b64decode(entry["path_b64"], validate=True) for entry in entries]
    if paths != sorted(paths):
        fail("entries must be canonically sorted before derivation")
    with args.fs_config_output.open("w", encoding="utf-8") as fs_config:
        fs_config.write("path_b64\tpath_utf8\tuid\tgid\tmode_octal\tcapability_hex\n")
        for entry in entries:
            fs_config.write(
                "\t".join(
                    str(entry.get(key, ""))
                    for key in (
                        "path_b64",
                        "path_utf8",
                        "uid",
                        "gid",
                        "mode_octal",
                        "capability_hex",
                    )
                )
                + "\n"
            )
    with args.selinux_output.open("w", encoding="utf-8") as labels:
        labels.write("path_b64\tpath_utf8\tselinux_label\n")
        for entry in entries:
            if "selinux_label" not in entry:
                fail(f"entry lacks SELinux label: {entry['path_utf8']}")
            labels.write(
                f"{entry['path_b64']}\t{entry['path_utf8']}\t{entry['selinux_label']}\n"
            )
    print(json.dumps({"entries": len(entries), "valid": True}, sort_keys=True))


if __name__ == "__main__":
    main()
