#!/usr/bin/env python3
"""Exercise fail-closed paths in verify-phase4-release-set.py."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def option(command: list[str], name: str) -> int:
    try:
        return command.index(name)
    except ValueError as error:
        raise ValueError(f"baseline verifier arguments omit {name}") from error


def replaced(command: list[str], name: str, value: str) -> list[str]:
    result = list(command)
    index = option(result, name)
    if index + 1 >= len(result):
        raise ValueError(f"baseline option has no value: {name}")
    result[index + 1] = value
    return result


def execute(name: str, command: list[str], *, expect_success: bool) -> dict[str, object]:
    completed = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
    )
    success = completed.returncode == 0
    if success != expect_success:
        raise ValueError(f"unexpected verifier result for {name}: exit {completed.returncode}")
    errors = completed.stderr.decode("utf-8", errors="replace").strip().splitlines()
    return {
        "name": name,
        "accepted": success,
        "exit_code": completed.returncode,
        "last_error": errors[-1] if errors else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrong-verity-key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("verifier_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    verifier_args = args.verifier_args
    if verifier_args and verifier_args[0] == "--":
        verifier_args = verifier_args[1:]
    if not verifier_args:
        parser.error("supply baseline verifier arguments after --")

    verifier = Path(__file__).with_name("verify-phase4-release-set.py")
    baseline = [sys.executable, str(verifier), *verifier_args]
    try:
        results = [execute("baseline", baseline, expect_success=True)]
        stock_boot = baseline[option(baseline, "--stock-boot") + 1]
        verity_key = baseline[option(baseline, "--verity-key") + 1]
        with tempfile.TemporaryDirectory(prefix="leo-release-set-faults-") as temporary:
            root = Path(temporary)
            missing = root / "does-not-exist"
            results.append(execute(
                "missing_system",
                replaced(baseline, "--system", str(missing)),
                expect_success=False,
            ))
            results.append(execute(
                "swapped_project_boot",
                replaced(baseline, "--boot", stock_boot),
                expect_success=False,
            ))
            results.append(execute(
                "wrong_verity_key",
                replaced(baseline, "--verity-key", str(args.wrong_verity_key.resolve())),
                expect_success=False,
            ))
            results.append(execute(
                "wrong_boot_certificate",
                replaced(baseline, "--boot-certificate", verity_key),
                expect_success=False,
            ))
            results.append(execute(
                "missing_stock_recovery",
                replaced(baseline, "--stock-recovery", str(missing)),
                expect_success=False,
            ))
            results.append(execute(
                "missing_fault_report",
                replaced(baseline, "--fault-report", str(missing)),
                expect_success=False,
            ))

            manifest_path = Path(baseline[option(baseline, "--manifest") + 1]).resolve()
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifacts"]["system_raw"]["sha256"] = "00" * 32
            bad_manifest = root / "hash-mismatch.json"
            bad_manifest.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            results.append(execute(
                "manifest_hash_mismatch",
                replaced(baseline, "--manifest", str(bad_manifest)),
                expect_success=False,
            ))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))

    report = {
        "schema": 1,
        "classification": "phase4-release-set-fault-injection",
        "baseline_accepted": results[0]["accepted"],
        "all_negative_cases_rejected": all(not item["accepted"] for item in results[1:]),
        "negative_case_count": len(results) - 1,
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
