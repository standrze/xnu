#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Tests for the sealed OpenSSH safe-leaf frontier."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import check_apple_ssh_leaf_frontier as gate


class AppleOpenSSHLeafFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = gate.audit()

    def test_exact_33_import_partition_has_no_admissible_leaf(self):
        self.assertEqual(self.report["remaining_count"], 33)
        flattened = [symbol for values in self.report["ownership"].values() for symbol in values]
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(sorted(flattened), gate.EXPECTED_MISSING)
        self.assertEqual(self.report["admissible_leafs"], [])
        self.assertEqual(self.report["ownership"]["stdio_process_pair"], ["_pclose", "_popen"])

    def test_exact_apple_archives_sources_and_semantic_evidence(self):
        gate.verify_sources()
        self.assertEqual(gate.sha256(gate.OLD_ARCHIVE), gate.OLD_PIN["archive_sha256"])
        self.assertEqual(gate.sha256(gate.OLD_SOURCE), gate.OLD_PIN["source_sha256"])
        self.assertEqual(gate.sha256(gate.CURRENT_ARCHIVE), gate.CURRENT_PIN["archive_sha256"])
        self.assertEqual(gate.sha256(gate.CURRENT_SOURCE), gate.CURRENT_PIN["source_sha256"])
        for pattern in gate.OLD_REQUIRED:
            self.assertIn(pattern, gate.OLD_SOURCE.read_text())
        for pattern in gate.CURRENT_REQUIRED:
            self.assertIn(pattern, gate.CURRENT_SOURCE.read_text())

    def test_real_old_popen_probe_closes_pair_but_adds_vfork(self):
        probe = self.report["popen_boundary"]["old_source_probe"]
        self.assertEqual(probe["object_exports"], ["_pclose", "_popen"])
        self.assertEqual(probe["closed_imports"], ["_pclose", "_popen"])
        self.assertEqual(probe["new_imports"], ["_vfork"])
        self.assertEqual(probe["duplicate_symbols"], [])
        self.assertEqual(probe["remaining_count"], 32)
        self.assertIn("_vfork", probe["object_undefined"])

    def test_semantic_downgrades_and_facades_are_rejected(self):
        self.assertFalse(self.report["popen_boundary"]["old_source_admissible"])
        self.assertFalse(self.report["popen_boundary"]["current_source_admissible"])
        self.assertFalse(any(self.report["forbidden_shortcuts"].values()))
        for mutation in self.report["forbidden_shortcuts"]:
            bad = copy.deepcopy(self.report)
            bad["forbidden_shortcuts"][mutation] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["admissible_leafs"] = ["_popen"]
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["popen_boundary"]["old_source_admissible"] = True
        with self.assertRaises(ValueError):
            gate.validate_report(bad)

    def test_cli_retains_identical_default_off_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "leaf-frontier.json"
            process = subprocess.run(
                [str(Path(gate.__file__)), "--output", str(output)],
                cwd=gate.ROOT, text=True, capture_output=True, timeout=60,
            )
            self.assertEqual(process.returncode, 2)
            self.assertEqual(process.stderr, "")
            self.assertEqual(json.loads(output.read_text()), self.report)
            self.assertEqual(json.loads(process.stdout), self.report)


if __name__ == "__main__":
    unittest.main()
