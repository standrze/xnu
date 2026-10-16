# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_decode_cycle_package as checker


class DecodeCyclePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_DECODE_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_six_device_pages_retained_fdt_and_loader(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['decode_package_checks'].values()))
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],25)
        self.assertTrue(self.report['decode_contract']['endpoint_memory_decode_temporarily_enabled'])
        self.assertFalse(self.report['decode_contract']['endpoint_register_access'])
        self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],6)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])

    def test_permission_and_generated_closure_mutations_rejected(self):
        contract=copy.deepcopy(self.manifest['decode_contract']);contract['command_changed_bits']=6
        self.reject('decode_contract',contract,'exact_decode')
        record=copy.deepcopy(self.manifest['rp1_device_handoff']);record['pages']=7
        self.reject('rp1_device_handoff',record,'exact_rp1_handoff')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
