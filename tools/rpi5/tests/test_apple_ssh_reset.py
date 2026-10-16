# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import unittest
from tools.rpi5 import build_apple_ssh_buffer_reset as builder


class AppleSSHResetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.report=builder.build()

    def test_exact_separate_source_overlay_and_original_pristine_baseline(self):
        r=self.report
        self.assertEqual(r['patched_unit'],'sshbuf.c');self.assertTrue(r['upstream_checkout_unchanged'])
        self.assertTrue(r['original_archive_and_failure_preserved']);self.assertTrue(r['apple_config_unchanged'])
        self.assertEqual(r['original_reproducer_before'],-11);self.assertEqual(r['same_original_reproducer_after'],7)
        self.assertTrue(r['corrected_target_objects']);self.assertFalse(r['production_stub_functions_added'])
        self.assertTrue(r['only_reset_body_changed']);self.assertTrue(r['production_definition_set_unchanged'])
        self.assertTrue(r['production_external_symbol_set_unchanged'])

    def test_real_capacity_zeroization_readonly_and_allocation_failure_cases(self):
        r=self.report;self.assertEqual(r['reset_capacities'],514);self.assertEqual(r['rounds_per_capacity'],3)
        self.assertTrue(r['zeroization_checked']);self.assertTrue(r['readonly_parent_behavior_checked'])
        self.assertIn('ALLOC_FAILURE=0',r['reset_host_test']);self.assertIn('ALLOC_FAILURE=1',r['allocation_fault_host_test'])
        self.assertIn('HOST_PASS',r['normal_host_test'])

    def test_every_actual_input_header_output_pin_and_scope(self):
        r=self.report
        for name,pin in (r['source_inputs_sha256']|r['headers_sha256']|r['generated_sha256']).items():
            self.assertEqual(builder.sha(Path(name)),pin,name)
        for field in ('crypto_runtime_linked','pi_static_runtime_closed','pi_executed','installed',
            'full_ssh_or_sshd_built','ethernet_or_ssh_proven','vm_or_pi_images_changed'):
            self.assertFalse(r[field],field)


if __name__=='__main__':unittest.main()
