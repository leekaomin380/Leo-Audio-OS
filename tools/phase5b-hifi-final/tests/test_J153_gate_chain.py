import unittest
import tempfile
import os
import json
import subprocess
import sys
import hashlib

class TestJ153GateChain(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.evidence_path = os.path.join(self.temp_dir.name, "evidence.json")
        self.output_path = os.path.join(self.temp_dir.name, "output.json")
        self.script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "hifi_readiness.py"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_file(self, filename, content=b"dummy"):
        filepath = os.path.join(self.temp_dir.name, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        return filename, hashlib.sha256(content).hexdigest()

    def test_global_host_pass_isolated_from_target(self):
        ev_file, ev_hash = self._create_file("dummy.log")
        data = {
            "artifact_scope": "systemui_full",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            },
            "target_build": {
                "full_target_manifest": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "baseline_build": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "resources_compatible": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "toolchain_provenance": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "target_artifact": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "legal_matching_signing_path": {
                    "passed": True,
                    "file_path": ev_file,
                    "sha256": ev_hash,
                    "proof_type": "reproducible_matching_signed_build"
                }
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        
        res = subprocess.run([sys.executable, self.script_path, "--evidence", self.evidence_path, "--output", self.output_path])
        self.assertEqual(res.returncode, 0)
        
        with open(self.output_path, "r") as f:
            out = json.load(f)
            
        self.assertTrue(out["gate_checks"]["host_diagnostic"])
        self.assertFalse(out["gate_checks"]["target_build"])

    def test_target_build_fails_if_host_fails(self):
        ev_file, ev_hash = self._create_file("dummy.log")
        data = {
            "artifact_scope": "systemui_full",
            "requested_gate": "target_build",
            "host_diagnostic": {},
            "target_build": {
                "full_target_manifest": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "baseline_build": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "resources_compatible": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "toolchain_provenance": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "target_artifact": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "legal_matching_signing_path": {
                    "passed": True,
                    "file_path": ev_file,
                    "sha256": ev_hash,
                    "proof_type": "authorized_matching_signer_attestation"
                }
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
            
        res = subprocess.run([sys.executable, self.script_path, "--evidence", self.evidence_path, "--output", self.output_path])
        self.assertEqual(res.returncode, 2)
        
        with open(self.output_path, "r") as f:
            out = json.load(f)
            
        self.assertFalse(out["gate_checks"]["host_diagnostic"])
        self.assertFalse(out["gate_checks"]["target_build"])

if __name__ == "__main__":
    unittest.main()
