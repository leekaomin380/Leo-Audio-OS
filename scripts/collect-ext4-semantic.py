#!/usr/bin/env python3
"""Read an ext4 image directly and emit a content-free semantic manifest.

This collector deliberately does not mount the image.  It understands the ext4
features present in the locked stock ``leo`` system image and fails closed on a
structure it cannot represent rather than silently omitting metadata.
"""

from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import math
from pathlib import Path
import struct
import uuid


XATTR_MAGIC = 0xEA020000
EXTENT_MAGIC = 0xF30A
EXT4_EXTENTS_FL = 0x00080000
EXT4_EXT_MAGIC = 0xF30A
EXT4_BG_INODE_UNINIT = 0x0001

FILE_TYPES = {
    0x1000: "fifo",
    0x2000: "char",
    0x4000: "directory",
    0x6000: "block",
    0x8000: "regular",
    0xA000: "symlink",
    0xC000: "socket",
}
XATTR_PREFIXES = {
    1: "user.",
    2: "system.posix_acl_access",
    3: "system.posix_acl_default",
    4: "trusted.",
    6: "security.",
    7: "system.",
    8: "system.richacl",
}


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def le16(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def le32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def le64(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<Q", data, offset)[0]


def signed32(data: bytes, offset: int = 0) -> int:
    return struct.unpack_from("<i", data, offset)[0]


def ext4_time_ns(inode: bytes, seconds_offset: int, extra_offset: int) -> int:
    seconds = signed32(inode, seconds_offset)
    extra = le32(inode, extra_offset)
    return (seconds + ((extra & 0x3) << 32)) * 1_000_000_000 + (extra >> 2)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def padded(length: int) -> int:
    return (length + 3) & ~3


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Ext4:
    def __init__(self, raw: Path) -> None:
        self.raw = raw
        self.source = raw.open("rb")
        self.source.seek(1024)
        self.sb = self.source.read(1024)
        if len(self.sb) != 1024 or le16(self.sb, 56) != 0xEF53:
            fail("not a readable ext4 image")
        self.block_size = 1024 << le32(self.sb, 24)
        self.block_count = le32(self.sb, 4)
        self.first_data_block = le32(self.sb, 20)
        self.blocks_per_group = le32(self.sb, 32)
        self.inodes_per_group = le32(self.sb, 40)
        self.inode_size = le16(self.sb, 88)
        self.inode_count = le32(self.sb, 0)
        self.group_count = math.ceil(
            (self.block_count - self.first_data_block) / self.blocks_per_group
        )
        self.descriptor_size = max(32, le16(self.sb, 254))
        table_block = 2 if self.block_size == 1024 else 1
        self.source.seek(table_block * self.block_size)
        table = self.source.read(self.group_count * self.descriptor_size)
        if len(table) != self.group_count * self.descriptor_size:
            fail("incomplete ext4 group descriptor table")
        self.groups = [
            table[i * self.descriptor_size : (i + 1) * self.descriptor_size]
            for i in range(self.group_count)
        ]

    def close(self) -> None:
        self.source.close()

    def read_at(self, offset: int, length: int) -> bytes:
        self.source.seek(offset)
        data = self.source.read(length)
        if len(data) != length:
            fail(f"short read at byte {offset}")
        return data

    def read_block(self, block: int) -> bytes:
        if block >= self.block_count:
            fail(f"block outside filesystem: {block}")
        return self.read_at(block * self.block_size, self.block_size)

    def read_inode(self, inode_number: int) -> bytes:
        if inode_number < 1 or inode_number > self.inode_count:
            fail(f"inode outside filesystem: {inode_number}")
        index = inode_number - 1
        group = index // self.inodes_per_group
        in_group = index % self.inodes_per_group
        descriptor = self.groups[group]
        if le16(descriptor, 18) & EXT4_BG_INODE_UNINIT:
            fail(f"referenced inode {inode_number} is in an uninitialized group")
        table_block = le32(descriptor, 8)
        return self.read_at(
            table_block * self.block_size + in_group * self.inode_size,
            self.inode_size,
        )

    def inode_extents(self, inode: bytes, context: str = "") -> list[tuple[int, int, int]]:
        if not (le32(inode, 32) & EXT4_EXTENTS_FL):
            fail(f"non-extent inode encountered; collector requires an explicit parser {context}")
        root = inode[40:100]
        return self._extent_entries(root, expected_depth=None)

    def _extent_entries(
        self, node: bytes, expected_depth: int | None
    ) -> list[tuple[int, int, int]]:
        if len(node) < 12 or le16(node, 0) != EXTENT_MAGIC:
            fail("invalid ext4 extent header")
        entries = le16(node, 2)
        maximum = le16(node, 4)
        depth = le16(node, 6)
        if expected_depth is not None and depth != expected_depth:
            fail("inconsistent ext4 extent depth")
        if entries > maximum or 12 + entries * 12 > len(node):
            fail("invalid ext4 extent entry count")
        result: list[tuple[int, int, int]] = []
        if depth == 0:
            for index in range(entries):
                entry = 12 + index * 12
                logical = le32(node, entry)
                length = le16(node, entry + 4)
                if length & 0x8000:
                    fail("uninitialized extent encountered")
                physical = (le16(node, entry + 6) << 32) | le32(node, entry + 8)
                if length == 0:
                    fail("zero-length extent encountered")
                result.append((logical, length, physical))
        else:
            for index in range(entries):
                entry = 12 + index * 12
                leaf = (le16(node, entry + 8) << 32) | le32(node, entry + 4)
                result.extend(self._extent_entries(self.read_block(leaf), depth - 1))
        result.sort()
        previous_end = 0
        for logical, length, _physical in result:
            if logical < previous_end:
                fail("overlapping ext4 extents")
            previous_end = logical + length
        return result

    def inode_data(self, inode: bytes, size: int) -> bytes:
        if size == 0:
            return b""
        chunks: list[bytes] = []
        remaining = size
        expected_logical = 0
        for logical, length, physical in self.inode_extents(inode):
            if logical > expected_logical:
                hole = min(remaining, (logical - expected_logical) * self.block_size)
                chunks.append(b"\0" * hole)
                remaining -= hole
                expected_logical = logical
            if remaining <= 0:
                break
            take = min(remaining, length * self.block_size)
            chunks.append(self.read_at(physical * self.block_size, take))
            remaining -= take
            expected_logical = logical + length
        if remaining:
            chunks.append(b"\0" * remaining)
        return b"".join(chunks)

    def inode_hash(self, inode: bytes, size: int) -> str:
        digest = hashlib.sha256()
        if size == 0:
            return digest.hexdigest()
        remaining = size
        expected_logical = 0
        for logical, length, physical in self.inode_extents(inode):
            if logical > expected_logical:
                hole = min(remaining, (logical - expected_logical) * self.block_size)
                digest.update(b"\0" * hole)
                remaining -= hole
                expected_logical = logical
            if remaining <= 0:
                break
            take = min(remaining, length * self.block_size)
            offset = physical * self.block_size
            while take:
                chunk_size = min(take, 1024 * 1024)
                digest.update(self.read_at(offset, chunk_size))
                offset += chunk_size
                take -= chunk_size
                remaining -= chunk_size
            expected_logical = logical + length
        if remaining:
            digest.update(b"\0" * remaining)
        return digest.hexdigest()

    def xattrs(self, inode: bytes) -> dict[str, bytes]:
        attributes: dict[str, bytes] = {}
        extra_isize = le16(inode, 128)
        inline_start = 128 + extra_isize
        if inline_start + 4 <= len(inode) and le32(inode, inline_start) == XATTR_MAGIC:
            # Inline e_value_offs is measured after the four-byte ibody header.
            self._xattr_entries(
                inode, inline_start, inline_start + 4, inline_start + 4, attributes
            )
        acl_block = le32(inode, 104)
        if acl_block:
            external = self.read_block(acl_block)
            if le32(external, 0) != XATTR_MAGIC:
                fail("invalid external xattr block")
            self._xattr_entries(external, 0, 32, 0, attributes)
        return dict(sorted(attributes.items()))

    def _xattr_entries(
        self,
        area: bytes,
        base: int,
        cursor: int,
        value_base: int,
        attributes: dict[str, bytes],
    ) -> None:
        while True:
            if cursor + 4 > len(area):
                fail("unterminated ext4 xattr entry list")
            name_len = area[cursor]
            name_index = area[cursor + 1]
            if name_len == 0 and name_index == 0:
                return
            if cursor + 16 + name_len > len(area):
                fail("invalid ext4 xattr entry")
            value_offset = le16(area, cursor + 2)
            value_inode = le32(area, cursor + 4)
            value_size = le32(area, cursor + 8)
            if value_inode:
                fail("EA inode values are not supported by this collector")
            prefix = XATTR_PREFIXES.get(name_index)
            if prefix is None:
                fail(f"unknown ext4 xattr namespace index: {name_index}")
            name = area[cursor + 16 : cursor + 16 + name_len]
            key = prefix + name.decode("utf-8", errors="strict")
            value_start = value_base + value_offset
            value_end = value_start + value_size
            if value_start < base or value_end > len(area):
                fail(f"invalid ext4 xattr value bounds for {key}")
            if key in attributes and attributes[key] != area[value_start:value_end]:
                fail(f"conflicting duplicate xattr: {key}")
            attributes[key] = area[value_start:value_end]
            cursor += padded(16 + name_len)


def decode_device(encoded: int) -> tuple[int, int]:
    major = ((encoded >> 8) & 0xFFF) | ((encoded >> 32) & 0xFFFFF000)
    minor = (encoded & 0xFF) | ((encoded >> 12) & 0xFFFFFF00)
    return major, minor


def inode_record(fs: Ext4, inode_number: int, inode: bytes) -> dict[str, object]:
    mode = le16(inode, 0)
    type_name = FILE_TYPES.get(mode & 0xF000)
    if type_name is None:
        fail(f"unknown inode mode: 0{mode:o}")
    size = le32(inode, 4) | (le32(inode, 108) << 32)
    xattrs = fs.xattrs(inode)
    result: dict[str, object] = {
        "inode": inode_number,
        "type": type_name,
        "mode_octal": f"{mode:06o}",
        "uid": le16(inode, 2),
        "gid": le16(inode, 24),
        "nlink": le16(inode, 26),
        "size": size,
        "mtime_ns": ext4_time_ns(inode, 16, 136),
        "xattrs": {key: b64(value) for key, value in xattrs.items()},
    }
    if "security.selinux" in xattrs:
        result["selinux_label"] = xattrs["security.selinux"].rstrip(b"\0").decode("utf-8")
    if "security.capability" in xattrs:
        result["capability_hex"] = xattrs["security.capability"].hex()
    if type_name == "regular":
        try:
            result["content_sha256"] = fs.inode_hash(inode, size)
        except SystemExit as error:
            fail(f"inode {inode_number}: {error}")
    elif type_name == "symlink":
        target = inode[40 : 40 + size] if size <= 60 else fs.inode_data(inode, size)
        result["symlink_target_b64"] = b64(target)
    elif type_name in {"char", "block"}:
        major, minor = decode_device(le32(inode, 40))
        result["rdev_major"] = major
        result["rdev_minor"] = minor
    return result


def directory_entries(fs: Ext4, inode: bytes, size: int) -> list[tuple[int, bytes]]:
    data = fs.inode_data(inode, size)
    entries: list[tuple[int, bytes]] = []
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            fail("truncated ext4 directory entry")
        inode_number = le32(data, offset)
        record_length = le16(data, offset + 4)
        name_length = data[offset + 6]
        if record_length < 8 or record_length % 4 or offset + record_length > len(data):
            fail("invalid ext4 directory record length")
        if name_length > record_length - 8:
            fail("invalid ext4 directory name length")
        if inode_number:
            name = data[offset + 8 : offset + 8 + name_length]
            if name not in {b".", b".."}:
                entries.append((inode_number, name))
        offset += record_length
    return entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    raw = args.raw.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        fail(f"output directory must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)

    fs = Ext4(raw)
    try:
        pending: collections.deque[tuple[bytes, int]] = collections.deque([(b"/", 2)])
        entries: list[dict[str, object]] = []
        inode_cache: dict[int, dict[str, object]] = {}
        inode_paths: dict[int, list[bytes]] = collections.defaultdict(list)
        visited_directories: set[int] = set()

        while pending:
            path, inode_number = pending.popleft()
            inode = fs.read_inode(inode_number)
            metadata = inode_cache.setdefault(inode_number, inode_record(fs, inode_number, inode))
            record = dict(metadata)
            record["path_b64"] = b64(path)
            record["path_utf8"] = path.decode("utf-8", errors="strict")
            entries.append(record)
            inode_paths[inode_number].append(path)
            if metadata["type"] != "directory" or inode_number in visited_directories:
                continue
            visited_directories.add(inode_number)
            for child_inode, name in directory_entries(fs, inode, int(metadata["size"])):
                if b"/" in name or b"\0" in name:
                    fail("unsafe ext4 directory name")
                child_path = path.rstrip(b"/") + b"/" + name
                pending.append((child_path, child_inode))

        entries.sort(key=lambda item: base64.b64decode(str(item["path_b64"])))
        with (output / "entries.jsonl").open("w", encoding="utf-8") as target:
            for entry in entries:
                target.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

        hardlinks = {
            str(inode): [b64(path) for path in sorted(paths)]
            for inode, paths in sorted(inode_paths.items())
            if len(paths) > 1
        }
        (output / "hardlinks.json").write_text(
            json.dumps(hardlinks, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        type_counts = collections.Counter(str(entry["type"]) for entry in entries)
        xattr_counts: collections.Counter[str] = collections.Counter()
        for entry in entries:
            xattr_counts.update(dict(entry["xattrs"]).keys())
        summary = {
            "schema": 1,
            "collector": "direct-ext4-read-only",
            "raw_sha256": file_sha256(raw),
            "entry_count": len(entries),
            "unique_inode_count": len(inode_paths),
            "hardlink_groups": len(hardlinks),
            "type_counts": dict(sorted(type_counts.items())),
            "xattr_counts": dict(sorted(xattr_counts.items())),
            "selinux_labelled_entries": sum("selinux_label" in entry for entry in entries),
            "capability_entries": sum("capability_hex" in entry for entry in entries),
            "filesystem": {
                "block_size": fs.block_size,
                "inode_size": fs.inode_size,
                "inode_count": fs.inode_count,
                "uuid": str(uuid.UUID(bytes=fs.sb[104:120])),
            },
        }
        (output / "audit-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    finally:
        fs.close()


if __name__ == "__main__":
    main()
