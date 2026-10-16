#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Tests for the Apple OpenSSH resolver/Libinfo ownership gate."""

import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5 import check_apple_ssh_resolver_gate as gate


class AppleOpenSSHResolverGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = gate.audit()

    def test_exact_sealed_import_partition(self):
        self.assertEqual(self.report["remaining_count"], 35)
        flattened = [symbol for values in self.report["ownership"].values() for symbol in values]
        self.assertEqual(len(flattened), len(set(flattened)))
        self.assertEqual(sorted(flattened), gate.EXPECTED_MISSING)
        self.assertEqual(
            self.report["selected_tranche"]["imports"],
            ["___res_9_state", "_res_9_init", "_res_9_query"],
        )

    def test_exact_apple_source_commits_hashes_and_semantic_evidence(self):
        self.assertEqual(self.report["apple_source_commits"], {
            "apple-libresolv": gate.LIBRESOLV_COMMIT,
            "apple-Libinfo": gate.LIBINFO_COMMIT,
            "apple-libnotify": gate.LIBNOTIFY_COMMIT,
            "apple-configd": gate.CONFIGD_COMMIT,
            "apple-OpenSSH": gate.OPENSSH_COMMIT,
        })
        self.assertEqual(
            self.report["apple_source_sha256"],
            {name: digest for name, (_, digest) in gate.SOURCE_PINS.items()},
        )
        for name, (path, digest) in gate.SOURCE_PINS.items():
            with self.subTest(name=name):
                self.assertEqual(gate.sha256(path), digest)
                text = path.read_text()
                for pattern in gate.REQUIRED_PATTERNS.get(name, []):
                    self.assertIn(pattern, text)

    def test_gate_preserves_semantics_and_rejects_facades(self):
        self.assertFalse(self.report["selected_tranche"]["admissible"])
        self.assertFalse(self.report["libinfo_destination"]["admissible"])
        self.assertEqual(self.report["libinfo_destination"]["replacement"], "none")
        self.assertFalse(any(self.report["forbidden_shortcuts"].values()))
        self.assertTrue(self.report["preservation"]["features_unchanged"])
        self.assertTrue(self.report["preservation"]["pam_enabled"])
        self.assertTrue(self.report["preservation"]["kerberos_gss_enabled"])
        for mutation in ("static_res_state_facade", "res_init_noop", "dnsservice_stub", "notify_stub", "configd_stub", "no_dependencies_comparator_alias", "feature_disabling"):
            bad = copy.deepcopy(self.report)
            bad["forbidden_shortcuts"][mutation] = True
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                gate.validate_report(bad)

    def test_omission_and_false_admission_controls(self):
        bad = copy.deepcopy(self.report)
        bad["ownership"]["resolver_transport"].pop()
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["selected_tranche"]["prerequisites"].pop()
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["selected_tranche"]["admissible"] = True
        with self.assertRaises(ValueError):
            gate.validate_report(bad)
        bad = copy.deepcopy(self.report)
        bad["libinfo_destination"]["replacement"] = "si_destination_compare_no_dependencies"
        with self.assertRaises(ValueError):
            gate.validate_report(bad)

    def test_cli_retains_same_failing_admission_report(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "resolver-gate.json"
            process = subprocess.run(
                [str(Path(gate.__file__)), "--output", str(output)],
                cwd=gate.ROOT,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(process.returncode, 2)
            self.assertEqual(process.stderr, "")
            self.assertEqual(json.loads(output.read_text()), self.report)
            self.assertEqual(json.loads(process.stdout), self.report)


if __name__ == "__main__":
    unittest.main()
