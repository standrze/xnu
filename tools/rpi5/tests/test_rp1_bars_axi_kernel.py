# SPDX-License-Identifier: BSD-2-Clause
"""Exact combined object/closure audit; no synthetic result becomes a board claim."""
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_rp1_bars_axi_kernel as source


class BarsAXIKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b=source.configured_builder();cls.p=Path(os.environ['RPI5_BARS_AXI_KERNEL']).resolve()
        cls.m=json.loads((cls.p/'manifest.json').read_text())

    def test_exact_three_cores_preserve_entire_bar_transport(self):
        b=self.b;original,current,replacements=b.objects(self.p)
        self.assertEqual((self.p/'kernel.rp1-config.filelist').read_text().splitlines(),[str(p) for p in current])
        self.assertEqual(len(replacements),3)
        self.assertEqual(sum(p!=q for p,q in zip(original,current)),3)
        for name in b.CORES:
            self.assertEqual((self.p/'overlay'/name).read_bytes(),(source.AXI/'overlay'/name).read_bytes())
        self.assertEqual((self.p/'overlay/rpi5_axi_reserved_profile.h').read_bytes(),
            (source.AXI/'overlay/rpi5_axi_reserved_profile.h').read_bytes())
        for part in ('BCM2712PCIePHYTransport.cpp.o','rp1_bars_probe.c.o','rp1_bars_plan.c.o'):
            self.assertEqual([p for p in current if p.name==part],[p for p in original if p.name==part])

    def test_exact_complete_inputs_artifacts_and_link(self):
        b=self.b;old,pins=b.inputs();cwd=b.audit.OBJ/'pexpert/DEVELOPMENT'
        for p in (self.p/'overlay').iterdir():pins[str(p)]=b.audit.sha(p)
        for name in b.CORES:
            deps=b.audit.dependency_paths(self.p/(name+'.d'),cwd)
            self.assertEqual(deps,b.audit.dependency_paths(self.p/(name+'.actual.d'),cwd))
            for p in deps:pins[str(p)]=b.audit.sha(p)
        self.assertEqual(self.m['inputs_sha256'],pins);b.verify(pins)
        self.assertEqual(self.m['generated_sha256'],{str(p):b.audit.sha(p) for p in self.p.rglob('*')
            if p.is_file() and p.name!='manifest.json'})
        result=b.base.full.linked_audit((self.p/'kernel.rp1-config').read_bytes(),
            (self.p/'kernel.symbols').read_text(),(self.p/'kernel.map').read_text(errors='surrogateescape'))
        self.assertEqual(result,self.m['link'])
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',self.p/'kernel.rp1-config']),'')

    def test_precise_diagnostics_and_no_decode_or_restoration_overclaim(self):
        old=json.loads((source.BASE/'manifest.json').read_text())
        for k in ('bar_failure_semantics','bar_config_transactions','bar_sizing_writes','command_writes',
                  'bar_assignment_performed','bar_memory_decode_enabled','bar_mmio_mapped',
                  'endpoint_write_offsets','emitted_all_bar_caller_sequence'):
            self.assertEqual(self.m[k],old[k])
        oldraw=(source.BASE/'kernel.rp1-config').read_bytes();raw=(self.p/'kernel.rp1-config').read_bytes()
        for prefix in (b'RPI5XNU:PCIEBARS:BEGIN',b'RPI5XNU:PCIEBARS:PREPARED',b'RPI5XNU:PCIEBARS:END'):
            start=oldraw.index(prefix);end=oldraw.index(b'\0',start)+1
            self.assertEqual(raw.count(oldraw[start:end]),1)
        self.assertFalse(self.m['loader_created']);self.assertFalse(self.m['physical_trial_admitted'])
        self.assertFalse(self.m['pi_executed']);self.assertFalse(self.m['ethernet_proven'])


if __name__=='__main__':unittest.main()
