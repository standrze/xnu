# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_gem_selected_package as checker


class GEMSelectedPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_GEM_SELECTED_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_device_and_exact_one_object_delta(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['selected_clock_package_checks'].values()))
        c=self.report['selected_clock_contract'];self.assertEqual(c['sys_ctrl_exact_values'],[2,0x802])
        self.assertEqual(c['sys_selected_exact'],4);self.assertFalse(c['physical_frequency_or_gate_measurement'])
        self.assertEqual(len(c['object_replacements']),1);self.assertEqual(c['added_objects'],[])
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],42)
        self.assertTrue(self.report['root_config_memory_writes']);self.assertTrue(self.report['root_command_changes_mem_only'])
        self.assertFalse(self.report['endpoint_register_writes']);self.assertFalse(self.report['serial_input_allowed'])
        self.assertFalse(self.report['physical_execution']);self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],6)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])

    def test_contract_closure_and_no_extra_authority_mutations_rejected(self):
        contract=copy.deepcopy(self.manifest['selected_clock_contract']);contract['sys_ctrl_exact_values']=[2,0x802,0x402]
        self.reject('selected_clock_contract',contract,'selected_clock_contract')
        contract=copy.deepcopy(self.manifest['selected_clock_contract']);contract['physical_frequency_or_gate_measurement']=True
        self.reject('selected_clock_contract',contract,'selected_clock_contract')
        contract=copy.deepcopy(self.manifest['root_forward_contract']);contract['root_command_changed_bits']=6
        self.reject('root_forward_contract',contract,'root_forward_contract')
        self.reject('root_command_changes_mem_only',False,'root_memory_only')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
