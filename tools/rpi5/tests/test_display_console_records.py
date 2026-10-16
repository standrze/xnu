# SPDX-License-Identifier: BSD-2-Clause
"""Exact new linked composition, no hardware or target-execution claim."""
import os
from pathlib import Path
import types
import unittest
from unittest import mock
from tools.rpi5 import check_display_console_records as c

class DisplayConsoleRecordTests(unittest.TestCase):
    def setUp(self):
        value=os.environ.get('RPI5_CONSOLE_RECORD_PACKAGE');self.pin=os.environ.get('RPI5_CONSOLE_RECORD_MANIFEST_SHA256')
        if not value or not self.pin:self.fail('Supply exact console-record package and manifest pin')
        self.package=Path(value).resolve()
    def test_actual_byte_only_full_link_root_and_guard_admission(self):
        with mock.patch('subprocess.run',side_effect=AssertionError('No compiler')):report=c.inspect(self.package,self.pin)
        self.assertTrue(all(report['checks'].values()));self.assertFalse(report['target_executed'])
        self.assertFalse(report['copy_phase_contract']['kernel_unchanged'])
        self.assertFalse(report['physical_psci_causality_proven'])
        self.assertEqual(report['init_shutdown_ready_marker'],c.b.profile.READY)
    def test_omission_type_and_owner_mutations_fail_closed(self):
        original=c.b.document
        mutations=[('root_nodes',True),('image_bytes',float((self.package/'probe.bin').stat().st_size)),
            ('console_record_contract',{**c.b.CONTRACT,'terminal_seconds':181}),('init_shutdown_ready_marker',c.b.profile.OLD_READY),
            ('init_shutdown_ready_max_reports',True),('kernel_replacements',{}),('target_inspection',{})]
        for key,value in mutations:
            def altered(path):
                m=original(path)
                if Path(path)==self.package/'manifest.json':m[key]=value
                return m
            with self.subTest(key=key),mock.patch.object(c.b,'document',side_effect=altered),self.assertRaises(ValueError):c.inspect(self.package,self.pin)
        for key in ('inputs_sha256','generated_sha256','headers_sha256','compiler_scans'):
            def altered(path):
                m=original(path)
                if Path(path)==self.package/'manifest.json':m[key].pop(next(iter(m[key])))
                return m
            with self.subTest(key=key),mock.patch.object(c.b,'document',side_effect=altered),self.assertRaises((ValueError,KeyError)):c.inspect(self.package,self.pin)
    def test_actual_native_loader_materializes_new_kernel_and_root(self):
        from tools.rpi5 import display_restart_native as native
        view=types.SimpleNamespace(inspect=c.inspect,b=c.b.diagnostic.original)
        fn=types.FunctionType(native.inspect.__code__,dict(vars(native),check=view),argdefs=native.inspect.__defaults__)
        report=fn(self.package);self.assertTrue(report['exact_same_image_bytes']);self.assertFalse(report['target_executed'])

if __name__=='__main__':unittest.main()
