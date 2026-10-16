# SPDX-License-Identifier: BSD-2-Clause
"""Complete new object/dependency/source closure, not physical RP1 proof."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from tools.rpi5 import build_rp1_config_trace_kernel as b


class ConfigTraceKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_CONFIG_TRACE_KERNEL']).resolve()
        cls.m=json.loads((cls.p/'manifest.json').read_text())

    def test_two_replacements_exact_private_sources(self):
        original,current,replacements=b.objects(self.p)
        self.assertEqual(self.m['rp1_trace_object_replacements'],{str(p):str(q) for p,q in replacements.items()})
        self.assertEqual([str(p) for p in current],(self.p/'kernel.rp1-config.filelist').read_text().splitlines())
        self.assertEqual(sum(p!=q for p,q in zip(original,current)),2)
        for name in ('pcie_link.c.o','pcie_ubus.c.o','pcie_qos.c.o','pcie_clock.c.o'):
            self.assertEqual([p for p in original if p.name==name],[p for p in current if p.name==name])
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'overlay';b.profile.emit(folder)
            self.assertEqual({p.name:p.read_bytes() for p in folder.iterdir()},
                {p.name:p.read_bytes() for p in (self.p/'overlay').iterdir()})
        self.assertEqual(self.m['endpoint_config_writes'],0)
        self.assertFalse(self.m['pi_executed'])

    def test_actual_dependency_and_generated_closure(self):
        parent,_,pins=b.inputs()
        for p in (self.p/'overlay').iterdir():pins[str(p)]=b.audit.sha(p)
        for name in ('BCM2712PCIePHYTransport.cpp','rp1_config_snapshot_checked.c'):
            cwd=b.audit.OBJ/('iokit/DEVELOPMENT' if name.endswith('.cpp') else 'pexpert/DEVELOPMENT')
            deps=b.audit.dependency_paths(self.p/(name+'.d'),cwd)
            self.assertEqual(deps,b.audit.dependency_paths(self.p/(name+'.actual.d'),cwd))
            for p in deps:pins[str(p)]=b.audit.sha(p)
        self.assertEqual(pins,self.m['inputs_sha256']);b.verify(pins)
        self.assertEqual(self.m['generated_sha256'],{str(p):b.audit.sha(p) for p in self.p.rglob('*') if p.is_file() and p.name!='manifest.json'})
        self.assertEqual(self.m['baseline_linker_warnings'],parent['baseline_linker_warnings'])

    def test_actual_link_layout_and_marker_contract(self):
        raw=(self.p/'kernel.rp1-config').read_bytes();listing=(self.p/'kernel.symbols').read_text()
        mapped=(self.p/'kernel.map').read_text(errors='surrogateescape')
        self.assertEqual(self.m['link'],b.base.full.linked_audit(raw,listing,mapped))
        _,current,_=b.objects(self.p)
        self.assertEqual(self.m['transport_class_layout'],b.previous.class_layout_audit(current,self.p/'BCM2712PCIePHYTransport.cpp.o',mapped))
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',self.p/'kernel.rp1-config']),'')
        self.assertEqual(b.audit.sha(self.p/'kernel.rp1-config'),self.m['kernel_sha256'])
        self.assertEqual(raw.count(b.profile.FIELDS.encode()),1)
        self.assertEqual(raw.count(b.previous.profile.FIELDS.encode()),1)
        self.assertTrue(self.m['link_object_unchanged']);self.assertTrue(self.m['config_core_unchanged'])
        self.assertEqual((self.m['reset_min_us'],self.m['reset_max_us'],self.m['poll_max_us']),(100000,110000,100000))


if __name__=='__main__':unittest.main()
