#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Negative admission controls for the genuine Apple notify service path."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import check_apple_ssh_notify_gate as gate


class AppleOpenSSHNotifyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = gate.audit()

    def test_exact_predecessor_and_complete_api_family(self):
        self.assertEqual(gate.sha256(gate.RESOLVER_REPORT), gate.RESOLVER_REPORT_SHA256)
        predecessor = json.loads(gate.RESOLVER_REPORT.read_text())
        self.assertEqual(self.report["current_unresolved_imports"], ["_notify_check", "_notify_register_check"])
        self.assertTrue(set(self.report["current_unresolved_imports"]).issubset(predecessor["remaining_imports"]))
        self.assertEqual(self.report["required_api_closure"], sorted(self.report["required_api_closure"]))
        self.assertEqual(
            set(self.report["required_api_closure"]) - set(self.report["current_unresolved_imports"]),
            set(self.report["newly_reachable_if_partial"]),
        )

    def test_exact_unchanged_apple_sources_and_service_evidence(self):
        self.assertEqual(
            subprocess.check_output(["git", "-C", gate.SOURCE, "rev-parse", "HEAD"], text=True).strip(),
            gate.COMMIT,
        )
        self.assertEqual(self.report["apple_source_sha256"], gate.SOURCE_PINS)
        for relative, digest in gate.SOURCE_PINS.items():
            with self.subTest(relative=relative):
                path = gate.SOURCE / relative
                self.assertEqual(gate.sha256(path), digest)
                self.assertEqual(path.read_bytes(), subprocess.check_output(["git", "-C", gate.SOURCE, "show", f"{gate.COMMIT}:{relative}"]))
                text = path.read_text()
                for pattern in gate.REQUIRED_PATTERNS.get(relative, []):
                    self.assertIn(pattern, text)

    def test_public_sdk_stops_at_real_private_build_inputs(self):
        probe = self.report["compile_probe"]
        self.assertEqual(probe["units"], {
            "notify_client.c": {"returncode": 1, "first_missing_private_header": "bootstrap_priv.h"},
            "libnotify.c": {"returncode": 1, "first_missing_private_header": "os/lock_private.h"},
        })
        self.assertEqual(gate.sha256(Path(probe["compiler"])), probe["compiler_sha256"])

    def test_default_off_and_no_service_facades(self):
        self.assertFalse(self.report["admissible"])
        self.assertFalse(self.report["provider_created"])
        self.assertFalse(any(self.report["forbidden_shortcuts"].values()))
        for shortcut in self.report["forbidden_shortcuts"]:
            bad = copy.deepcopy(self.report)
            bad["forbidden_shortcuts"][shortcut] = True
            with self.subTest(shortcut=shortcut), self.assertRaises(ValueError):
                gate.validate_report(bad)

    def test_omission_false_admission_and_boundary_controls(self):
        bad = copy.deepcopy(self.report)
        bad["required_api_closure"].pop()
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["prerequisites"].pop()
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["admissible"] = True
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["preservation"]["target_executed"] = True
        with self.assertRaises(ValueError):
            gate.validate_report(bad)

    def test_cli_retains_identical_default_off_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "notify-gate.json"
            proc = subprocess.run(
                [str(Path(gate.__file__)), "--output", str(output)],
                cwd=gate.ROOT, text=True, capture_output=True, timeout=30,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(proc.stderr, "")
            self.assertEqual(json.loads(proc.stdout), self.report)
            self.assertEqual(json.loads(output.read_text()), self.report)


if __name__ == "__main__":
    unittest.main()
