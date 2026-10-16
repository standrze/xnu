# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_bars_assignment_package as checker


class BarsAssignmentPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=Path(os.environ['RPI5_ASSIGNMENT_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_handoff_and_exact_no_decode_contract(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['assignment_package_checks'].values()))
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],23)
        self.assertFalse(self.report['assignment_contract']['mapping_performed']);self.assertFalse(self.report['assignment_contract']['memory_decode_enabled'])
        self.assertEqual(self.report['guard_composition']['cumulative_pm_limit'],65536)
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])

    def test_permission_and_generated_closure_mutations_rejected(self):
        contract=copy.deepcopy(self.manifest['assignment_contract']);contract['memory_decode_enabled']=True
        self.reject('assignment_contract',contract,'exact_assignment')
        owner=copy.deepcopy(self.manifest['owner_trace']);owner['guard_policy_unchanged']=True
        self.reject('owner_trace',owner,'exact_owner')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
