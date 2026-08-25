#!/usr/bin/env python3
"""Generate exact canned fs_config and closed-world file_contexts for Gate 2."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import struct
from pathlib import Path


EXPECTED_CAP_MAGIC = 0x02000001
TYPE_QUALIFIERS = {
    "directory": "-d",
    "regular": "--",
    "symlink": "-l",
}
TYPE_LETTERS = {
    "directory": "d",
    "regular": "f",
    "symlink": "l",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def decode_capability(entry: dict[str, object]) -> int:
    encoded = entry.get("xattrs", {}).get("security.capability")
    if encoded is None:
        return 0
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != 20:
        fail(f"unsupported capability size for {entry['path_utf8']}: {len(raw)}")
    magic, permitted_low, inheritable_low, permitted_high, inheritable_high = struct.unpack(
        "<IIIII", raw
    )
    if magic != EXPECTED_CAP_MAGIC:
        fail(f"unsupported capability magic for {entry['path_utf8']}: 0x{magic:08x}")
    if inheritable_low or inheritable_high:
        fail(f"non-zero inheritable capability set for {entry['path_utf8']}")
    mask = permitted_low | (permitted_high << 32)
    rebuilt = struct.pack(
        "<IIIII", EXPECTED_CAP_MAGIC, permitted_low, 0, permitted_high, 0
    )
    if rebuilt != raw:
        fail(f"capability round-trip mismatch for {entry['path_utf8']}")
    return mask


def mount_path(raw_path: str, mountpoint: str) -> str:
    if raw_path == "/":
        return mountpoint
    return mountpoint + raw_path


def canned_path(raw_path: str) -> str:
    if raw_path == "/":
        return ""
    return "system" + raw_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--entries", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mountpoint", default="/system")
    args = parser.parse_args()
    if args.mountpoint != "/system":
        fail("Gate 2 only accepts mountpoint /system")

    raw_entries = args.entries.read_bytes()
    entries = [json.loads(line) for line in raw_entries.splitlines()]
    if not entries:
        fail("entries manifest is empty")
    decoded_paths = [base64.b64decode(entry["path_b64"], validate=True) for entry in entries]
    if decoded_paths != sorted(decoded_paths):
        fail("entries must be canonically byte-sorted")
    if len(set(decoded_paths)) != len(decoded_paths):
        fail("entries contain duplicate paths")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    fs_config_lines: list[str] = []
    file_context_lines: list[str] = []
    lookup_rows: list[dict[str, object]] = []
    lookup_tsv_lines = ["path\ttype\texpected_label\tsource_path"]
    capability_rows: list[dict[str, object]] = []

    for entry in entries:
        raw_path = entry["path_utf8"]
        if raw_path.encode("utf-8") != base64.b64decode(entry["path_b64"], validate=True):
            fail(f"path display is not a lossless UTF-8 representation: {raw_path!r}")
        if any(character.isspace() for character in raw_path):
            fail(f"unsupported whitespace in path: {raw_path!r}")
        entry_type = entry["type"]
        if entry_type not in TYPE_QUALIFIERS:
            fail(f"unsupported entry type for Gate 2: {raw_path}: {entry_type}")
        mode = int(entry["mode_octal"], 8) & 0o7777
        capability_mask = decode_capability(entry)
        canned = canned_path(raw_path)
        # The canned fs_config parser encodes the root path as a leading-space record.
        fs_line = f"{canned} {entry['uid']} {entry['gid']} {mode:04o}"
        if capability_mask:
            fs_line += f" capabilities=0x{capability_mask:x}"
        fs_config_lines.append(fs_line)

        label = entry.get("selinux_label")
        if not isinstance(label, str) or not label:
            fail(f"missing SELinux label: {raw_path}")
        labeled_path = mount_path(raw_path, args.mountpoint)
        file_context_lines.append(
            f"{re.escape(labeled_path)} {TYPE_QUALIFIERS[entry_type]} {label}"
        )
        lookup_rows.append(
            {
                "path": labeled_path,
                "mode_octal": entry["mode_octal"],
                "expected_label": label,
                "source_path": raw_path,
            }
        )
        lookup_tsv_lines.append(
            "\t".join((labeled_path, TYPE_LETTERS[entry_type], label, raw_path))
        )
        if capability_mask:
            capability_rows.append(
                {
                    "path": raw_path,
                    "raw_hex": base64.b64decode(
                        entry["xattrs"]["security.capability"], validate=True
                    ).hex(),
                    "mask_hex": f"0x{capability_mask:x}",
                }
            )

    fs_config = "\n".join(fs_config_lines) + "\n"
    file_contexts = "\n".join(file_context_lines) + "\n"
    (args.output_dir / "fs_config.canned").write_text(fs_config, encoding="utf-8")
    (args.output_dir / "file_contexts.closed-world").write_text(
        file_contexts, encoding="utf-8"
    )
    (args.output_dir / "selinux-lookups.json").write_text(
        json.dumps(lookup_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "selinux-lookups.tsv").write_text(
        "\n".join(lookup_tsv_lines) + "\n", encoding="utf-8"
    )
    (args.output_dir / "capability-roundtrip.json").write_text(
        json.dumps(capability_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema": 1,
        "entries": len(entries),
        "fs_config_entries": len(fs_config_lines),
        "selinux_rules": len(file_context_lines),
        "capability_entries": len(capability_rows),
        "mountpoint": args.mountpoint,
        "source_entries_sha256": sha256_bytes(raw_entries),
        "fs_config_sha256": sha256_bytes(fs_config.encode()),
        "file_contexts_sha256": sha256_bytes(file_contexts.encode()),
        "root_fs_config_encoding": "leading-space-empty-path",
        "strategy": "closed-world-literal-rule-per-source-path",
    }
    (args.output_dir / "metadata-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
