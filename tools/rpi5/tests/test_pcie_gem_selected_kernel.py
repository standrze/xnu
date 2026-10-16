# SPDX-License-Identifier: BSD-2-Clause
import json
import tempfile
import unittest
from pathlib import Path
from tools.rpi5 import build_pcie_gem_selected_kernel as b


class GEMSelectedKernelTests(unittest.TestCase):
    def test_one_decoder_delta_all_other_sources_and_objects_retained(self):
        with tempfile.TemporaryDirectory(prefix='gem-selected-kernel-') as directory:
            folder=Path(directory)/'overlay';sources=b.profile.emit(folder)
            self.assertEqual([p.name for p in sources],['rp1_gem_identify.c'])
            for path in b.profile.FROZEN.iterdir():
                if path.is_file() and path.name!='rp1_gem_identify.c':self.assertEqual(path.read_bytes(),(folder/path.name).read_bytes())
            original,current,changes=b.objects(Path(directory))
            self.assertEqual(len(changes),1);self.assertEqual(len(original),len(current))
            self.assertEqual([p.name for p in changes],['rp1_gem_identify.c.o'])
            self.assertEqual(b.audit.sha(b.REFERENCE),b.REFERENCE_SHA)
            self.assertEqual(b.audit.sha(b.CAPTURE),b.CAPTURE_SHA)
            data=b.CAPTURE.read_bytes()
            self.assertIn(b'CLOCK_BEFORE0 CTRL=00000002 DIV=00000001 SEL=00000004 CS=80000001',data)
            self.assertIn(b'GEM CALL=1 RC=-5 STAGE=6 READS=15 READY=0',data)
            self.assertFalse(b.contract()['physical_frequency_or_gate_measurement'])

    def test_actual_linked_complete_single_object_successor(self):
        folder=b.ROOT/'build/rpi5/pcie-gem-selected-kernel-20261013-v1'
        if not (folder/'manifest.json').exists():self.skipTest('Kernel not built yet')
        m=json.loads((folder/'manifest.json').read_text());b.engine.verify(m['inputs_sha256']|m['generated_sha256'])
        self.assertEqual(m['profile'],b.PROFILE);self.assertEqual(m['selected_clock_contract'],b.contract())
        self.assertEqual(m['kernel_sha256'],b.audit.sha(folder/'kernel.rp1-config'))
        self.assertEqual(len(m['selected_clock_object_replacements']),1);self.assertEqual(m['selected_clock_added_objects'],[])
        self.assertTrue(m['transport_object_unchanged']);self.assertTrue(m['passive_trace_unchanged'])
        self.assertTrue(m['owner_client_core_secure_objects_unchanged']);self.assertTrue(m['decode_core_unchanged'])
        self.assertFalse(m['gem_and_decode_core_objects_unchanged'])
        self.assertEqual(m['transport_class_layout']['other_class_imports'],0)
        self.assertTrue(m['transport_class_layout']['transport_class_layout_unchanged'])
        self.assertFalse(m['transport_class_layout']['constructors_allocators_vtable_and_methods_recompiled'])
        for p,h in ((b.REFERENCE,b.REFERENCE_SHA),(b.CAPTURE,b.CAPTURE_SHA)):
            self.assertEqual(m['inputs_sha256'][str(p)],h)


if __name__=='__main__':unittest.main()
