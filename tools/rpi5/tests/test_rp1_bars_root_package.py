# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_rp1_bars_root_package as checker


class BarsPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_BARS_ROOT_PACKAGE']).resolve();cls.path=cls.p/'manifest.json'
        cls.m=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.p)

    def reject(self,change,reason):
        m=copy.deepcopy(self.m);change(m);read=Path.read_text
        def injected(p,*a,**kw):return json.dumps(m) if p==self.path else read(p,*a,**kw)
        with patch.object(Path,'read_text',injected),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.p)

    def test_actual_native_device_full_fdt_single_cpu_zero_input(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['bars_package_checks'].values()))
        self.assertEqual(self.report['bootargs'],'serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress cpus=1')
        self.assertFalse(self.report['serial_input_allowed']);self.assertEqual(self.report['trace_contract']['max_scalar_arguments'],15)

    def test_complete_generated_header_and_ordered_identity(self):
        self.reject(lambda m:m['generated_sha256'].pop(str(self.p/'probe_main.o')),'complete_generated_closure')
        self.reject(lambda m:m['headers_sha256'].clear(),'complete_header_closure')
        self.reject(lambda m:m['boot_markers'].reverse(),'ordered_boot_markers')

    def test_bar_or_logging_or_deadline_expansion_refused(self):
        for key,value in (('endpoint_writes_max',13),('command_writes',1),('bar_mmio_mapped',True),('assignment_performed',True)):
            self.reject(lambda m:m['bars_contract'].update({key:value}),'exact_bars')
        self.reject(lambda m:m['trace_contract'].update(reject_faults_through_normal_return=False),'actual_bounded_logging')
        self.reject(lambda m:m['watchdog'].update(transfer_to_bootsys_bound_seconds=999),'exact_watchdog')


if __name__=='__main__':unittest.main()
