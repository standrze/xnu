# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from tools.rpi5 import check_pcie_gem_mdio_package as checker


class GEMMDIOPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if 'RPI5_GEM_MDIO_PACKAGE' not in os.environ:raise unittest.SkipTest('Exact new package not supplied')
        cls.package=Path(os.environ['RPI5_GEM_MDIO_PACKAGE']).resolve();cls.path=cls.package/'manifest.json'
        cls.manifest=json.loads(cls.path.read_text());cls.report=checker.inspect(cls.package)

    def reject(self,key,value,reason):
        changed=copy.deepcopy(self.manifest);changed[key]=value;read=Path.read_text
        def inject(path,*a,**kw):return json.dumps(changed) if path==self.path else read(path,*a,**kw)
        with patch.object(Path,'read_text',inject),self.assertRaisesRegex(ValueError,reason):checker.inspect(self.package)

    def test_actual_native_fdt_device_kernel_and_exact_scope(self):
        self.assertTrue(all(self.report['checks'].values()));self.assertTrue(all(self.report['mdio_package_checks'].values()))
        c=self.report['mdio_contract'];self.assertEqual(c['clause22_phy_reads'],[2,3,0,1,1])
        self.assertEqual(len(c['object_replacements']),1);self.assertEqual(len(c['added_objects']),1)
        self.assertEqual(c['native_modeled_pm_checks'],65420)
        self.assertEqual(self.report['trace_contract']['terminal_kprintf_count'],53)
        self.assertTrue(self.report['endpoint_register_writes']);self.assertFalse(self.report['phy_register_writes'])
        self.assertFalse(self.report['serial_input_allowed']);self.assertFalse(self.report['physical_execution'])
        self.assertEqual(self.report['native_handoff_contract']['exact_rp1_pages'],6)
        self.assertTrue(self.report['native_handoff_contract']['excluded_adjacent_pages'])

    def test_contract_closure_typed_counts_and_no_authority_expansion(self):
        for key,value in (('read_limit',47),('unchanged_pm_limit',99999),('phy_address',True),('write_limit',9.0),('clause22_phy_reads',[2,3,0,1,2])):
            c=copy.deepcopy(self.manifest['mdio_contract']);c[key]=value;self.reject('mdio_contract',c,'mdio_contract')
        self.reject('phy_register_writes',True,'management_writes_only')
        self.reject('root_command_changes_mem_only',False,'root_memory_only')
        generated=dict(self.manifest['generated_sha256']);generated.pop(str(self.package/'probe_main.o'))
        self.reject('generated_sha256',generated,'complete_generated_closure')
        self.reject('headers_sha256',{},'complete_header_closure')


if __name__=='__main__':unittest.main()
