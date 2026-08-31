import argparse
import json
import os
import sys
import hashlib
from pathlib import Path

def calculate_sha256(filepath):
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception:
        return None

def verify_evidence_file(evidence_dir, path, expected_sha256):
    if not isinstance(path, str) or not isinstance(expected_sha256, str):
        return False
    if not path or not expected_sha256:
        return False
    if os.path.isabs(path) or ".." in path.split(os.sep):
        return False
    full_path = os.path.join(os.path.realpath(evidence_dir), path)
    if not os.path.isfile(full_path):
        return False
    candidate = Path(full_path)
    root = Path(evidence_dir).resolve()
    if any(p.is_symlink() for p in [candidate, *candidate.parents]):
        return False
    if root not in candidate.resolve().parents:
        return False
    actual_sha256 = calculate_sha256(full_path)
    return actual_sha256 == expected_sha256

def is_strict_true(val):
    return type(val) is bool and val is True

def check_gate(evidence, gate_name, evidence_dir, scope):
    if not isinstance(evidence, dict) or gate_name not in evidence:
        return False
    gate_data = evidence[gate_name]
    if not isinstance(gate_data, dict):
        return False
        
    required_fields = []
    if gate_name == "host_diagnostic":
        required_fields = ["source_frozen", "host_tests", "elf_closure", "feature_off_equal", "repeatable"]
    elif gate_name == "target_build":
        required_fields = ["full_target_manifest", "baseline_build", "resources_compatible", "toolchain_provenance", "target_artifact"]
        if scope == "systemui_full":
            required_fields.append("legal_matching_signing_path")
    elif gate_name == "device_window":
        required_fields = ["offline_fs_audit", "rollback_verified", "device_preflight_fresh", "current_device_authorization"]
        
    for field in required_fields:
        if field not in gate_data:
            return False
        field_data = gate_data[field]
        if not isinstance(field_data, dict):
            return False
        if not is_strict_true(field_data.get("passed")):
            return False
        if not verify_evidence_file(evidence_dir, field_data.get("file_path"), field_data.get("sha256")):
            return False
            
    if gate_name == "target_build" and scope == "systemui_full":
        signing_data = gate_data.get("legal_matching_signing_path", {})
        proof_type = signing_data.get("proof_type")
        if proof_type not in ["authorized_matching_signer_attestation", "reproducible_matching_signed_build"]:
            return False

    return True

def evaluate_evidence(evidence, evidence_dir):
    if not isinstance(evidence, dict):
        return 1, False, False, False

    scope = evidence.get("artifact_scope")
    if scope not in ["host_diagnostic", "hal_only", "systemui_full"]:
        return 1, False, False, False
        
    requested_gate = evidence.get("requested_gate")
    if scope == "host_diagnostic" and requested_gate != "host_diagnostic":
        return 1, False, False, False
    if requested_gate not in ["host_diagnostic", "target_build", "device_window"]:
        return 1, False, False, False
        
    host_pass = False
    target_pass = False
    device_pass = False

    host_pass = check_gate(evidence, "host_diagnostic", evidence_dir, scope)
    if host_pass and requested_gate in ["target_build", "device_window"]:
        target_pass = check_gate(evidence, "target_build", evidence_dir, scope)
    if target_pass and requested_gate == "device_window":
        device_pass = check_gate(evidence, "device_window", evidence_dir, scope)
        
    is_go = False
    if requested_gate == "host_diagnostic":
        is_go = host_pass
    elif requested_gate == "target_build":
        is_go = target_pass
    elif requested_gate == "device_window":
        is_go = device_pass
        
    return (0 if is_go else 2), host_pass, target_pass, device_pass

def process_evidence(evidence, evidence_dir):
    return evaluate_evidence(evidence, evidence_dir)[0]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if os.path.lexists(args.output):
        sys.exit(1)

    if not os.path.isfile(args.evidence):
        sys.exit(1)

    evidence_dir = os.path.dirname(os.path.abspath(args.evidence))
    try:
        with open(args.evidence, "r") as f:
            evidence = json.load(f)
    except Exception:
        sys.exit(1)

    exit_code, host_pass, target_pass, device_pass = evaluate_evidence(evidence, evidence_dir)
    
    try:
        with open(args.output, "x") as f:
            scope = evidence.get("artifact_scope") if isinstance(evidence, dict) else None
            requested = evidence.get("requested_gate") if isinstance(evidence, dict) else None
            json.dump({"exit_code": exit_code,
                       "status": "GO" if exit_code == 0 else "INVALID_INPUT" if exit_code == 1 else "NO_GO",
                       "artifact_scope": scope, "requested_gate": requested,
                       "gate_checks": {
                           "host_diagnostic": host_pass,
                           "target_build": target_pass,
                           "device_window": device_pass
                       },
                       "note": "File hashes bind reviewed evidence; this checker does not itself compile, sign or authorize deployment."}, f, indent=2)
    except Exception:
        sys.exit(1)
        
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
