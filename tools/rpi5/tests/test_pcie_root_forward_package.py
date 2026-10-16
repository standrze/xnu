# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_root_forward_package as checker


class RootForwardPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_ROOT_FORWARD_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_device_and_exact_root_forward_kernel(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['root_forward_package_checks'].values()))
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],42)
        self.assertEqual(self.report['root_forward_contract']['root_read_bound'],79)
        self.assertEqual(self.report['root_forward_contract']['root_command_write_width'],16)
        self.assertEqual(len(self.report['root_forward_contract']['primary_source_references']),5)
        self.assertTrue(self.report['root_config_memory_writes']);self.assertTrue(self.report['root_command_changes_mem_only'])
        self.assertFalse(self.report['endpoint_register_writes']);self.assertFalse(self.report['serial_input_allowed'])
        self.assertFalse(self.report['physical_execution']);self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],6)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])

    def test_permission_scope_and_closure_mutations_rejected(self):
        contract=copy.deepcopy(self.manifest['root_forward_contract']);contract['root_command_changed_bits']=6
        self.reject('root_forward_contract',contract,'root_forward_contract')
        contract=copy.deepcopy(self.manifest['gem_contract']);contract['endpoint_register_writes']=True
        self.reject('gem_contract',contract,'gem_contract')
        self.reject('root_command_changes_mem_only',False,'root_memory_only')
        record=copy.deepcopy(self.manifest['rp1_device_handoff']);record['pages']=7
        self.reject('rp1_device_handoff',record,'exact_historical_components')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
