# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_guard_composition_package as checker


class GuardPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_GUARD_PACKAGE']).resolve();cls.path=cls.p/'manifest.json'
        cls.m=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.p)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.m);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.p)

    def test_actual_native_handoff_changed_composition_same_bounds(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['guard_package_checks'].values()))
        self.assertEqual(self.report['guard_composition']['deadline_seconds'],[9,10,12,15])
        self.assertEqual(self.report['guard_composition']['cumulative_pm_limit'],65536)
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],19)
        self.assertFalse(self.report['owner_trace']['guard_policy_unchanged'])
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])
        self.assertIs(self.m['ethernet_proven'],False)

    def test_changed_guard_truth_and_complete_closure(self):
        owner=copy.deepcopy(self.m['owner_trace']);owner['guard_policy_unchanged']=True
        self.reject('owner_trace',owner,'truthful_owner_contract')
        guard=copy.deepcopy(self.m['guard_composition']);guard['cumulative_pm_limit']=65537
        self.reject('guard_composition',guard,'exact_guard_composition')
        changed=dict(self.m['generated_sha256']);changed.pop(str(self.p/'probe_main.o'))
        self.reject('generated_sha256',changed,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
