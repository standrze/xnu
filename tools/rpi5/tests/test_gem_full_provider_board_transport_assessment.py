# SPDX-License-Identifier: BSD-2-Clause
import copy
import unittest

from tools.rpi5 import assess_gem_full_provider_board_transport as assessment


class FullProviderBoardTransportAssessmentTests(unittest.TestCase):
    def test_fail_closed_assessment(self):
        report = assessment.assess()
        self.assertTrue(report["software_candidate_qualified"])
        self.assertFalse(report["physical_transport_qualified"])
        self.assertFalse(report["stageable"])
        self.assertFalse(report["publish_authorized"])
        self.assertFalse(report["hardware_touched"])
        self.assertFalse(any(report["activation"].values()))
        self.assertEqual(report["catalog_baseline_count"], 536)
        self.assertEqual(report["bounded_target"]["provider_bytes"], 0x48000)
        self.assertEqual(report["bounded_target"]["mapping_pages"], 18)
        self.assertEqual(report["bounded_target"]["packet_spans"], 128)

    def test_evidence_inventory_is_exact_and_nonaggregate(self):
        rows = assessment.assess()["required_physical_evidence"]
        self.assertEqual(len(rows), 9)
        joined = "\n".join(rows)
        for token in ("18 ordered page records", "retained CPU VA", "physical PA",
                "RP1 DMA address", "retained/static Normal-NC", "128 ordered packet-span",
                "global non-overlap", "BME bit clear", "RE and TE clear",
                "queue registers unchanged", "interrupts remain masked",
                "zero-transmit", "catalog transition from count 536", "exact post-return restoration"):
            self.assertIn(token, joined)

    def test_no_mutation_can_be_interpreted_as_admission(self):
        report = assessment.assess()
        for key in ("physical_transport_qualified", "stageable", "publish_authorized", "hardware_touched"):
            altered = copy.deepcopy(report)
            altered[key] = True
            self.assertNotEqual(altered, assessment.assess())


if __name__ == "__main__":
    unittest.main()
