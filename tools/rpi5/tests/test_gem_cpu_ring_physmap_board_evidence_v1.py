# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from tools.rpi5 import gem_cpu_ring_physmap_board_evidence_v1 as evidence
from tools.rpi5 import gem_cpu_ring_physmap_serial_v3 as parser


class CPUringPhysmapBoardEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state = json.loads((evidence.CAPTURE / "state.json").read_bytes())
        cls.data = (evidence.CAPTURE / "serial.bin").read_bytes()
        cls.report = cls.state["installation"]["preflight"]
        cls.sources = cls.state["source_sha256"]

    def test_exact_retained_capture_passes(self):
        result = evidence.inspect()
        diagnostic = result["diagnostic"]
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["cpu_ring_physical_trial_pass"])
        self.assertEqual(diagnostic["observed_field_rows"], 53)
        self.assertEqual(len(diagnostic["ordered_records"]), 53)
        self.assertEqual(diagnostic["ordered_record_names"][0], "BEGIN")
        self.assertEqual(diagnostic["ordered_record_names"][-1], "END")
        self.assertEqual(diagnostic["preparation"], dict(step=17, error=0, bytes=32768, packets=0))
        self.assertEqual(diagnostic["cpu_ring_stage"],
            dict(state=2, error=0, attempted=640, written=640, read=640, calls=81, checks=164))
        self.assertEqual(diagnostic["cpu_ring_geometry"]["owned"], 160)
        self.assertTrue(diagnostic["automatic_watchdog_return_observed"])
        self.assertTrue(diagnostic["no_fault_through_return"])
        self.assertFalse(result["runtime_fault_signature_observed"])
        self.assertFalse(result["ethernet_proven"])

    def test_contracts_and_markers_are_bound_from_pinned_software(self):
        bound = parser.bind_report(self.report, self.sources)
        self.assertIn("cpu_ring_contract", bound)
        self.assertIn("inherited_capability_contracts", bound)
        self.assertEqual(len(bound["boot_markers"]), 6)
        for marker in bound["boot_markers"]:
            self.assertEqual(self.data.count(marker.encode()), 1)

    def test_missing_source_pin_is_rejected(self):
        sources = dict(self.sources)
        sources.pop(str(parser.CONTRACT_SOURCE))
        with self.assertRaisesRegex(ValueError, "Contract source absent"):
            parser.inspect(self.data, self.report, sources)

    def test_changed_contract_dictionary_is_rejected(self):
        changed = parser.contracts.contract()
        changed["word_writes"] += 1
        with mock.patch.object(parser.contracts, "contract", return_value=changed):
            with self.assertRaisesRegex(ValueError, "Pinned gem_dma_batch_contract"):
                parser.inspect(self.data, self.report, self.sources)

    def test_changed_hardware_row_is_rejected(self):
        changed = self.data.replace(b"DMA_STAGE STATE=2", b"DMA_STAGE STATE=1", 1)
        with self.assertRaises(ValueError):
            parser.inspect(changed, self.report, self.sources)

    def test_reordered_hardware_rows_are_rejected(self):
        rows = self.data.splitlines(keepends=True)
        positions = [i for i, row in enumerate(rows) if row.startswith(parser.protocol.PREFIX)]
        rows[positions[-2]], rows[positions[-3]] = rows[positions[-3]], rows[positions[-2]]
        with self.assertRaisesRegex(ValueError, "53 ordered records"):
            parser.inspect(b"".join(rows), self.report, self.sources)

    def test_missing_return_tail_is_rejected(self):
        end = self.data.find(b"RPI5XNU:PCIEID:END ")
        truncated = self.data[:self.data.find(b"\n", end) + 1]
        with self.assertRaisesRegex(ValueError, "return"):
            parser.inspect(truncated, self.report, self.sources)

    def test_fault_after_end_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Fault"):
            parser.inspect(self.data + b"RPI5XNU:FAULT synthetic\r\n", self.report, self.sources)


if __name__ == "__main__":
    unittest.main()
