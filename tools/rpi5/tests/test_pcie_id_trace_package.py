# SPDX-License-Identifier: BSD-2-Clause
"""Read-only exact-package mutations. Never rewrite any candidate file."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_id_trace_package as c


class PCIeIDTracePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_PCIE_TRACE_PACKAGE']).resolve()
        cls.manifest=cls.package/'manifest.json'
        cls.original=json.loads(cls.manifest.read_text())
        cls.actual=c.inspect(cls.package)

    def reject(self,mutate,reason):
        record=copy.deepcopy(self.original);mutate(record);read=Path.read_text
        def injected(path,*args,**kwargs):
            return json.dumps(record) if path==self.manifest else read(path,*args,**kwargs)
        # Keep actual dependency/ELF/closure/native checks; no cached admission.
        with patch.object(Path,'read_text',injected):
            with self.assertRaisesRegex(ValueError,reason):c.inspect(self.package)

    def test_actual_trace_pair(self):
        self.assertTrue(self.actual['preflight_pass'])
        self.assertTrue(all(self.actual['checks'].values()))
        self.assertTrue(all(self.actual['trace_checks'].values()))
        self.assertFalse(self.actual['serial_input_allowed'])

    def test_omitted_generated_pin(self):
        self.reject(lambda m:m['generated_sha256'].pop(str(self.package/'probe_main.o')),'complete_generated_closure')

    def test_omitted_header_pin(self):
        self.reject(lambda m:m['headers_sha256'].pop(next(iter(m['headers_sha256']))),'complete_header_closure')

    def test_missing_trace_contract(self):
        self.reject(lambda m:m.pop('trace_contract'),'actual_end_telemetry')

    def test_changed_watchdog_bound(self):
        self.reject(lambda m:m['watchdog'].update(transfer_to_bootsys_bound_seconds=999),'exact_watchdog')

    def test_reordered_boot_markers(self):
        self.reject(lambda m:m['boot_markers'].reverse(),'ordered_boot_markers')


if __name__=='__main__':unittest.main()
