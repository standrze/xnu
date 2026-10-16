# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_phy_gpio_package as checker


class PHYGPIOPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if 'RPI5_PHY_GPIO_PACKAGE' not in os.environ:raise unittest.SkipTest('Exact new package not supplied')
        cls.package=Path(os.environ['RPI5_PHY_GPIO_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_device_kernel_and_exact_scope(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['gpio_package_checks'].values()))
        c=self.report['gpio_contract'];self.assertEqual(c['read_limit'],12)
        self.assertEqual(len(c['object_replacements']),1);self.assertEqual(len(c['added_objects']),1)
        self.assertEqual(c['native_model_pm_checks'],63916)
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],53)
        self.assertFalse(self.report['endpoint_register_writes']);self.assertFalse(self.report['phy_register_writes'])
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])
        self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],9)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])
        self.assertEqual(self.report['rp1_device_handoff'],checker.source.gpio_handoff_contract())

    def test_contract_closure_typed_counts_and_no_authority_expansion(self):
        for key,value in (('read_limit',11),('unchanged_pm_limit',99999),('reset_active_low',1),('passes',2.0),('reset_pin',31)):
            c=copy.deepcopy(self.manifest['gpio_contract']);c[key]=value;self.reject('gpio_contract',c,'gpio_contract')
        self.reject('phy_register_writes',True,'read_only_gpio_scope')
        self.reject('root_command_changes_mem_only',False,'root_memory_only')
        c=copy.deepcopy(self.manifest['rp1_device_handoff']);c['pages']=6
        self.reject('rp1_device_handoff',c,'exact_gpio_device_handoff')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
