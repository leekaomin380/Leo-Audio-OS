#!/usr/bin/env python3
"""Prove that the Phase 4 system/boot verifiers fail closed.

All mutations are made in a temporary directory.  Inputs are read-only and no
device interface is available to this script.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def clone(source: Path, destination: Path) -> None:
    completed = subprocess.run(
        ["/bin/cp", "-c", str(source), str(destination)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        shutil.copyfile(source, destination)


def flip(path: Path, offset: int) -> None:
    with path.open("r+b") as handle:
        handle.seek(offset)
        value = handle.read(1)
        if len(value) != 1:
            raise ValueError(f"fault offset exceeds file: {path} @ {offset}")
        handle.seek(offset)
        handle.write(bytes([value[0] ^ 0x01]))


def expect_rejected(name: str, command: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    accepted = completed.returncode == 0
    if accepted:
        raise ValueError(f"fault was unexpectedly accepted: {name}")
    stderr = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
    return {
        "name": name,
        "rejected": True,
        "exit_code": completed.returncode,
        "last_error": stderr[-1] if stderr else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", required=True, type=Path)
    parser.add_argument("--verity-key", required=True, type=Path)
    parser.add_argument("--wrong-verity-key", required=True, type=Path)
    parser.add_argument("--boot", required=True, type=Path)
    parser.add_argument("--system-verification", required=True, type=Path)
    parser.add_argument("--boot-verification", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--formal-release", action="store_true")
    args = parser.parse_args()

    paths = [
        args.system, args.verity_key, args.wrong_verity_key, args.boot,
        args.system_verification, args.boot_verification,
    ]
    paths = [path.resolve() for path in paths]
    if not all(path.is_file() for path in paths):
        parser.error("one or more required inputs do not exist")

    system, verity_key, wrong_key, boot, system_report_path, boot_report_path = paths
    system_report = json.loads(system_report_path.read_text(encoding="utf-8"))
    boot_report = json.loads(boot_report_path.read_text(encoding="utf-8"))

    system_verifier = Path(__file__).with_name("inspect-legacy-system-verity.py")
    boot_verifier = Path(__file__).with_name("inspect-legacy-boot-signature.py")
    python = sys.executable

    ext4_offset = 4096
    tree_offset = int(system_report["hash_tree"]["offset"]) + 4096
    metadata_offset = int(system_report["metadata"]["offset"]) + 16
    fec_offset = int(system_report["fec"]["payload_offset"]) + 4096
    signable_size = int(boot_report["signable_size"])

    results: list[dict[str, object]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="leo-phase4-faults-") as temporary:
            root = Path(temporary)
            system_command = [python, str(system_verifier), "--verity-key", str(verity_key)]
            for name, offset in (
                ("system_ext4_data", ext4_offset),
                ("system_verity_tree", tree_offset),
                ("system_metadata_signature", metadata_offset),
                ("system_fec_payload", fec_offset),
            ):
                candidate = root / f"{name}.raw"
                clone(system, candidate)
                flip(candidate, offset)
                results.append(expect_rejected(name, system_command + ["--system", str(candidate)]))

            results.append(expect_rejected(
                "system_wrong_verity_key",
                [python, str(system_verifier), "--system", str(system), "--verity-key", str(wrong_key)],
            ))

            signed_region = root / "boot-signed-region.img"
            shutil.copyfile(boot, signed_region)
            flip(signed_region, 4096)
            results.append(expect_rejected(
                "boot_signed_region",
                [python, str(boot_verifier), "--boot", str(signed_region), "--expected-target", "/boot"],
            ))

            footer = root / "boot-footer.img"
            shutil.copyfile(boot, footer)
            flip(footer, footer.stat().st_size - 1)
            results.append(expect_rejected(
                "boot_signature_footer",
                [python, str(boot_verifier), "--boot", str(footer), "--expected-target", "/boot"],
            ))

            wrong_target = root / "boot-wrong-target.img"
            image = bytearray(boot.read_bytes())
            target_offset = image.find(b"/boot", signable_size)
            if target_offset < 0 or image.find(b"/boot", target_offset + 1) >= 0:
                raise ValueError("cannot identify one exact BootSignature target")
            image[target_offset:target_offset + 5] = b"/boox"
            wrong_target.write_bytes(image)
            results.append(expect_rejected(
                "boot_wrong_target",
                [python, str(boot_verifier), "--boot", str(wrong_target), "--expected-target", "/boot"],
            ))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        parser.error(str(error))

    report = {
        "schema": 1,
        "classification": (
            "phase4-formal-release-pair-fault-injection"
            if args.formal_release else "phase4-development-pair-fault-injection"
        ),
        "device_interface_available": False,
        "all_faults_rejected": all(item["rejected"] for item in results),
        "fault_count": len(results),
        "results": results,
    }
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
