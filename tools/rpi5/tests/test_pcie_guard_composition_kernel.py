# SPDX-License-Identifier: BSD-2-Clause
"""One linked transport delta with exact immutable owner/core implementations."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from tools.rpi5 import build_pcie_guard_composition_kernel as b
PACKAGE=Path(os.environ.get('RPI5_GUARD_KERNEL',str(b.ROOT/'build/rpi5/pcie-guard-composition-kernel-20261013-v1'))).resolve()


class GuardKernelTests(unittest.TestCase):
    def test_one_object_emitted_sources_and_complete_closure(self):
        m=json.loads((PACKAGE/'manifest.json').read_text());before,after,changed=b.objects(PACKAGE)
        self.assertEqual(len(changed),1)
        self.assertEqual(m['guard_composition_object_replacements'],{str(p):str(q) for p,q in changed.items()})
        self.assertEqual((PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines(),list(map(str,after)))
        b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        with tempfile.TemporaryDirectory() as name:
            folder=Path(name)/'overlay';sources=b.profile.emit(folder)
            self.assertEqual(len(sources),1)
            for path in folder.iterdir():self.assertEqual(path.read_bytes(),(PACKAGE/'overlay'/path.name).read_bytes())
        for name in ('pe_fiq.c.o','pcie_watchdog_lease.c.o','pcie_irq_mask.c.o','pcie_fw_client.c.o',
                     'rp1_bars_probe.c.o','rp1_bars_plan.c.o','pcie_rc.c.o','pcie_link.c.o'):
            self.assertEqual([p for p in before if p.name==name],[p for p in after if p.name==name])
        self.assertEqual(m['unchanged_parent_objects'],len(before)-1)
        self.assertEqual(m['guard_composition'],b.profile.unchanged_contract())
        self.assertFalse(m['guard_predicates_and_call_order_unchanged'])
        self.assertTrue(m['transport_common_owner_predicates_unchanged'])
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)

    def test_actual_guard_owner_calls_and_unchanged_diagnostics(self):
        text=(PACKAGE/'BCM2712PCIePHYTransport.cpp.s').read_text()
        guard=re.search(r'^__ZN\d+BCM2712PCIePHYTransport5guardEv:[^\n]*\n(.*?)Lfunc_end\d+:',text,re.M|re.S)[1]
        calls=re.findall(r'\tbl\t(_pe_rpi5_\w+)',guard)
        self.assertEqual(calls.count('_pe_rpi5_pcie_fw_check'),2)
        self.assertEqual(calls.count('_pe_rpi5_watchdog_check_pcie'),1)
        self.assertNotIn('_pe_rpi5_pcie_irq_check',calls)
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',PACKAGE/'kernel.rp1-config']),'')
        m=json.loads((PACKAGE/'manifest.json').read_text())
        self.assertEqual(m['logging_calls'],19)
        self.assertFalse(m['physical_success_proven'])
        self.assertEqual([m[k] for k in ('ns_fw_deadline_seconds','secure_fw_deadline_seconds','pm_access_deadline_seconds','hardware_reset_seconds')],[9,10,12,15])
        self.assertEqual(m['cumulative_pm_limit'],65536)
        self.assertEqual(m['cumulative_fw_limit'],65536)
        self.assertEqual((PACKAGE/'overlay/BCM2712PCIeIDTrialProgress.inc').read_bytes(),
                         (b.BASE/'overlay/BCM2712PCIeIDTrialProgress.inc').read_bytes())


if __name__=='__main__':unittest.main()
