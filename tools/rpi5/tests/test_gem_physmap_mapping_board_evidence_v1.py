# SPDX-License-Identifier: BSD-2-Clause
"""Mutation qualification for immutable mapping-verification board evidence."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools.rpi5 import check_gem_physmap_mapping_board_evidence_v1 as checker


class PhysmapMappingBoardEvidenceV1Tests(unittest.TestCase):
    def setUp(self):
        self.documents = checker.load_documents()

    def mutate_serial(self, old, new):
        data = self.documents["serial"]
        self.assertEqual(data.count(old), 1)
        return data.replace(old, new, 1)

    def assert_serial_rejected(self, data):
        with self.assertRaises(ValueError):
            checker.inspect_serial(data, require_immutable=False)

    def test_exact_board_capture_and_typed_report(self):
        result = checker.check()
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["evidence_type"], "physical-board-mapping-verification-only")
        self.assertEqual(result["serial_sha256"], checker.SERIAL_SHA)
        self.assertTrue(result["complete_capture"] and result["zero_transmit"])
        self.assertTrue(result["mapping_verification_pass"] and result["discard_before_route"])
        self.assertFalse(result["route_dma_irq_queues_packets_tx_activated"])
        self.assertFalse(result["rp1_identity_or_link_success_claimed"])
        self.assertEqual(result["restoration"]["counts"], [512, 518, 524])
        self.assertTrue(result["restoration"]["independent_nvme_return"])
        self.assertTrue(result["restoration"]["exact_triple_restored"])
        self.assertEqual(result["source_receipts"]["source_files"], 1742)
        self.assertEqual(result["source_receipts"]["receipt_files"], 14270)
        completed = subprocess.run([sys.executable, str(Path(checker.__file__).resolve())],
            cwd=checker.ROOT, text=True, capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), checker.compact(result))
        report = json.loads((checker.ROOT /
            "build/rpi5/gem-physmap-mapping-board-evidence-20261014-v1.json").read_text())
        self.assertEqual(report, checker.compact(result))

    def test_link_end_alias_order_and_accounting_mutations(self):
        self.assert_serial_rejected(self.mutate_serial(b"LINK_CALL=0", b"LINK_CALL=1"))
        end = (b"RPI5XNU:PCIEID:END OK=1 PHASE=1 LAST=1 LIFE=0 FLAGS=00 ID=00000000 "
            b"COMMAND=0000 BAR1=00000000 GEN=0 LANES=0")
        self.assert_serial_rejected(self.mutate_serial(end, end.replace(b"OK=1", b"OK=0")))
        self.assert_serial_rejected(self.mutate_serial(
            b"DMA_ALIAS PAGE=0 VA=1", b"DMA_ALIAS PAGE=1 VA=1"))
        data = self.documents["serial"]
        first = data.index(b"RPI5XNU:PCIEID:DMA_ALIAS PAGE=0 VA=1")
        first_end = data.index(b"\n", first) + 1
        second = first_end
        second_end = data.index(b"\n", second) + 1
        swapped = data[:first] + data[second:second_end] + data[first:first_end] + data[second_end:]
        self.assert_serial_rejected(swapped)
        self.assert_serial_rejected(self.mutate_serial(b"PAGES=5 MAX=6", b"PAGES=6 MAX=6"))
        alias = (b"DMA_ALIAS PAGE=0 VA=1 CACHE=6 PA=185516032 "
            b"PAR_R=4899916394764618496 PAR_W=4899916394764618496 ATTR_R=68")
        self.assert_serial_rejected(self.mutate_serial(alias, alias.replace(b"ATTR_R=68", b"ATTR_R=44")))

    def test_state_events_source_return_and_restoration_mutations(self):
        bad = copy.deepcopy(self.documents)
        source = str(checker.ROOT / "tools/rpi5/stage_gem_physmap_mapping_trial_v5.py")
        bad["state"]["source_sha256"][source] = "0" * 64
        with self.assertRaises(ValueError):
            checker.inspect_documents(bad)

        bad = copy.deepcopy(self.documents)
        rows = bad["events_text"].splitlines()
        event = json.loads(rows[1])
        event["offset"] += 1
        rows[1] = json.dumps(event, sort_keys=True)
        bad["events_text"] = "\n".join(rows) + "\n"
        with self.assertRaises(ValueError):
            checker.inspect_documents(bad)

        bad = copy.deepcopy(self.documents)
        bad["return"]["linux_boot_id"] = checker.BOOT_BEFORE
        with self.assertRaises(ValueError):
            checker.inspect_documents(bad)

        bad = copy.deepcopy(self.documents)
        bad["restored_result"]["next_catalog"] = bad["restored_result"]["next_catalog"][:-1]
        with self.assertRaises(ValueError):
            checker.inspect_documents(bad)

        bad = copy.deepcopy(self.documents)
        bad["offline_plan"]["media"]["ancestry"]["return_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            checker.inspect_documents(bad)


if __name__ == "__main__":
    unittest.main()
