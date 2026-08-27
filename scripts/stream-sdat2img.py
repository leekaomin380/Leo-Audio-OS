#!/usr/bin/env python3
"""Reconstruct a block OTA image while streaming decompressed new.dat bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys


BLOCK_SIZE = 4096
SUPPORTED_COMMANDS = {"new", "zero", "erase"}


def parse_ranges(raw: str) -> list[tuple[int, int]]:
    values = [int(value) for value in raw.split(",")]
    if not values or values[0] != len(values) - 1 or values[0] % 2:
        raise ValueError(f"invalid range set: {raw}")
    ranges = list(zip(values[1::2], values[2::2]))
    if any(start < 0 or end <= start for start, end in ranges):
        raise ValueError(f"invalid range bounds: {raw}")
    return ranges


def read_exact(stream, length: int) -> bytes:
    chunks: list[bytes] = []
    remaining = length
    while remaining:
        chunk = stream.read(min(8 * 1024 * 1024, remaining))
        if not chunk:
            raise EOFError(f"new.dat ended with {remaining} bytes still required")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transfer-list", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--new-data", default="-", help="decompressed new.dat path or '-' for stdin")
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lines = [line.strip() for line in args.transfer_list.read_text().splitlines() if line.strip()]
    if len(lines) < 5:
        raise ValueError("transfer list is too short")
    version = int(lines[0])
    declared_touched_blocks = int(lines[1])
    if version not in {3, 4}:
        raise ValueError(f"unsupported transfer-list version: {version}")

    commands: list[tuple[str, list[tuple[int, int]]]] = []
    max_block = 0
    command_blocks = {name: 0 for name in SUPPORTED_COMMANDS}
    for line in lines[4:]:
        name, raw_ranges = line.split(maxsplit=1)
        if name not in SUPPORTED_COMMANDS:
            raise ValueError(f"unsupported command in full-image converter: {name}")
        ranges = parse_ranges(raw_ranges)
        commands.append((name, ranges))
        for start, end in ranges:
            command_blocks[name] += end - start
            max_block = max(max_block, end)

    touched_blocks = command_blocks["new"] + command_blocks["zero"]
    if touched_blocks != declared_touched_blocks:
        raise ValueError(
            f"declared touched blocks {declared_touched_blocks} != parsed {touched_blocks}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    source = sys.stdin.buffer if args.new_data == "-" else Path(args.new_data).open("rb")
    consumed = 0
    try:
        with args.output.open("w+b") as output:
            output.truncate(max_block * BLOCK_SIZE)
            for name, ranges in commands:
                if name != "new":
                    continue
                for start, end in ranges:
                    length = (end - start) * BLOCK_SIZE
                    output.seek(start * BLOCK_SIZE)
                    output.write(read_exact(source, length))
                    consumed += length
            output.flush()
            os.fsync(output.fileno())
        if source.read(1):
            raise ValueError("new.dat contains trailing bytes after all new ranges")
    finally:
        if source is not sys.stdin.buffer:
            source.close()

    report = {
        "schema": 1,
        "transfer_list": os.fspath(args.transfer_list.resolve()),
        "transfer_version": version,
        "declared_touched_blocks": declared_touched_blocks,
        "command_blocks": command_blocks,
        "max_block": max_block,
        "block_size": BLOCK_SIZE,
        "output": os.fspath(args.output.resolve()),
        "output_logical_bytes": args.output.stat().st_size,
        "new_data_consumed_bytes": consumed,
        "output_sha256": sha256(args.output),
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
