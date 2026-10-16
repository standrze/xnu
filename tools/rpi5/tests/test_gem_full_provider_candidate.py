# SPDX-License-Identifier: BSD-2-Clause
"""Fail-closed metadata tests for the full retained GEM provider candidate."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.rpi5 import build_gem_full_provider_candidate as build
from tools.rpi5 import check_gem_full_provider_candidate as check

ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT / "iokit/Kernel/BCM2712GEMDMAMemory.h"
PROVIDER = HEADER.with_suffix(".cpp")


class FullProviderCandidateTests(unittest.TestCase):
    def test_exact_default_off_layout_contract(self):
        header = HEADER.read_text()
        provider = PROVIDER.read_text()
        for token in (
            "RPI5_GEM_FULL_PROVIDER_RING_PAGES 2u",
            "RPI5_GEM_FULL_PROVIDER_PACKET_SPANS 128u",
            "RPI5_GEM_FULL_PROVIDER_PAGE_BYTES UINT32_C(0x4000)",
            "RPI5_GEM_FULL_PROVIDER_PACKET_BYTES UINT32_C(0x0800)",
            "RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES 18u",
            "observeCPUOwnedLayout",
            "normal_nc_page_bitmap",
            "rpi5_gem_full_provider_page",
            "base_physical_address",
            "packet_spans_cpu_owned",
        ):
            self.assertIn(token, header)
        for token in (
            "static_assert(AllocationBytes==",
            "bitmap!=(UINT64_C(1)<<RPI5_GEM_FULL_PROVIDER_MAPPING_PAGES)-1",
            "RPI5_GEM_FULL_PROVIDER_OWNER_CPU",
            "mapping(&bitmap,observation_.page)",
            "*out=observation_",
            "route(&windows->expected,&geometry,true)",
            "routePlan.inbound[slot].bar_lo!=(expected&~UINT32_C(31))",
        ):
            self.assertIn(token, provider)
        for forbidden in ("write32(", "COMMAND.BME", "GEM_NCR", "GEM_RBQP", "GEM_TBQP"):
            self.assertNotIn(forbidden, provider)

    def test_source_manifest_exact(self):
        source = json.loads((ROOT / "tools/rpi5/gem_full_provider_sources.json").read_text())
        self.assertEqual(source["profile"], build.PROFILE)
        observed = {row["path"]: row["sha256"] for row in source["sources"]}
        self.assertEqual(set(observed), set(build.SOURCES[:-1]))
        for relative, digest in observed.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)

    def test_checker_rejects_activation_and_source_mutations(self):
        fixture = ROOT / "build/rpi5/gem-full-provider-candidate-20261014-v1"
        if not fixture.exists():
            self.skipTest("immutable candidate package not built yet")
        with tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as directory:
            package = Path(directory)
            original = json.loads((fixture / "manifest.json").read_text())
            for mutation in ("bme", "packet_spans", "normal_nc_page_bitmap_required"):
                altered = copy.deepcopy(original)
                if mutation == "bme":
                    altered["activation"]["bme"] = True
                else:
                    altered[mutation] -= 1
                (package / "manifest.json").write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    check.check(package)


if __name__ == "__main__":
    unittest.main()
