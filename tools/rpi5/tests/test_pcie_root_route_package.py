# SPDX-License-Identifier: BSD-2-Clause
"""Actual root-route package plus exact closure, route/deadline negatives."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_root_route_package as checker


class RootRoutePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_ROOT_ROUTE_PACKAGE']).resolve();cls.path=cls.p/'manifest.json'
        cls.m=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.p)

    def reject(self,change,reason):
        m=copy.deepcopy(self.m);change(m);read=Path.read_text
        def injected(p,*a,**kw):return json.dumps(m) if p==self.path else read(p,*a,**kw)
        with patch.object(Path,'read_text',injected),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.p)

    def test_complete_native_noinput_pair(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['root_route_checks'].values()))
        self.assertEqual(self.report['bootargs'],'serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress cpus=1')
        self.assertFalse(self.report['serial_input_allowed'])
        self.assertEqual(self.report['root_route']['root_writes_max'],1)

    def test_omitted_generated_closure(self):
        self.reject(lambda m:m['generated_sha256'].pop(str(self.p/'probe_main.o')),'complete_generated_closure')

    def test_omitted_header_closure(self):
        self.reject(lambda m:m['headers_sha256'].clear(),'complete_header_closure')

    def test_route_permissions_or_values_or_physical_claim_changed(self):
        for key,value in (('root_writes_max',2),('root_write_offset',4),('low24_value',0xff0100),
            ('post_link_readback',False),('physical_cause_proven',True),('endpoint_writes',1)):
            self.reject(lambda m:m['root_route'].update({key:value}),'exact_root_route')

    def test_changed_watchdog(self):
        self.reject(lambda m:m['watchdog'].update(transfer_to_bootsys_bound_seconds=999),'exact_watchdog')

    def test_changed_trace_or_order(self):
        self.reject(lambda m:m['trace_contract'].update(extra_mmio=True),'actual_end_telemetry')
        self.reject(lambda m:m['boot_markers'].reverse(),'ordered_boot_markers')


if __name__=='__main__':unittest.main()
