# SPDX-License-Identifier: BSD-2-Clause
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools.rpi5 import check_gem_cpu_ring_physmap_composite_closure_v1 as closure


class CPUringPhysmapCompositeClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = closure.load_documents()

    def changed(self):
        return copy.deepcopy(self.documents)

    def test_exact_composite_closure_passes_without_overclaim(self):
        report = closure.inspect_documents(self.documents)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["cpu_ring_physmap_trial_closed"])
        self.assertEqual(report["restoration"]["catalog_counts"], [524, 530, 536])
        self.assertEqual(report["restoration"]["restored_triple_sha256"], closure.RESTORED_TRIPLE)
        self.assertTrue(report["restoration"]["legacy_catalog_replay"])
        self.assertFalse(report["restoration"]["historical_archives_reverified"])
        self.assertFalse(report["legacy_return"]["capture_valid"])
        self.assertTrue(report["authority"]["cpu_owned_descriptor_store_readback_and_owner_lifecycle"])
        for key in ("dma", "irq_delivery", "queue_publication", "packets", "ethernet_proven"):
            self.assertFalse(report["authority"][key])

    def test_direct_cli_from_repository_root_needs_no_pythonpath(self):
        environment = dict(os.environ)
        environment.pop("PYTHONPATH", None)
        script = Path(closure.__file__).resolve()
        completed = subprocess.run(
            [sys.executable, str(script)], cwd=closure.ROOT, env=environment,
            check=True, capture_output=True, text=True,
        )
        self.assertEqual(json.loads(completed.stdout), closure.inspect_documents(self.documents))
        self.assertEqual(completed.stderr, "")

    def test_altered_board_report_is_rejected(self):
        documents = self.changed()
        documents["board_report"]["cpu_ring_physical_trial_pass"] = False
        with self.assertRaisesRegex(ValueError, "supplemental CPU-ring board report"):
            closure.inspect_documents(documents)

    def test_altered_serial_is_rejected(self):
        documents = self.changed()
        documents["serial"] = documents["serial"][:-1] + bytes([documents["serial"][-1] ^ 1])
        with self.assertRaisesRegex(ValueError, "immutable CPU-ring serial"):
            closure.inspect_documents(documents)

    def test_altered_return_boot_id_is_rejected(self):
        documents = self.changed()
        documents["return"]["linux_boot_id"] = "00000000-0000-0000-0000-000000000000"
        with self.assertRaisesRegex(ValueError, "fresh NVMe boot"):
            closure.inspect_documents(documents)

    def test_altered_restore_triple_is_rejected(self):
        documents = self.changed()
        documents["restored_result"]["publication"]["protected_files_sha256"]["probe.bin"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "restored normal triple"):
            closure.inspect_documents(documents)

    def test_altered_catalog_is_rejected(self):
        documents = self.changed()
        documents["restored_result"]["next_catalog"][-1]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "catalog536"):
            closure.inspect_documents(documents)

    def test_false_historical_reverification_claim_is_rejected(self):
        documents = self.changed()
        documents["restored_result"]["historical_archives_reverified"] = True
        with self.assertRaisesRegex(ValueError, "must not claim archive re-verification"):
            closure.inspect_documents(documents)


if __name__ == "__main__":
    unittest.main()
