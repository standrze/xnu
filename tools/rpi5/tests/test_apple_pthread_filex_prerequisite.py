# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import tempfile
import unittest

from tools.rpi5 import build_apple_pthread_filex_prerequisite as gate


class ApplePthreadFilexPrerequisiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.report = gate.build()

    def test_gate_is_default_off_with_exact_target_blockers(self):
        self.assertTrue(self.report['default_off'])
        self.assertFalse(self.report['gate_open'])
        self.assertFalse(self.report['admitted'])
        self.assertFalse(self.report['filex_popen_admission_allowed'])
        self.assertEqual(
            {name for name, value in self.report['target_semantics_qualified'].items() if not value},
            {'recursive_mutex', 'atfork_fork', 'cancellation_boundaries'})

    def test_existing_physical_evidence_is_narrow(self):
        evidence = self.report['existing_target_evidence']
        for name in ('create_join', 'mutex_contention', 'errno_tls',
                     'tsd_destructors', 'pthread_once', 'scope_exact'):
            self.assertTrue(evidence[name])
        for name in ('recursive_mutex', 'atfork_fork', 'deferred_cancellation'):
            self.assertFalse(evidence[name])
        self.assertTrue(self.report['rejected_trial']['contributes_no_positive_evidence'])

    def test_host_oracle_is_not_target_evidence(self):
        oracle = self.report['host_oracle']
        self.assertTrue(all(oracle['behaviors'].values()))
        self.assertTrue(oracle['host_pthread_only'])
        self.assertFalse(oracle['target_evidence'])
        self.assertIn('HOST_ONLY', oracle['stdout'])

    def test_current_apple_sources_and_exports_own_the_apis(self):
        self.assertTrue(all(c['present'] for c in self.report['source_contracts'].values()))
        self.assertEqual(self.report['missing_required_exports'], [])
        self.assertTrue(set(self.report['required_exports']).issubset(
            self.report['archive_exports']['scoped']))
        self.assertTrue(self.report['kernel_ownership']['source_presence_only'])
        self.assertFalse(self.report['kernel_ownership']['target_behavior_qualified'])
        self.assertTrue(self.report['current_compile_variant']['variant_static'])
        self.assertFalse(self.report['current_compile_variant']['variant_cancelable'])

    def test_checker_rejects_a_manufactured_open_gate(self):
        with tempfile.TemporaryDirectory(dir=gate.ROOT / 'build/rpi5') as raw:
            copy = Path(raw)
            manifest = json.loads((self.package / 'manifest.json').read_text())
            manifest['gate_open'] = True
            (copy / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'may not open'):
                gate.check(copy)

    def test_checker_accepts_exact_package(self):
        checked = gate.check(self.package)
        self.assertEqual(checked['profile'], gate.PROFILE)


if __name__ == '__main__':
    unittest.main()
