#!/usr/bin/env python3
"""Emit the Gate 1 semantic manifest from an already read-only mounted tree."""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import os
from pathlib import Path
import stat


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def file_hash(path: bytes) -> str:
    digest = hashlib.sha256()
    with open(path, "rb", buffering=1024 * 1024) as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def type_name(mode: int) -> str:
    for predicate, name in (
        (stat.S_ISFIFO, "fifo"),
        (stat.S_ISCHR, "char"),
        (stat.S_ISDIR, "directory"),
        (stat.S_ISBLK, "block"),
        (stat.S_ISREG, "regular"),
        (stat.S_ISLNK, "symlink"),
        (stat.S_ISSOCK, "socket"),
    ):
        if predicate(mode):
            return name
    fail(f"unsupported filesystem mode: 0{mode:o}")


def entry(path: bytes, system_root: bytes) -> dict[str, object]:
    metadata = os.lstat(path)
    relative = path[len(system_root) :]
    canonical = b"/" if not relative else relative
    attrs: dict[str, str] = {}
    for name in sorted(os.listxattr(path, follow_symlinks=False)):
        raw = os.getxattr(path, name, follow_symlinks=False)
        attrs[name] = b64(raw)
    kind = type_name(metadata.st_mode)
    result: dict[str, object] = {
        "path_b64": b64(canonical),
        "path_utf8": canonical.decode("utf-8", errors="strict"),
        "inode": metadata.st_ino,
        "type": kind,
        "mode_octal": f"{metadata.st_mode:06o}",
        "uid": metadata.st_uid,
        "gid": metadata.st_gid,
        "nlink": metadata.st_nlink,
        "size": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "xattrs": attrs,
    }
    if "security.selinux" in attrs:
        raw_label = base64.b64decode(attrs["security.selinux"])
        result["selinux_label"] = raw_label.rstrip(b"\0").decode("utf-8")
    if "security.capability" in attrs:
        result["capability_hex"] = base64.b64decode(attrs["security.capability"]).hex()
    if kind == "regular":
        result["content_sha256"] = file_hash(path)
    elif kind == "symlink":
        result["symlink_target_b64"] = b64(os.readlink(path))
    elif kind in {"char", "block"}:
        result["rdev_major"] = os.major(metadata.st_rdev)
        result["rdev_minor"] = os.minor(metadata.st_rdev)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--system-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = os.fsencode(args.system_root.resolve())
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        fail(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    pending: collections.deque[bytes] = collections.deque([root])
    entries: list[dict[str, object]] = []
    seen_directories: set[int] = set()
    inode_paths: dict[int, list[bytes]] = collections.defaultdict(list)
    while pending:
        path = pending.popleft()
        current = entry(path, root)
        entries.append(current)
        inode_paths[int(current["inode"])].append(base64.b64decode(str(current["path_b64"])))
        if current["type"] != "directory":
            continue
        inode = int(current["inode"])
        if inode in seen_directories:
            continue
        seen_directories.add(inode)
        with os.scandir(path) as directory:
            for child in directory:
                if child.name not in {b".", b".."}:
                    pending.append(path + b"/" + child.name)

    entries.sort(key=lambda item: base64.b64decode(str(item["path_b64"])))
    with (output / "entries.jsonl").open("w", encoding="utf-8") as target:
        for value in entries:
            target.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
    hardlinks = {
        str(inode): [b64(path) for path in sorted(paths)]
        for inode, paths in sorted(inode_paths.items())
        if len(paths) > 1
    }
    (output / "hardlinks.json").write_text(
        json.dumps(hardlinks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    types = collections.Counter(str(value["type"]) for value in entries)
    xattrs = collections.Counter()
    for value in entries:
        xattrs.update(dict(value["xattrs"]).keys())
    summary = {
        "schema": 1,
        "collector": "linux-kernel-ro-noload",
        "entry_count": len(entries),
        "unique_inode_count": len(inode_paths),
        "hardlink_groups": len(hardlinks),
        "type_counts": dict(sorted(types.items())),
        "xattr_counts": dict(sorted(xattrs.items())),
        "selinux_labelled_entries": sum("selinux_label" in value for value in entries),
        "capability_entries": sum("capability_hex" in value for value in entries),
    }
    (output / "audit-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
