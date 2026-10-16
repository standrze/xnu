# SPDX-License-Identifier: BSD-2-Clause
import unittest
from tools.rpi5 import gem_physmap_alias_gate as gate


class GEMPhysmapAliasGateTests(unittest.TestCase):
    def test_exact_accepted_board_rejection(self):
        line = gate.evidence()
        self.assertIn("REASON=36 PAGE=0 ATTR=6 VA=2 PA=185532416", line)
        self.assertIn("PAR_R=18374686479857158912", line)

    def test_opt_in_is_default_off_and_coupled(self):
        gate.validate_coupling()
        makeinc = (gate.ROOT / "makedefs/MakeInc.def").read_text()
        self.assertNotIn("MACHINE_FLAGS_ARM64_BCM2712 = -DRPI5_GEM_PAGE_GRANULAR_PHYSMAP", makeinc)

    def test_missing_pmap_half_is_rejected(self):
        proc = (gate.ROOT / "osfmk/arm64/proc_reg.h").read_text()
        proc = proc.replace("defined(RPI5_GEM_PAGE_GRANULAR_PHYSMAP) && RPI5_GEM_PAGE_GRANULAR_PHYSMAP", "0", 1)
        with self.assertRaisesRegex(ValueError, "pmap physical-aperture"):
            gate.validate_coupling(proc=proc)

    def test_missing_page_granularity_half_is_rejected(self):
        arm = gate.SOURCES["arm_vm_init"].read_text().replace(
            "const unsigned physmap_granule = 0;", "const unsigned physmap_granule = ARM64_GRANULE_ALLOW_BLOCK;", 1)
        with self.assertRaisesRegex(ValueError, "page granularity"):
            gate.validate_coupling(arm=arm)

    def test_provider_alias_invariant_is_not_bypassed(self):
        provider = (gate.ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.cpp").read_text()
        self.assertIn("!translated_nc(cpu_+offset,pa)", provider)
        self.assertIn("!translated_nc(ml_static_ptovirt(pa),pa)", provider)
        self.assertIn("pmap_cache_attributes", provider)

    def test_loose_ends_is_in_coupled_compile_set(self):
        loose = gate.SOURCES["loose_ends"].read_text()
        self.assertGreaterEqual(loose.count("__ARM_PTE_PHYSMAP__"), 4)
        self.assertIn("phystokv_range", loose)


if __name__ == "__main__":
    unittest.main()
