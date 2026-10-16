# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import unittest
from tools.rpi5 import build_apple_ssh_buffers as builder


class AppleSSHBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=builder.build()

    def test_original_target_objects_config_archive_and_native_host_result(self):
        r=self.report
        self.assertEqual(r['upstream_commit'],builder.COMMIT);self.assertEqual(r['source_units'],list(builder.UNITS))
        self.assertTrue(r['actual_arm64_objects']);self.assertTrue(r['apple_config_unchanged'])
        self.assertTrue(r['openssl_policy_unchanged']);self.assertTrue(r['pam_and_sandbox_policy_unchanged'])
        self.assertIn('HOST_PASS',r['host_test_stdout']);self.assertFalse(r['stub_functions_added'])
        self.assertEqual(r['known_original_low_max_reset_failure']['returncode'],-11)
        self.assertFalse(r['known_original_low_max_reset_failure']['fixed'])

    def test_every_input_header_and_output_pin_and_explicit_limits(self):
        r=self.report
        for n,pin in (r['source_inputs_sha256']|r['headers_sha256']|r['generated_sha256']).items():
            self.assertEqual(builder.sha(Path(n)),pin,n)
        for field in ('full_ssh_or_sshd_built','pi_static_runtime_closed','crypto_runtime_linked',
            'pi_executed','installed','ethernet_or_ssh_proven','vm_sources_or_artifacts_modified','root_or_kernel_changed'):
            self.assertFalse(r[field],field)

    def test_runtime_inventory_is_measured_not_fabricated_closure(self):
        r=self.report;inventory=r['selected_archive_dependency_inventory']
        self.assertTrue(inventory['external_symbols']);self.assertTrue(inventory['absent_from_selected_runtime_archives'])
        self.assertEqual(set(inventory['external_symbols']),
            set(inventory['potential_runtime_providers'])|set(inventory['absent_from_selected_runtime_archives']))
        self.assertFalse(set(inventory['potential_runtime_providers'])&set(inventory['absent_from_selected_runtime_archives']))


if __name__=='__main__':unittest.main()
