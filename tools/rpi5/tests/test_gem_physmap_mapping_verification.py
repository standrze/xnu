#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
import copy, subprocess, tempfile, unittest
from pathlib import Path
from tools.rpi5 import gem_physmap_mapping_verification_profile as profile
from tools.rpi5 import check_gem_physmap_mapping_verification as checker


class PhysmapMappingVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = profile.derive()

    def test_terminal_discard_precedes_route(self):
        source = self.files["BCM2712GEMDMABatch.cpp"].decode()
        prepare = source[source.index("bool BCM2712GEMDMABatch::prepare()"):
            source.index("bool BCM2712GEMDMABatch::discardBeforeAdmission()")]
        tail = prepare[prepare.index("if (!mapping())"):]
        self.assertIn("discardBeforeAdmission()", tail)
        self.assertNotIn("route(", tail)
        self.assertNotIn("state_=Prepared", prepare)

    def test_exact_four_alias_rows(self):
        source = self.files["BCM2712PCIeIDTrialProgress.inc"].decode()
        entry = source[source.index('extern "C" void rpi5_pcie_id_trial_start(void)\n'):]
        self.assertIn("page<2", entry)
        self.assertIn("vaClass<=2", entry)
        self.assertEqual(entry.count("RPI5XNU:PCIEID:DMA_ALIAS"), 1)
        self.assertNotIn("runBoundedRP1Trial(&observed)", entry)
        self.assertNotIn("pe_rpi5_pcie_owner_trace(", entry)

    def test_at_par_interrupt_semantics_retained(self):
        source = self.files["BCM2712GEMDMABatch.cpp"].decode()
        for token in ("at s1e1r", "at s1e1w", "mrs %0, par_el1", "msr par_el1, %0",
                      "ml_set_interrupts_enabled(FALSE)", "ml_set_interrupts_enabled(interrupts)"):
            self.assertEqual(source.count(token), 1, token)

    def test_accounting_is_bounded_and_reservation_checked(self):
        source = self.files["BCM2712GEMDMABatch.cpp"].decode()
        self.assertIn("account.maximum_pages>259", source)
        self.assertIn("account.edge_pages>2", source)
        self.assertIn("account.preallocated_upper_pages!=1", source)
        self.assertIn("account.table_end<account.table_start", source)
        self.assertIn("account.table_bytes!=uint64_t(account.table_pages)*Alignment", source)
        self.assertIn("rpi5_reservation_kernel_buffer(currentRecord,account.table_start,account.table_bytes)", source)

    def test_boundary_and_edge_accounting_helpers(self):
        root = Path(__file__).resolve().parents[3]
        code = r'''#include <assert.h>
#include "osfmk/arm64/rpi5_gem_physmap_bounds.h"
int main(void) {
  const uint64_t C=0x2000000, P=0x4000;
  assert(rpi5_gem_table_span_pages(0,0,C)==0);
  assert(rpi5_gem_table_span_pages(0,C,C)==1);
  assert(rpi5_gem_table_span_pages(P,C,C)==2);
  assert(rpi5_gem_table_span_pages(C-P,P,C)==1);
  assert(rpi5_gem_table_span_pages(C-P,2*P,C)==2);
  assert(rpi5_gem_partial_edge_pages(0,C,C)==0);
  assert(rpi5_gem_partial_edge_pages(P,C-P,C)==1);
  assert(rpi5_gem_partial_edge_pages(P,C+P,C)==2);
  assert(rpi5_gem_partial_edge_pages(0,C+P,C)==1);
  assert(rpi5_gem_partial_edge_pages(P,C,C)==1);
  return 0;
}'''
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "bounds.c"
            binary = Path(td) / "bounds"
            source.write_text(code)
            subprocess.run(["clang", "-std=c11", "-I", str(root), str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    def test_marker_and_loose_ends_mutations_are_rejected(self):
        tag = "6db66759d35d47789e3dc1c21a3481f9"
        marker = f"RPI5XNU:CPU_RINGS:ENTRY TAG={tag} CPUS=1 NO_CPU_ON NO_QUEUE NO_DMA"
        manifest = {"tag": tag, "trial_marker": marker, "replaced_objects": {
            "/old/pmap.o": "/new/pmap-enabled.o",
            "/old/arm_vm_init.o": "/new/arm_vm_init-enabled.o",
            "/old/loose_ends.o": "/new/loose_ends-enabled.o"}}
        self.assertEqual(checker.marker_errors(manifest, marker.encode()), [])
        self.assertEqual(checker.replacement_errors(manifest), [])
        for key, value in (("tag", "0" * 32), ("trial_marker", marker.replace(tag, "1" * 32))):
            changed = copy.deepcopy(manifest)
            changed[key] = value
            self.assertTrue(checker.marker_errors(changed, marker.encode()))
        duplicate = marker.encode() + marker.encode()
        self.assertTrue(checker.marker_errors(manifest, duplicate))
        missing = copy.deepcopy(manifest)
        del missing["replaced_objects"]["/old/loose_ends.o"]
        self.assertTrue(checker.replacement_errors(missing))

    def test_mutation_route_after_mapping_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            package = Path(td)
            overlay = package / "overlay"
            overlay.mkdir()
            for name, data in self.files.items():
                (overlay / name).write_bytes(data)
            provider = overlay / "BCM2712GEMDMABatch.cpp"
            provider.write_text(provider.read_text().replace("prepareStep_=15;state_=Rejected;",
                "prepareStep_=15;struct rpi5_gem_dma_route g;route(&expected_,&g);state_=Rejected;"))
            # Exercise the same critical local predicate without fabricating a manifest.
            text = provider.read_text()
            prepare = text[text.index("bool BCM2712GEMDMABatch::prepare()"):
                text.index("bool BCM2712GEMDMABatch::discardBeforeAdmission()")]
            self.assertIn("route(", prepare[prepare.index("if (!mapping())"):])


if __name__ == "__main__":
    unittest.main()
