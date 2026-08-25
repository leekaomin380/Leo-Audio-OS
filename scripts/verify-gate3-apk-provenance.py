#!/usr/bin/env python3
"""Prove that signing changed no Gate 3 APK payload member."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import zipfile


SIGNATURE_MEMBER = re.compile(
    r"META-INF/(?:MANIFEST\.MF|[^/]+\.(?:SF|RSA|DSA|EC))$",
    re.IGNORECASE,
)


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def members(path: Path) -> tuple[dict[str, str], list[str]]:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            fail(f"duplicate ZIP member names: {path}")
        signatures = sorted(name for name in names if SIGNATURE_MEMBER.fullmatch(name))
        payload = {
            name: sha256(archive.read(name))
            for name in names
            if not SIGNATURE_MEMBER.fullmatch(name)
        }
        return payload, signatures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unsigned", required=True, type=Path)
    parser.add_argument("--signed", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        fail(f"output already exists: {args.output}")
    unsigned, unsigned_signatures = members(args.unsigned)
    signed, signed_signatures = members(args.signed)
    if unsigned_signatures:
        fail("unsigned release unexpectedly contains JAR signature members")
    if "META-INF/MANIFEST.MF" not in signed_signatures:
        fail("signed APK lacks the v1 JAR manifest")
    if sum(name.upper().endswith(".SF") for name in signed_signatures) != 1:
        fail("signed APK must contain exactly one v1 .SF member")
    if sum(name.upper().endswith((".RSA", ".DSA", ".EC")) for name in signed_signatures) != 1:
        fail("signed APK must contain exactly one v1 signature block member")
    if unsigned.keys() != signed.keys():
        fail("signed APK payload member set differs from the unsigned release")
    changed = [name for name in unsigned if unsigned[name] != signed[name]]
    if changed:
        fail(f"signing changed APK payload members: {changed}")
    result = {
        "schema": 1,
        "valid": True,
        "payload_member_count": len(unsigned),
        "payload_members_unchanged": len(unsigned),
        "signed_jar_signature_members": signed_signatures,
        "comparison": "member names and uncompressed bytes; only JAR signature members excluded",
        "unsigned_payload_manifest_sha256": sha256(
            json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        ),
        "signed_payload_manifest_sha256": sha256(
            json.dumps(signed, sort_keys=True, separators=(",", ":")).encode()
        ),
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
