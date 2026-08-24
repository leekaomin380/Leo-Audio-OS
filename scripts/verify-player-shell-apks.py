#!/usr/bin/env python3
"""Verify the compiled Phase 2 APK pair before device installation."""

from pathlib import Path
import os
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "player-shell"
SAFE_APK = SHELL / "app/build/outputs/apk/safePreview/debug/app-safePreview-debug.apk"
HOME_APK = SHELL / "app/build/outputs/apk/homeCandidate/debug/app-homeCandidate-debug.apk"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def find_aapt2() -> Path:
    android_home = Path(os.environ.get("ANDROID_HOME", Path.home() / "Library/Android/sdk"))
    build_tools = android_home / "build-tools"
    candidates = sorted(build_tools.glob("*/aapt2"), reverse=True)
    if not candidates:
        fail(f"aapt2 not found below {build_tools}")
    return candidates[0]


def output(*args: str | Path) -> str:
    result = subprocess.run(
        [str(value) for value in args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return result.stdout


def verify_common(label: str, tree: str, badging: str) -> None:
    if "android.intent.category.LAUNCHER" not in tree:
        fail(f"{label} has no LAUNCHER entry")
    if "minSdkVersion:'24'" not in badging:
        fail(f"{label} does not pin minSdk 24")
    forbidden = (
        "uses-permission",
        "android.intent.action.BOOT_COMPLETED",
        "android.permission.WRITE_SECURE_SETTINGS",
        "android.permission.SYSTEM_ALERT_WINDOW",
    )
    for token in forbidden:
        if token in tree:
            fail(f"{label} contains forbidden pre-Gate-C token: {token}")


def main() -> None:
    aapt2 = find_aapt2()
    for apk in (SAFE_APK, HOME_APK):
        if not apk.is_file():
            fail(f"missing APK: {apk.relative_to(ROOT)}")

    safe_tree = output(aapt2, "dump", "xmltree", SAFE_APK, "--file", "AndroidManifest.xml")
    home_tree = output(aapt2, "dump", "xmltree", HOME_APK, "--file", "AndroidManifest.xml")
    safe_badging = output(aapt2, "dump", "badging", SAFE_APK)
    home_badging = output(aapt2, "dump", "badging", HOME_APK)

    verify_common("safePreview", safe_tree, safe_badging)
    verify_common("homeCandidate", home_tree, home_badging)

    if "android.intent.category.HOME" in safe_tree:
        fail("safePreview compiled APK unexpectedly declares HOME")
    if "android.intent.category.HOME" not in home_tree:
        fail("homeCandidate compiled APK is missing HOME")
    if "android.intent.category.DEFAULT" not in home_tree:
        fail("homeCandidate compiled APK is missing DEFAULT")

    if "package: name='io.github.leoaudio.shell.preview.debug'" not in safe_badging:
        fail("safePreview compiled package identity changed")
    if "package: name='io.github.leoaudio.shell.debug'" not in home_badging:
        fail("homeCandidate compiled package identity changed")
    if "application-label:'Leo Shell 安全预览'" not in safe_badging:
        fail("safePreview label is not visibly distinct")
    if "application-label:'Leo Shell HOME 候选'" not in home_badging:
        fail("homeCandidate label is not visibly distinct")

    print("OK: compiled safePreview has LAUNCHER but no HOME")
    print("OK: compiled homeCandidate has LAUNCHER + HOME + DEFAULT")
    print("OK: both APKs pin minSdk 24 and request no permissions")
    print("OK: compiled package identities match the recovery plan")
    print("OK: preview and HOME candidate labels are visibly distinct")


if __name__ == "__main__":
    main()
