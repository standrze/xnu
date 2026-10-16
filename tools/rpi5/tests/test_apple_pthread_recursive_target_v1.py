# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.rpi5 import build_apple_pthread_recursive_target_v1 as target


class ApplePthreadRecursiveTargetV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package, cls.report = target.build()

    def mutate(self, callback):
        with tempfile.TemporaryDirectory(dir=target.ROOT / 'build/rpi5') as raw:
            copy = Path(raw) / 'package'
            shutil.copytree(self.package, copy)
            manifest = json.loads((copy / 'manifest.json').read_text())
            callback(manifest)
            (copy / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            return target.check(copy)

    def test_target_candidate_is_closed_linked_but_not_qualified(self):
        self.assertTrue(self.report['target_link_complete'])
        self.assertEqual(self.report['target_undefined_symbols'], [])
        self.assertTrue(self.report['recursive_mutex_stage']['implementation_linked'])
        self.assertTrue(self.report['recursive_mutex_stage']['genuine_current_apple_owners'])
        self.assertFalse(self.report['recursive_mutex_stage']['target_execution'])
        self.assertFalse(self.report['recursive_mutex_stage']['target_behavior_qualified'])
        for field in ('gate_open', 'admitted', 'filex_popen_admission_allowed',
                      'target_image_installed', 'pi_executed'):
            self.assertFalse(self.report[field])

    def test_live_apis_have_exact_genuine_apple_owners(self):
        self.assertEqual(set(self.report['target_api_owners']), set(target.API_OWNERS))
        for symbol, member in target.API_OWNERS.items():
            self.assertTrue(self.report['target_api_owners'][symbol].endswith(f'({member})'))

    def test_behavior_contract_covers_depth_ownership_and_release(self):
        contract = self.report['source_contract']
        self.assertTrue(contract['checks_depth_three'])
        self.assertTrue(contract['checks_foreign_owner'])
        self.assertTrue(contract['checks_partial_release_still_busy'])
        self.assertTrue(contract['checks_final_release'])
        self.assertEqual(self.report['host_oracle']['stdout'], target.HOST_LINE)
        self.assertTrue(self.report['host_oracle']['host_pthread_only'])
        self.assertFalse(self.report['host_oracle']['target_evidence'])

    def test_checker_rejects_manufactured_gate_open(self):
        with self.assertRaisesRegex(ValueError, 'closed recursive prerequisite'):
            self.mutate(lambda manifest: manifest.__setitem__('gate_open', True))

    def test_checker_rejects_manufactured_target_execution(self):
        def change(manifest):
            manifest['recursive_mutex_stage']['target_execution'] = True
            manifest['recursive_mutex_stage']['target_behavior_qualified'] = True
        with self.assertRaisesRegex(ValueError, 'readiness/qualification boundary'):
            self.mutate(change)

    def test_checker_rejects_promoted_host_oracle(self):
        with self.assertRaisesRegex(ValueError, 'host behavior oracle'):
            self.mutate(lambda manifest: manifest['host_oracle'].__setitem__('target_evidence', True))

    def test_checker_rejects_source_receipt_mutation(self):
        def change(manifest):
            manifest['source_inputs_sha256'][str(target.SOURCE)] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'source receipts'):
            self.mutate(change)

    def test_checker_rejects_owner_mutation(self):
        def change(manifest):
            manifest['target_api_owners']['_pthread_mutex_lock'] = 'fake.a(fake.o)'
        with self.assertRaisesRegex(ValueError, 'API owner changed'):
            self.mutate(change)

    def test_checker_rejects_generated_binary_mutation(self):
        with tempfile.TemporaryDirectory(dir=target.ROOT / 'build/rpi5') as raw:
            copy = Path(raw) / 'package'
            shutil.copytree(self.package, copy)
            with (copy / 'NOT_RUN_recursive_mutex_target').open('ab') as stream:
                stream.write(b'X')
            with self.assertRaisesRegex(ValueError, 'generated recursive target evidence drift'):
                target.check(copy)

    def test_checker_accepts_exact_package(self):
        checked = target.check(self.package)
        self.assertEqual(checked['profile'], target.PROFILE)


if __name__ == '__main__':
    unittest.main()
