# SPDX-License-Identifier: BSD-2-Clause
"""Read-only proof of the exact three-object corrected trace kernel."""
import json
import os
from pathlib import Path
import unittest
from tools.rpi5 import build_pcie_axi_trace_kernel as b


class AXITraceKernelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p=Path(os.environ['RPI5_AXI_TRACE_KERNEL']).resolve()
        cls.m=json.loads((cls.p/'manifest.json').read_text())

    def test_only_three_cores_replace_frozen_link_constituents(self):
        original,current,replacements=b.objects(self.p)
        self.assertEqual([str(p) for p in current],(self.p/'kernel.rp1-config.filelist').read_text().splitlines())
        self.assertEqual(self.m['axi_object_replacements'],{str(p):str(q) for p,q in replacements.items()})
        self.assertEqual(len(replacements),3)
        self.assertEqual(sum(p!=q for p,q in zip(original,current)),3)
        for name in b.CORES:
            self.assertEqual((self.p/'overlay'/name).read_text(),b.profile.transform(name,(b.ROOT/'loader/rpi5'/name).read_text()))
        self.assertEqual((self.p/'overlay/rpi5_axi_reserved_profile.h').read_text(),b.profile.HEADER)
        self.assertFalse(self.m['pi_executed'])

    def test_complete_original_new_source_and_generated_closure(self):
        old,pins=b.inputs();cwd=b.audit.OBJ/'pexpert/DEVELOPMENT'
        for p in (self.p/'overlay').iterdir():pins[str(p)]=b.audit.sha(p)
        for name in b.CORES:
            deps=b.audit.dependency_paths(self.p/(name+'.d'),cwd)
            self.assertEqual(deps,b.audit.dependency_paths(self.p/(name+'.actual.d'),cwd))
            for p in deps:pins[str(p)]=b.audit.sha(p)
        self.assertEqual(self.m['inputs_sha256'],pins);b.verify(pins)
        actual={str(p):b.audit.sha(p) for p in self.p.rglob('*') if p.is_file() and p.name!='manifest.json'}
        self.assertEqual(self.m['generated_sha256'],actual)
        self.assertEqual(self.m['kernel_sha256'],b.audit.sha(self.p/'kernel.rp1-config'))
        self.assertEqual(self.m['baseline_linker_warnings'],old['baseline_linker_warnings'])

    def test_actual_complete_link_and_unchanged_terminal_markers(self):
        symbols=(self.p/'kernel.symbols').read_text();mapped=(self.p/'kernel.map').read_text(errors='surrogateescape')
        result=b.base.full.linked_audit((self.p/'kernel.rp1-config').read_bytes(),symbols,mapped)
        self.assertEqual(self.m['link'],result)
        old=(b.BASE/'kernel.rp1-config').read_bytes();new=(self.p/'kernel.rp1-config').read_bytes()
        for prefix in (b'RPI5XNU:PCIEID:BEGIN',b'RPI5XNU:PCIEID:PREPARED',b'RPI5XNU:PCIEID:END'):
            start=old.index(prefix);end=old.index(b'\0',start)+1
            self.assertEqual(new.count(old[start:end]),1)
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',self.p/'kernel.rp1-config']),'')


if __name__=='__main__':unittest.main()
