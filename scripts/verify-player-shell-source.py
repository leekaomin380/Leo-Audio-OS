#!/usr/bin/env python3
"""Verify Phase 2 source manifests before any APK reaches the device."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "apps" / "player-shell"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"


def categories(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    return {
        node.attrib[ANDROID_NS + "name"]
        for node in root.findall(".//category")
    }


def permissions(path: Path) -> set[str]:
    root = ET.parse(path).getroot()
    return {
        node.attrib[ANDROID_NS + "name"]
        for node in root.findall("uses-permission")
    }


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    main_manifest = SHELL / "app/src/main/AndroidManifest.xml"
    safe_manifest = SHELL / "app/src/safePreview/AndroidManifest.xml"
    home_manifest = SHELL / "app/src/homeCandidate/AndroidManifest.xml"
    build_file = SHELL / "app/build.gradle"
    main_layout = SHELL / "app/src/main/res/layout/activity_main.xml"
    main_activity = SHELL / "app/src/main/java/io/github/leoaudio/shell/MainActivity.java"

    for path in (
        main_manifest,
        safe_manifest,
        home_manifest,
        build_file,
        main_layout,
        main_activity,
    ):
        if not path.is_file():
            fail(f"missing required file: {path.relative_to(ROOT)}")

    safe_categories = categories(safe_manifest)
    home_categories = categories(home_manifest)
    if "android.intent.category.HOME" in safe_categories:
        fail("safePreview must not declare HOME")
    if "android.intent.category.LAUNCHER" not in safe_categories:
        fail("safePreview must remain directly launchable")
    if "android.intent.category.HOME" not in home_categories:
        fail("homeCandidate must declare HOME")
    if "android.intent.category.DEFAULT" not in home_categories:
        fail("homeCandidate HOME filter must declare DEFAULT")

    declared_permissions = permissions(main_manifest)
    if declared_permissions:
        fail(f"initial prototype must request no permissions: {sorted(declared_permissions)}")

    manifest_text = main_manifest.read_text(encoding="utf-8")
    forbidden = ("BOOT_COMPLETED", "WRITE_SECURE_SETTINGS", "SYSTEM_ALERT_WINDOW")
    for token in forbidden:
        if token in manifest_text:
            fail(f"forbidden pre-Gate-C capability present: {token}")

    build_text = build_file.read_text(encoding="utf-8")
    required_build_tokens = (
        'applicationId "io.github.leoaudio.shell"',
        "minSdk 24",
        'safePreview {',
        'homeCandidate {',
        'buildConfigField "boolean", "HOME_CAPABLE", "false"',
        'buildConfigField "boolean", "HOME_CAPABLE", "true"',
    )
    for token in required_build_tokens:
        if token not in build_text:
            fail(f"missing build invariant: {token}")

    for flavor, label in (
        ("safePreview", "Leo Shell 安全预览"),
        ("homeCandidate", "Leo Shell HOME 候选"),
    ):
        if f'manifestPlaceholders = [appLabel: "{label}"]' not in build_text:
            fail(f"{flavor} must supply its manifest label without a resource overlay")

    for layout_path in (SHELL / "app/src/main/res/layout").glob("*.xml"):
        if "android:textAllCaps" in layout_path.read_text(encoding="utf-8"):
            fail(
                "old MIUI compatibility invariant violated: "
                f"{layout_path.relative_to(ROOT)} contains android:textAllCaps"
            )

    layout_root = ET.parse(main_layout).getroot()
    mode_nodes = [
        node
        for node in layout_root.iter()
        if node.attrib.get(ANDROID_NS + "id") == "@+id/shell_mode_state"
    ]
    if len(mode_nodes) != 1:
        fail("main layout must contain exactly one shell_mode_state")
    if mode_nodes[0].attrib.get(ANDROID_NS + "text") != "@string/mode_safe_preview":
        fail("shell_mode_state must own the replaceable mode status text")

    activity_text = main_activity.read_text(encoding="utf-8")
    back_guard = (
        "public void onBackPressed()",
        "if (BuildConfig.HOME_CAPABLE)",
        "super.onBackPressed()",
        "Build.VERSION.SDK_INT >= 33",
        "BackApi33.register(this)",
        "registerOnBackInvokedCallback",
    )
    for token in back_guard:
        if token not in activity_text:
            fail(f"HOME root back-key guard is missing: {token}")

    print("OK: safePreview has no HOME capability")
    print("OK: homeCandidate declares HOME + DEFAULT")
    print("OK: initial prototype requests no Android permissions")
    print("OK: no boot receiver, secure-settings, or overlay capability")
    print("OK: API 24 and package identity are pinned")
    print("OK: dynamic HOME mode text is bound to the correct status view")
    print("OK: flavor labels do not replace compiled string resources")
    print("OK: layouts avoid the old-MIUI textAllCaps inflater fault")
    print("OK: HOME candidate consumes Back while safe preview retains normal Back")


if __name__ == "__main__":
    main()
