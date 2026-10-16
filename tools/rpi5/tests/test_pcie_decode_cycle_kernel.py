# SPDX-License-Identifier: BSD-2-Clause
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from tools.rpi5 import build_pcie_decode_cycle_kernel as b
PACKAGE=Path(os.environ.get('RPI5_DECODE_KERNEL',str(b.ROOT/'build/rpi5/pcie-decode-cycle-kernel-20261013-v1'))).resolve()


class DecodeKernelTests(unittest.TestCase):
    def test_exact_one_replacement_one_addition_and_regenerated_closure(self):
        m=json.loads((PACKAGE/'manifest.json').read_text());before,after,changes=b.objects(PACKAGE)
        self.assertEqual(len(changes),1);self.assertEqual(len(after),len(before)+1)
        self.assertEqual(m['decode_object_replacements'],{str(p):str(q) for p,q in changes.items()})
        self.assertEqual(m['decode_added_objects'],[str(PACKAGE/'rp1_decode_cycle.c.o')])
        self.assertEqual((PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines(),list(map(str,after)))
        b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)/'overlay';b.profile.emit(folder)
            for path in folder.iterdir():self.assertEqual(path.read_bytes(),(PACKAGE/'overlay'/path.name).read_bytes())
        for name in ('pe_fiq.c.o','pcie_watchdog_lease.c.o','pcie_irq_mask.c.o','pcie_fw_client.c.o','rp1_bars_probe.c.o','rp1_bars_plan.c.o','rp1_bars_assign.c.o'):
            self.assertEqual([p for p in before if p.name==name],[p for p in after if p.name==name])
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        self.assertEqual(m['decode_contract'],b.contract())

    def test_actual_linked_adapter_calls_and_bounded_rows(self):
        m=json.loads((PACKAGE/'manifest.json').read_text())
        self.assertEqual(b.audit.read_command(['xcrun','nm','-ju',PACKAGE/'kernel.rp1-config']),'')
        assembly=(PACKAGE/'BCM2712PCIePHYTransport.cpp.s').read_text()
        source=re.search(r'^__ZN\d+BCM2712PCIePHYTransport12decodeSource[^:]*:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
        for forbidden in ('_pe_rpi5_','_clock_get','_IODelay'):
            self.assertNotIn(forbidden,source)
        for name in m['decode_required_implementations']:
            self.assertIn(name,(PACKAGE/'kernel.symbols').read_text())
        for name in ('decodeMap','decodeUnmap','decodeWrite','decodeMapValid'):
            self.assertIn(name,assembly)
        self.assertEqual(m['logging_calls'],25)
        self.assertEqual([m[k] for k in ('ns_fw_deadline_seconds','secure_fw_deadline_seconds','pm_access_deadline_seconds','hardware_reset_seconds')],[9,10,12,15])
        self.assertEqual(m['cumulative_pm_limit'],65536)
        self.assertFalse(m['physical_success_proven'])
        self.assertFalse(m['decode_contract']['endpoint_register_access'])


if __name__=='__main__':unittest.main()
