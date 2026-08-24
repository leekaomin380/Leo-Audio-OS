#!/usr/bin/env python3
"""Build a reproducible ELF dependency graph for the stock audio stack.

The input system tree and the generated detailed report are private evidence.
Only this analyzer and manually reviewed, non-proprietary summaries belong in Git.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path


DEFAULT_SEEDS = (
    "lib/hw/audio.primary.msm8994.so",
    "lib64/hw/audio.primary.msm8994.so",
    "bin/audioserver",
    "bin/audiod",
    "bin/adsprpcd",
    "bin/rfs_access",
    "vendor/lib/libacdbloader.so",
)

NEEDED_RE = re.compile(r"^\s*NEEDED\s+(.+?)\s*$")
SO_RE = re.compile(rb"(?:[A-Za-z0-9_+.-]+/)*lib[A-Za-z0-9_+.-]+\.so(?:\.[0-9]+)*")
MAP_RE = re.compile(r"\s(/(?:system|vendor)/\S+)")
MAP_HEADING_RE = re.compile(r"^\[([^\]]+) pid=\d+ maps\]$")


@dataclass(frozen=True, order=True)
class Edge:
    source: str
    edge_type: str
    target: str
    resolved_path: str
    arch: str
    status: str


def elf_arch(path: Path) -> str | None:
    try:
        header = path.read_bytes()[:5]
    except OSError:
        return None
    if header[:4] != b"\x7fELF":
        return None
    return {1: "elf32", 2: "elf64"}.get(header[4], "elf-unknown")


def needed_libraries(path: Path) -> list[str]:
    result = subprocess.run(
        ["/usr/bin/objdump", "-p", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"objdump failed for {path}: {result.stderr.strip()}")
    return sorted(
        match.group(1)
        for line in result.stdout.splitlines()
        if (match := NEEDED_RE.match(line))
    )


def string_library_references(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return []
    refs = {match.decode("ascii", errors="ignore") for match in SO_RE.findall(data)}
    return sorted(refs)


def candidate_directories(source: str, arch: str) -> tuple[str, ...]:
    source_dir = str(Path(source).parent)
    bit_dir = "lib64" if arch == "elf64" else "lib"
    vendor_dir = f"vendor/{bit_dir}"
    if source.startswith("vendor/"):
        ordered = (source_dir, vendor_dir, bit_dir)
    else:
        ordered = (source_dir, bit_dir, vendor_dir)
    return tuple(dict.fromkeys(ordered))


def resolve_library(root: Path, source: str, target: str, arch: str) -> str | None:
    target_name = Path(target).name
    for directory in candidate_directories(source, arch):
        candidate = root / directory / target_name
        if candidate.is_file() and elf_arch(candidate) == arch:
            return str(candidate.relative_to(root))
    return None


def system_path_to_relative(path: str) -> str | None:
    if path.startswith("/system/"):
        return path.removeprefix("/system/")
    if path.startswith("/vendor/"):
        return "vendor/" + path.removeprefix("/vendor/")
    return None


def runtime_mapped_elfs(root: Path, map_files: list[Path]) -> set[tuple[str, str]]:
    mapped: set[tuple[str, str]] = set()
    for map_file in map_files:
        process = "unknown"
        for line in map_file.read_text(errors="replace").splitlines():
            heading = MAP_HEADING_RE.match(line)
            if heading:
                process = heading.group(1)
                continue
            if line.startswith("["):
                process = ""
                continue
            if not process:
                continue
            match = MAP_RE.search(line)
            if not match:
                continue
            relative = system_path_to_relative(match.group(1))
            if relative and (root / relative).is_file() and elf_arch(root / relative):
                mapped.add((process, relative))
    return mapped


def analyze(root: Path, seeds: list[str], map_files: list[Path]) -> tuple[set[str], set[Edge]]:
    edges: set[Edge] = set()
    visited: set[str] = set()
    queued: set[str] = set()
    queue: deque[str] = deque()

    def enqueue(relative: str) -> None:
        if relative not in visited and relative not in queued:
            queue.append(relative)
            queued.add(relative)

    for seed in seeds:
        path = root / seed
        if not path.is_file():
            edges.add(Edge("[seed]", "seed", seed, "", "", "missing"))
            continue
        arch = elf_arch(path) or ""
        edges.add(Edge("[seed]", "seed", seed, seed, arch, "resolved"))
        enqueue(seed)

    for process, relative in sorted(runtime_mapped_elfs(root, map_files)):
        arch = elf_arch(root / relative) or ""
        edges.add(Edge(f"[runtime-map:{process}]", "runtime-map", Path(relative).name,
                       relative, arch, "observed"))
        enqueue(relative)

    while queue:
        source = queue.popleft()
        queued.discard(source)
        if source in visited:
            continue
        visited.add(source)
        source_path = root / source
        arch = elf_arch(source_path)
        if arch is None:
            edges.add(Edge(source, "inspect", "", "", "", "not-elf"))
            continue

        needed = needed_libraries(source_path)
        for target in needed:
            resolved = resolve_library(root, source, target, arch)
            edges.add(Edge(source, "dt-needed", target, resolved or "", arch,
                           "resolved" if resolved else "unresolved"))
            if resolved:
                enqueue(resolved)

        # Embedded library names are most useful on the explicitly selected
        # entry points. Scanning every transitive framework library produces a
        # large unrelated plugin inventory and obscures the audio question.
        if source in seeds:
            direct_needed = set(needed)
            for target in string_library_references(source_path):
                target_name = Path(target).name
                if target_name in direct_needed:
                    continue
                resolved = resolve_library(root, source, target_name, arch)
                edges.add(Edge(source, "string-ref", target, resolved or "", arch,
                               "candidate" if resolved else "unresolved-candidate"))

    return visited, edges


def write_tsv(output: Path, edges: set[Edge]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("source", "edge_type", "target", "resolved_path", "arch", "status"))
        for edge in sorted(edges):
            writer.writerow((edge.source, edge.edge_type, edge.target,
                             edge.resolved_path, edge.arch, edge.status))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-root", required=True, type=Path)
    parser.add_argument("--runtime-maps", action="append", default=[], type=Path)
    parser.add_argument("--seed", action="append", default=[])
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = args.system_root.resolve()
    if not root.is_dir():
        parser.error(f"system root is not a directory: {root}")

    map_files = [path.resolve() for path in args.runtime_maps]
    missing_maps = [str(path) for path in map_files if not path.is_file()]
    if missing_maps:
        parser.error("runtime map files not found: " + ", ".join(missing_maps))

    seeds = args.seed or list(DEFAULT_SEEDS)
    try:
        visited, edges = analyze(root, seeds, map_files)
        write_tsv(args.output, edges)
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1

    unresolved = sum(edge.status.startswith("unresolved") for edge in edges)
    print(f"analyzed_elfs={len(visited)}")
    print(f"edges={len(edges)}")
    print(f"unresolved={unresolved}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
