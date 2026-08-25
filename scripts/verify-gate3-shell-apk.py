#!/usr/bin/env python3
"""Reject anything other than the minimal, signed Gate 3 Leo Shell APK."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import zipfile


PACKAGE = "io.github.leoaudio.shell"
VERSION_CODE = "10"
VERSION_NAME = "0.3.0-gate3.1-home"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def find_build_tool(name: str) -> Path:
    sdk = Path(os.environ.get("ANDROID_HOME", Path.home() / "Library/Android/sdk"))
    candidates = sorted((sdk / "build-tools").glob(f"*/{name}"), reverse=True)
    if not candidates:
        fail(f"{name} not found below {sdk / 'build-tools'}")
    return candidates[0]


def run(*command: str | Path) -> str:
    result = subprocess.run(
        [str(value) for value in command], text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode:
        print(result.stdout, file=sys.stderr, end="")
        fail(f"command failed ({result.returncode}): {command[0]}")
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--expected-cert-sha256", required=True)
    parser.add_argument("--aapt2")
    parser.add_argument("--apksigner")
    args = parser.parse_args()

    apk = args.apk.resolve()
    if not apk.is_file():
        fail(f"APK does not exist: {apk}")
    expected_cert = args.expected_cert_sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_cert):
        fail("expected certificate SHA-256 must be 64 lowercase/uppercase hex characters")
    aapt2 = Path(args.aapt2) if args.aapt2 else find_build_tool("aapt2")
    apksigner = Path(args.apksigner) if args.apksigner else find_build_tool("apksigner")
    if not aapt2.is_file() or not apksigner.is_file():
        fail("aapt2 or apksigner is not a regular file")

    badging = run(aapt2, "dump", "badging", apk)
    tree = run(aapt2, "dump", "xmltree", apk, "--file", "AndroidManifest.xml")
    expected_badging = (
        f"package: name='{PACKAGE}' versionCode='{VERSION_CODE}' "
        f"versionName='{VERSION_NAME}'"
    )
    if expected_badging not in badging:
        fail("APK package or Gate 3 version identity differs from contract")
    if "application-debuggable" in badging or "android:debuggable" in tree:
        fail("release APK is debuggable")
    required = (
        "android.intent.action.MAIN",
        "android.intent.category.LAUNCHER",
        "android.intent.category.HOME",
        "android.intent.category.DEFAULT",
        "io.github.leoaudio.shell.MainActivity",
    )
    for token in required:
        if token not in tree:
            fail(f"required manifest token is missing: {token}")
    forbidden = (
        "uses-permission",
        "sharedUserId",
        "android.intent.action.BOOT_COMPLETED",
        "WRITE_SECURE_SETTINGS",
        "SYSTEM_ALERT_WINDOW",
        "BIND_ACCESSIBILITY_SERVICE",
        "android:process",
    )
    for token in forbidden:
        if token in tree:
            fail(f"forbidden manifest token is present: {token}")
    if tree.count("E: activity") != 3:
        fail("APK must expose exactly three activities")
    if tree.count(":exported") != 3 or tree.count(")=true") < 1:
        fail("activity export boundary differs from contract")

    with zipfile.ZipFile(apk) as archive:
        members = archive.namelist()
    dex = [member for member in members if re.fullmatch(r"classes(?:[0-9]+)?\.dex", member)]
    if dex != ["classes.dex"]:
        fail(f"APK must contain exactly one classes.dex, got {dex}")
    forbidden_payload = (
        lambda member: member.startswith("kotlin/"),
        lambda member: member.endswith(".so"),
        lambda member: member.endswith(".jar"),
        lambda member: member.endswith(".apk"),
    )
    for member in members:
        if any(check(member) for check in forbidden_payload):
            fail(f"forbidden runtime payload: {member}")

    # At the APK's real minSdk 24, apksigner chooses v2 and reports v1 as
    # false even when a valid v1 block is present.  Force API 18 in a second
    # compatibility pass so v1 must be selected and cryptographically checked.
    signing = run(
        apksigner, "verify", "--verbose", "--print-certs",
        "--min-sdk-version", "24", apk,
    )
    compatibility_signing = run(
        apksigner, "verify", "--verbose", "--print-certs",
        "--min-sdk-version", "18", apk,
    )
    if "Verified using v1 scheme (JAR signing): true" not in compatibility_signing:
        fail("v1 signature is required")
    if "Verified using v2 scheme (APK Signature Scheme v2): true" not in signing:
        fail("v2 signature is required")
    if "Number of signers: 1" not in signing:
        fail("APK must have exactly one signer")
    certificate = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-fA-F]{64})", signing)
    if certificate is None:
        fail("cannot find signer certificate SHA-256")
    if certificate.group(1).lower() != expected_cert:
        fail("APK signer certificate differs from the registered Leo Shell app key")

    print("OK: Gate 3 APK identity, manifest, payload and v1/v2 signer are accepted")


if __name__ == "__main__":
    main()
