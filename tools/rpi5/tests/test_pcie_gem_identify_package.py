# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_gem_identify_package as checker


class GEMIdentifyPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_GEM_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_device_stack_and_new_kernel(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['gem_package_checks'].values()))
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],35)
        self.assertEqual(self.report['gem_contract']['endpoint_read_bound'],32)
        self.assertTrue(self.report['decode_contract']['endpoint_register_access'])
        self.assertFalse(self.report['gem_contract']['endpoint_register_writes'])
        self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],6)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])

    def test_permission_closure_and_scope_mutations_rejected(self):
        contract=copy.deepcopy(self.manifest['gem_contract']);contract['endpoint_register_writes']=True
        self.reject('gem_contract',contract,'exact_gem')
        contract=copy.deepcopy(self.manifest['decode_contract']);contract['endpoint_register_access']=False
        self.reject('decode_contract',contract,'exact_decode')
        record=copy.deepcopy(self.manifest['rp1_device_handoff']);record['pages']=7
        self.reject('rp1_device_handoff',record,'exact_historical_components')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
