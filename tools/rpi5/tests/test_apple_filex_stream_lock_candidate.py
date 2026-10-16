#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Focused current-Apple FILEX stream-lock candidate tests."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.rpi5 import build_apple_filex_stream_lock_candidate as candidate


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "build/rpi5/apple-filex-stream-lock-3gixnms6"


class AppleFILEXStreamLockCandidateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = Path(tempfile.mkdtemp(prefix="filex-candidate-test-", dir=ROOT / "build/rpi5"))
        self.package = self.temporary / "package"
        shutil.copytree(PACKAGE, self.package)
        manifest = json.loads((self.package / "manifest.json").read_text())
        old = str(PACKAGE)
        new = str(self.package)
        manifest["target"] = manifest["target"].replace(old, new)
        manifest["license_copy"] = manifest["license_copy"].replace(old, new)
        manifest["generated_sha256"] = {
            name.replace(old, new): digest
            for name, digest in manifest["generated_sha256"].items()
        }
        (self.package / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )

    def tearDown(self):
        shutil.rmtree(self.temporary)

    def manifest(self):
        return json.loads((self.package / "manifest.json").read_text())

    def write_manifest(self, document):
        (self.package / "manifest.json").write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n"
        )

    def test_exact_package_is_closed_but_default_off(self):
        report = candidate.check(self.package)
        self.assertTrue(report["target_zero_undefined"])
        self.assertTrue(report["current_file_abi_only"])
        self.assertFalse(report["legacy_file_abi_mixed"])
        self.assertFalse(report["gate_open"])
        self.assertFalse(report["target_executed"])
        self.assertEqual(
            report["next_prerequisite"],
            "target FILEX recursive-lock/orientation execution trial",
        )
        owners = report["live_symbol_owners"]
        self.assertIn("target-flock.o", owners["_flockfile"])
        self.assertIn("target-fwide.o", owners["_fwide"])
        self.assertIn(
            "libapple-pthread-platform-scoped.a", owners["_pthread_mutex_lock"]
        )

    def test_gate_open_claim_is_rejected(self):
        report = self.manifest()
        report["gate_open"] = True
        self.write_manifest(report)
        with self.assertRaisesRegex(ValueError, "evidence boundary"):
            candidate.check(self.package)

    def test_host_result_cannot_be_promoted_to_target_evidence(self):
        report = self.manifest()
        report["host_oracle"]["target_evidence"] = True
        self.write_manifest(report)
        with self.assertRaisesRegex(ValueError, "host/target"):
            candidate.check(self.package)

    def test_target_mutation_is_rejected(self):
        target = Path(self.manifest()["target"])
        target.write_bytes(target.read_bytes() + b"mutation")
        with self.assertRaisesRegex(ValueError, "target drift"):
            candidate.check(self.package)

    def test_legacy_file_abi_map_input_is_rejected(self):
        mapping = self.package / "target.map"
        mapping.write_text(mapping.read_text() + "\nprivate-apple-runtime.a\n")
        with self.assertRaisesRegex(ValueError, "legacy FILE ABI"):
            candidate.check(self.package)

    def test_license_mutation_is_rejected(self):
        license_path = self.package / "APPLE_LICENSE"
        license_path.write_text(license_path.read_text() + "\nmutation\n")
        with self.assertRaisesRegex(ValueError, "generated artifact drift|license receipt drift"):
            candidate.check(self.package)


if __name__ == "__main__":
    unittest.main()
