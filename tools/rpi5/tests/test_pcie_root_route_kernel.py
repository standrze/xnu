# SPDX-License-Identifier: BSD-2-Clause
"""Read-only linked root-route candidate closure and retained implementation checks."""
import json
from pathlib import Path
import unittest
from tools.rpi5 import build_pcie_root_route_kernel as b

PACKAGE=b.ROOT/'build/rpi5/pcie-root-route-kernel-20261013-v3'


class RootRouteKernelTests(unittest.TestCase):
    def test_exact_two_replacements_and_all_input_bytes(self):
        m=json.loads((PACKAGE/'manifest.json').read_text())
        self.assertEqual(m['profile'],b.PROFILE)
        b.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(b.audit.sha(Path(m['kernel'])),m['kernel_sha256'])
        old,current,replacements=b.objects(PACKAGE)
        self.assertEqual(set(p.name for p in replacements),{'pcie_rc.c.o','BCM2712PCIePHYTransport.cpp.o'})
        self.assertEqual(len(old),len(current))
        actual=(PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines()
        self.assertEqual(actual,list(map(str,current)))
        self.assertEqual(m['root_route_object_replacements'],{str(k):str(v) for k,v in replacements.items()})
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        deps=(PACKAGE/'BCM2712PCIePHYTransport.cpp.actual.d').read_text()
        self.assertIn(str(PACKAGE/'overlay/BCM2712PCIeControllerPolicy.h'),deps)
        self.assertNotIn(str(b.ROOT/'iokit/Kernel/BCM2712PCIeControllerPolicy.h'),deps)

    def test_actual_core_source_and_ordered_linked_call(self):
        m=json.loads((PACKAGE/'manifest.json').read_text())
        core=PACKAGE/'overlay/pcie_rc.c'
        self.assertEqual(core.read_text(),b.profile.core((b.ROOT/'loader/rpi5/pcie_rc.c').read_text()))
        calls=m['root_route_call_sequence']
        self.assertLess(calls.index('_rpi5_pcie_rc_configure_root_route'),calls.index('_rpi5_pcie_link_train_elapsed_trace'))
        self.assertEqual(m['root_config_write_offset'],24)
        self.assertEqual(m['root_config_writes_max'],1)
        self.assertEqual(m['root_config_reads_max'],6)
        self.assertTrue(m['root_route_post_link_readback'])
        self.assertEqual(m['endpoint_config_writes'],0)
        self.assertEqual(m['command_writes'],0)
        self.assertEqual(m['root_config_identity'],0x271214e4)
        self.assertFalse(m['physical_cause_proven'])

    def test_original_link_config_snapshot_firmware_and_bounds_preserved(self):
        m=json.loads((PACKAGE/'manifest.json').read_text())
        parent=json.loads((b.BASE/'manifest.json').read_text())
        for key in ('reset_min_us','reset_max_us','poll_max_us','firmware_guard_unchanged','watchdog_unchanged',
            'link_trace_fields','rp1_trace_fields','rp1_trace_object_replacements','axi_object_replacements'):
            self.assertEqual(m[key],parent[key],key)
        for name in ('pcie_link.c.o','rp1_config_snapshot_checked.c.o','pcie_clock.c.o'):
            before=[p for p in (b.BASE/'kernel.rp1-config.filelist').read_text().splitlines() if Path(p).name==name]
            after=[p for p in (PACKAGE/'kernel.rp1-config.filelist').read_text().splitlines() if Path(p).name==name]
            self.assertEqual(before,after);self.assertEqual(len(after),1)
        blob=Path(m['kernel']).read_bytes()
        self.assertEqual(blob.count(b.profile.FIELDS.encode()),1)


if __name__=='__main__':unittest.main()
