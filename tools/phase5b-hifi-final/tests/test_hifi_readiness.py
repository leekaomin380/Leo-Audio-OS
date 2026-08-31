import unittest
import tempfile
import os
import json
import subprocess
import sys
import hashlib

class TestHiFiReadiness(unittest.TestCase):
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
        sha256 = hashlib.sha256(content).hexdigest()
        return filename, sha256
        
    def _run_checker(self):
        result = subprocess.run([sys.executable, self.script_path, "--evidence", self.evidence_path, "--output", self.output_path], capture_output=True)
        return result.returncode

    def test_symlink_directory_rejected(self):
        from pathlib import Path
        sys.path.insert(0, str(Path(self.script_path).parent))
        import hifi_readiness as m
        root=Path(self.temp_dir.name).resolve();(root/'real').mkdir()
        (root/'real/proof').write_bytes(b'proof');(root/'alias').symlink_to(root/'real',target_is_directory=True)
        self.assertFalse(m.verify_evidence_file(str(root),'alias/proof',hashlib.sha256(b'proof').hexdigest()))

    def test_diagnostic_scope_cannot_be_target(self):
        from pathlib import Path
        sys.path.insert(0, str(Path(self.script_path).parent))
        import hifi_readiness as m
        self.assertEqual(m.process_evidence({'artifact_scope':'host_diagnostic','requested_gate':'target_build'},self.temp_dir.name),1)

    def test_output_exists_no_overwrite(self):
        with open(self.evidence_path, "w") as f:
            f.write("{}")
        with open(self.output_path, "w") as f:
            f.write("{}")
        self.assertEqual(self._run_checker(), 1)

    def test_invalid_json(self):
        with open(self.evidence_path, "w") as f:
            f.write("{invalid}")
        self.assertEqual(self._run_checker(), 1)
        
    def test_synthetic_positive_host_diagnostic(self):
        # All examples clearly marked synthetic
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 0)

    def test_negative_type_false_string(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": "false", "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)
        
    def test_negative_type_1(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": 1, "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_missing_field(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_hash_mismatch(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": ev_file, "sha256": "badhash"},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_path_traversal(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": "../evidence.json", "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_symlink(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        sym_file = "synthetic_sym.log"
        os.symlink(os.path.join(self.temp_dir.name, ev_file), os.path.join(self.temp_dir.name, sym_file))
        data = {
            "artifact_scope": "host_diagnostic",
            "requested_gate": "host_diagnostic",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": sym_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_only_public_key_as_proof(self):
        ev_file, ev_hash = self._create_file("synthetic_target.log")
        data = {
            "artifact_scope": "systemui_full",
            "requested_gate": "target_build",
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
                    "proof_type": "public_key_match_only"
                }
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

    def test_negative_host_pass_not_upgrade_device(self):
        ev_file, ev_hash = self._create_file("synthetic_host.log")
        data = {
            "artifact_scope": "systemui_full",
            "requested_gate": "device_window",
            "host_diagnostic": {
                "source_frozen": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "host_tests": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "elf_closure": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "feature_off_equal": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "repeatable": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)
        
    def test_negative_no_go_device(self):
        ev_file, ev_hash = self._create_file("synthetic_target.log")
        data = {
            "artifact_scope": "systemui_full",
            "requested_gate": "device_window",
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
                    "proof_type": "actual_signing_service_log"
                }
            },
            "device_window": {
                "offline_fs_audit": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "rollback_verified": {"passed": True, "file_path": ev_file, "sha256": ev_hash},
                "device_preflight_fresh": {"passed": True, "file_path": ev_file, "sha256": ev_hash}
            }
        }
        with open(self.evidence_path, "w") as f:
            json.dump(data, f)
        self.assertEqual(self._run_checker(), 2)

if __name__ == "__main__":
    unittest.main()
