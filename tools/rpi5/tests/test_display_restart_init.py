# SPDX-License-Identifier: BSD-2-Clause
"""Actual source/package closure and root-only mutation negatives."""
import copy
import json
import os
import types
from pathlib import Path
from unittest import mock
import unittest
from tools.rpi5 import check_display_restart_init as c

class DisplayRestartInitTests(unittest.TestCase):
    def setUp(self):
        value=os.environ.get('RPI5_RESTART_INIT_PACKAGE');self.pin=os.environ.get('RPI5_RESTART_INIT_MANIFEST_SHA256')
        if not value or not self.pin:self.fail('Supply exact saved PID1 successor package and SHA')
        self.p=Path(value).resolve()
    def test_actual_byte_checker_root_and_kernel_with_no_compile(self):
        with mock.patch('subprocess.run',side_effect=AssertionError('No compiler')):r=c.inspect(self.p,self.pin)
        self.assertEqual(r['root_only_replaced'],'/sbin/launchd')
        self.assertFalse(r['copy_phase_contract']['kernel_root_payload_unchanged'])
        self.assertTrue(all(r['init_shutdown_checks'].values()))
        self.assertFalse(r['physical_psci_causality_proven'])
    def test_exact_contract_and_closure_mutations(self):
        original=c.b.document
        for field,value in [('root_only_replaced','/bin/sh'),('root_nodes',True),('copy_phase_contract',c.b.prior.CONTRACT),('init_shutdown_ready_marker','')]:
            def altered(path):
                m=original(path)
                if Path(path)==self.p/'manifest.json':m[field]=value
                return m
            with self.subTest(field=field),mock.patch.object(c.b,'document',side_effect=altered),self.assertRaises(ValueError):c.inspect(self.p,self.pin)
        for key in ('inputs_sha256','headers_sha256','generated_sha256','compiler_scans'):
            def omitted(path):
                m=original(path)
                if Path(path)==self.p/'manifest.json':m[key].pop(next(iter(m[key])))
                return m
            with self.subTest(key=key),mock.patch.object(c.b,'document',side_effect=omitted),self.assertRaises(ValueError):c.inspect(self.p,self.pin)

    def test_actual_native_materialization_new_root(self):
        from tools.rpi5 import display_restart_native as native
        view=types.SimpleNamespace(inspect=c.inspect,b=c.b.prior.prior.original)
        fn=types.FunctionType(native.inspect.__code__,dict(vars(native),check=view),argdefs=native.inspect.__defaults__)
        result=fn(self.p)
        self.assertTrue(result['exact_same_image_bytes']);self.assertFalse(result['target_executed'])

if __name__=='__main__':unittest.main()
