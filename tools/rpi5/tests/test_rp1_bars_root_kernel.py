# SPDX-License-Identifier: BSD-2-Clause
"""Read-only actual linked object and generated-source closure, no board claims."""
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from tools.rpi5 import build_rp1_bars_root_kernel as source

PACKAGE=source.ROOT/'build/rpi5/rp1-bars-root-kernel-20261013-v2'


class BarsRootKernelTests(unittest.TestCase):
    def test_exact_object_delta_and_complete_current_inputs(self):
        b=source.configured();m=json.loads((PACKAGE/'manifest.json').read_text())
        original,current,replacements=b.objects(PACKAGE)
        self.assertEqual(len(replacements),1);self.assertEqual(len(current),len(original)+2)
        self.assertEqual((PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines(),list(map(str,current)))
        self.assertEqual(m['bars_transport_replacements'],{str(k):str(v) for k,v in replacements.items()})
        self.assertEqual(set(Path(p).name for p in m['bars_added_objects']),{'rp1_bars_plan.c.o','rp1_bars_probe.c.o'})
        source.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(source.audit.sha(Path(m['kernel'])),m['kernel_sha256'])
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        with tempfile.TemporaryDirectory() as d:
            overlay=Path(d)/'overlay';source.profile.emit(overlay)
            for p in overlay.iterdir():self.assertEqual(p.read_bytes(),(PACKAGE/'overlay'/p.name).read_bytes())
        deps=(PACKAGE/'BCM2712PCIePHYTransport.cpp.actual.d').read_text()
        self.assertIn(str(PACKAGE/'overlay/BCM2712RP1BarsTransport.inc'),deps)
        self.assertIn(str(PACKAGE/'overlay/BCM2712PCIeControllerPolicy.h'),deps)
        self.assertNotIn(str(source.ROOT/'iokit/Kernel/BCM2712PCIeControllerPolicy.h'),deps)

    def test_linked_class_guarded_call_order_and_all_old_cores_unchanged(self):
        b=source.configured();m=json.loads((PACKAGE/'manifest.json').read_text())
        original,current,_=b.objects(PACKAGE)
        for name in ('pcie_rc.c.o','pcie_link.c.o','pcie_clock.c.o','pcie_qos.c.o','pcie_ubus.c.o','rp1_config_snapshot_checked.c.o'):
            self.assertEqual([p for p in original if p.name==name],[p for p in current if p.name==name])
            self.assertEqual(len([p for p in current if p.name==name]),1)
        self.assertEqual(m['emitted_all_bar_caller_sequence'],['_rpi5_rp1_config_snapshot_trace',
            '_rpi5_rp1_bars_probe','_rpi5_rp1_bars_assignment_plan'])
        self.assertEqual(source.audit.read_command(['xcrun','nm','-ju',PACKAGE/'kernel.rp1-config']),'')
        assembly=(PACKAGE/'BCM2712PCIePHYTransport.cpp.s').read_text()
        body=re.search(r'^_rpi5_pcie_id_trial_start:[^\n]*\n(.*?)Lfunc_end\d+:',assembly,re.M|re.S)[1]
        # Clang duplicates PREPARED in the allocation-failure branch; all
        # runtime paths still emit the same single PREPARED before diagnostics.
        self.assertEqual(len(re.findall(r'\tbl\t_kprintf(?:\n|\s)',body)),15)
        label=re.search(r'^(l_\.str\.\d+):[^\n]*\n\s*\.asciz\s+"RPI5XNU:PCIEID:PREPARED ',assembly,re.M)[1]
        self.assertEqual(body.count('add\tx0, x0, '+label+'@PAGEOFF'),2)

    def test_no_oversized_format_or_assignment_claim(self):
        m=json.loads((PACKAGE/'manifest.json').read_text());raw=(PACKAGE/'kernel.rp1-config').read_bytes()
        for name in ('BEGIN','PREPARED','UBUS','LINK','RP1','ROOT','BARS','BAR0','BAR1','BAR2','BAR3','BAR4','BAR5','END'):
            start=raw.index(('RPI5XNU:PCIEID:'+name+' ').encode());end=raw.index(b'\0',start)
            fmt=raw[start:end]
            self.assertLessEqual(len(re.findall(rb'%(?:0[248])?(?:llu|[udx])',fmt)),15)
        for key in ('bar_assignment_performed','bar_memory_decode_enabled','bar_mmio_mapped','bar_failure_exact_restoration_claimed',
            'clean_preceding_runtime_trial','pi_executed','ethernet_proven'):
            self.assertIs(m[key],False,key)
        self.assertEqual(m['command_writes'],0);self.assertEqual(m['endpoint_write_offsets'],list(range(0x10,0x28,4)))
        self.assertEqual(m['endpoint_config_writes_max'],12);self.assertEqual(m['bar_config_transactions_max'],49)


if __name__=='__main__':unittest.main()
