# SPDX-License-Identifier: BSD-2-Clause
"""Focused closure and mutation tests for the ring/physmap successor."""
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.rpi5 import check_gem_cpu_ring_physmap_trial as checker


class RingPhysmapTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = os.environ.get("RPI5_RING_PHYSMAP_PACKAGE")
        pin = os.environ.get("RPI5_RING_PHYSMAP_MANIFEST_SHA")
        if not package or not pin:
            raise unittest.SkipTest("final ring/physmap package not supplied")
        cls.package = Path(package).resolve()
        cls.pin = pin
        cls.manifest = json.loads((cls.package / "manifest.json").read_text())

    def test_final_package_is_software_only_and_complete(self):
        report = checker.check(self.package, self.pin)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(report["page_granular_physmap"])
        self.assertTrue(report["cpu_owned_ring_structure_only"])
        for key in ("bme", "queues", "dma", "irq", "packets", "tx",
                    "hardware_executed", "staged"):
            self.assertFalse(report[key])

    def test_activation_and_vm_object_mutations_fail(self):
        original = Path.read_text
        manifest_path = self.package / "manifest.json"
        for key, value in (("bme_enable", True), ("packet_spans", 1),
                           ("descriptor_pages", 3), ("tx_enable", True)):
            mutant = copy.deepcopy(self.manifest)
            mutant[key] = value
            raw = json.dumps(mutant, sort_keys=True)
            pin = hashlib.sha256(raw.encode()).hexdigest()
            def read_text(path, *args, _raw=raw, **kwargs):
                return _raw if path == manifest_path else original(path, *args, **kwargs)
            with patch.object(Path, "read_text", read_text), self.assertRaises(ValueError):
                checker.check(self.package, pin)

        mutant = copy.deepcopy(self.manifest)
        victim = next(old for old in mutant["replaced_objects"] if Path(old).name == "loose_ends.o")
        mutant["replaced_objects"].pop(victim)
        raw = json.dumps(mutant, sort_keys=True)
        pin = hashlib.sha256(raw.encode()).hexdigest()
        def read_text(path, *args, **kwargs):
            return raw if path == manifest_path else original(path, *args, **kwargs)
        with patch.object(Path, "read_text", read_text), self.assertRaises(ValueError):
            checker.check(self.package, pin)


if __name__ == "__main__":
    unittest.main()
