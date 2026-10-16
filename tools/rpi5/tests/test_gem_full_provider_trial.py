# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import gem_full_provider_trial_profile as profile
from tools.rpi5 import parse_gem_full_provider_trial as parser


class FullProviderTrialTests(unittest.TestCase):
    def test_derived_path_is_observation_only(self):
        files = profile.derive()
        transport = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
        progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
        self.assertIn("observePreparedFullProvider", transport)
        self.assertIn("FULL_PAGE INDEX=", progress)
        self.assertIn("FULL_SPAN INDEX=", progress)
        self.assertIn("OSTEP=%u OERROR=%d", progress)
        self.assertIn("dmaObserveStep=9", transport)
        self.assertIn("before.imr!=UINT32_C(0x3fffffff)", transport)
        self.assertIn("after.imr!=UINT32_C(0x3fffffff)", transport)
        self.assertNotIn("before.imr || after.imr", transport)
        self.assertLess(transport.index("dmaBefore=before;dmaAfter=after;"),
            transport.index("if(before.ncr || after.ncr"))
        for token in ("stageCPUOwned", "rpi5_gem_queue_admission_run", "publishQueue"):
            self.assertNotIn(token, transport + progress)

    def test_parser_rejects_empty_or_duplicate_incomplete_evidence(self):
        self.assertEqual(parser.RP1_GEM_ALL_INTERRUPTS_MASKED, "3fffffff")
        self.assertEqual(parser._fields("RP1=68909694976 X1=2"),
            {"RP1": "68909694976", "X1": "2"})
        # Preferred RAM remains the sole enabled inbound decoder; DISABLED=0
        # is therefore required while the exact FULL_ROUTE proof constrains it.
        self.assertIn('"DISABLED": "0"',
            __import__("pathlib").Path(parser.__file__).read_text())
        with self.assertRaises(ValueError):
            parser.parse("")
        with self.assertRaises(ValueError):
            parser.parse("RPI5XNU:PCIEID:BEGIN FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA\n" * 2)


if __name__ == "__main__":
    unittest.main()
