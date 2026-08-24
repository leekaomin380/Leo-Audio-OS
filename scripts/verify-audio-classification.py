#!/usr/bin/env python3
"""Validate the public audio component classification manifest."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path


FIELDS = (
    "component_id",
    "layer",
    "selector",
    "classification",
    "generation2_action",
    "confidence",
    "evidence",
    "failure_if_missing",
    "next_gate",
)
CLASSIFICATIONS = {
    "must-retain",
    "support-retain",
    "conditional-retain",
    "removal-candidate",
    "out-of-scope",
}
ACTIONS = {
    "extract-stock",
    "rebuild-source",
    "preserve-first-build",
    "remove-after-gate",
    "generate-policy",
    "omit-product",
}
CONFIDENCE = {"high", "medium", "low"}


def validate(path: Path) -> Counter[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise ValueError(f"unexpected columns: {reader.fieldnames}")
        rows = list(reader)

    if not rows:
        raise ValueError("manifest has no component rows")

    identifiers: set[str] = set()
    for number, row in enumerate(rows, start=2):
        empty = [field for field in FIELDS if not row[field].strip()]
        if empty:
            raise ValueError(f"line {number}: empty fields: {', '.join(empty)}")
        identifier = row["component_id"]
        if identifier in identifiers:
            raise ValueError(f"line {number}: duplicate component_id: {identifier}")
        identifiers.add(identifier)
        if row["classification"] not in CLASSIFICATIONS:
            raise ValueError(f"line {number}: invalid classification: {row['classification']}")
        if row["generation2_action"] not in ACTIONS:
            raise ValueError(f"line {number}: invalid action: {row['generation2_action']}")
        if row["confidence"] not in CONFIDENCE:
            raise ValueError(f"line {number}: invalid confidence: {row['confidence']}")
        if row["classification"] == "must-retain" and row["generation2_action"] in {
            "remove-after-gate",
            "omit-product",
        }:
            raise ValueError(f"line {number}: must-retain component cannot be removed")
        if row["classification"] == "out-of-scope" and row["generation2_action"] != "omit-product":
            raise ValueError(f"line {number}: out-of-scope component must use omit-product")

    return Counter(row["classification"] for row in rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest",
        nargs="?",
        type=Path,
        default=Path("manifests/audio-component-classification-v0.2.tsv"),
    )
    args = parser.parse_args()
    try:
        counts = validate(args.manifest)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f"components={sum(counts.values())}")
    for classification in sorted(counts):
        print(f"{classification}={counts[classification]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
