# SPDX-License-Identifier: BSD-2-Clause
"""Exact linked passive PE snapshot and complete source/object closure."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from tools.rpi5 import build_pcie_owner_trace_kernel as b
PACKAGE=Path(os.environ.get('RPI5_OWNER_KERNEL',str(b.ROOT/'build/rpi5/pcie-owner-trace-kernel-20261013-v1'))).resolve()


class OwnerKernelTests(unittest.TestCase):
    def test_exact_delta_closure_and_emitted_sources(self):
        m=json.loads((PACKAGE/'manifest.json').read_text());old,now,replacements=b.objects(PACKAGE)
        self.assertEqual(len(old),len(now));self.assertEqual(len(replacements),2)
        self.assertEqual(m['owner_trace_object_replacements'],{str(p):str(q) for p,q in replacements.items()})
        self.assertEqual((PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines(),list(map(str,now)))
        b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'overlay';b.profile.emit(folder)
            for p in folder.iterdir():
                expected=p.read_text().replace(str(folder),str(PACKAGE/'overlay'))
                self.assertEqual(expected,(PACKAGE/'overlay'/p.name).read_text())
        for name in ('pe_fiq.c','BCM2712PCIePHYTransport.cpp'):
            deps=b.audit.dependency_paths(PACKAGE/(name+'.actual.d'),b.audit.OBJ/('pexpert/DEVELOPMENT' if name.endswith('.c') else 'iokit/DEVELOPMENT'))
            self.assertIn(b.profile.HEADER,deps)
        for name in ('pcie_watchdog_lease.c.o','pcie_irq_mask.c.o','pcie_fw_client.c.o','rp1_bars_probe.c.o','rp1_bars_plan.c.o','pcie_rc.c.o','pcie_link.c.o'):
            self.assertEqual([p for p in old if p.name==name],[p for p in now if p.name==name])

    def test_linked_readonly_snapshot_and_bounded_records(self):
        assembly=(PACKAGE/'pe_fiq.c.s').read_text()
        body=re.search(r'^_pe_rpi5_pcie_owner_trace:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
        self.assertNotIn('\tsmc\t',body)
        self.assertNotIn('pcie_fw_client_check',body)
        self.assertNotIn('watchdog_check',body)
        self.assertNotIn('CNTVCT',body.upper())
        self.assertNotIn('rpi5_mmio',body)
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',PACKAGE/'kernel.rp1-config']),'')
        raw=(PACKAGE/'kernel.rp1-config').read_bytes()
        for label,fmt,_ in b.profile.ROWS:
            self.assertEqual(raw.count(('RPI5XNU:PCIEID:'+label+' '+fmt+'\n\0').encode()),1)
        m=json.loads((PACKAGE/'manifest.json').read_text())
        self.assertEqual(m['logging_calls'],19)
        self.assertEqual([m[k] for k in ('ns_fw_deadline_seconds','secure_fw_deadline_seconds','pm_access_deadline_seconds','hardware_reset_seconds')],[9,10,12,15])
        self.assertFalse(m['physical_failure_cause_proven'])


if __name__=='__main__':unittest.main()
