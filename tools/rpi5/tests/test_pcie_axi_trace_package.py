# SPDX-License-Identifier: BSD-2-Clause
"""Fresh immutable-package audit and fail-closed metadata mutations."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_axi_trace_package as checker


class AXITracePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_AXI_TRACE_PACKAGE']).resolve();cls.path=cls.p/'manifest.json'
        cls.m=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.p)

    def reject(self,change,reason):
        m=copy.deepcopy(self.m);change(m);read=Path.read_text
        def injected(p,*a,**kw):return json.dumps(m) if p==self.path else read(p,*a,**kw)
        with patch.object(Path,'read_text',injected),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.p)

    def test_complete_native_noinput_pair(self):
        self.assertTrue(all(self.report['checks'].values()))
        self.assertTrue(all(self.report['axi_trace_checks'].values()))
        self.assertEqual(self.report['bootargs'],'serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress cpus=1')
        self.assertFalse(self.report['serial_input_allowed'])

    def test_omitted_generated_closure(self):
        self.reject(lambda m:m['generated_sha256'].pop(str(self.p/'probe_main.o')),'complete_generated_closure')

    def test_omitted_header_closure(self):
        self.reject(lambda m:m['headers_sha256'].clear(),'complete_header_closure')

    def test_changed_fallback_contract(self):
        self.reject(lambda m:m['axi_correction'].update(fallback_max_outstanding=63),'exact_axi_correction')

    def test_changed_watchdog(self):
        self.reject(lambda m:m['watchdog'].update(transfer_to_bootsys_bound_seconds=999),'exact_watchdog')

    def test_changed_trace_end(self):
        self.reject(lambda m:m['trace_contract'].update(extra_mmio=True),'actual_end_telemetry')

    def test_changed_order(self):
        self.reject(lambda m:m['boot_markers'].reverse(),'ordered_boot_markers')


if __name__=='__main__':unittest.main()
