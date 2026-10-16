# SPDX-License-Identifier: BSD-2-Clause
"""Software-only catalog524 transport checks for the physmap CPU-ring trial."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5 import stage_gem_cpu_ring_physmap_trial_v1 as stage


class CPURingPhysmapTransportV1Tests(unittest.TestCase):
    def report(self):
        return stage.checker.inspect(stage.PACKAGE, stage.MANIFEST_SHA)

    def test_exact_package_mapping_and_zero_activation(self):
        report = self.report()
        self.assertTrue(stage.valid_report(report))
        self.assertEqual(stage.BASELINE_CATALOG, 524)
        self.assertEqual(stage.BASELINE_CATALOG_SHA,
            "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20")
        self.assertEqual(stage.BASELINE_BOOT, "2d237d96-a323-4df7-a8b4-ad9b4eb5f477")
        self.assertEqual(report["mapping_report_sha256"], stage.MAPPING_REPORT_SHA)
        self.assertTrue(report["zero_serial_transmit"])
        self.assertFalse(report["activation_authorized"])
        self.assertTrue(report["automatic_watchdog_return_required"])
        self.assertTrue(report["complete_capture_health_required"])
        self.assertTrue(all(report[name] is False for name in
            ("bme", "queues", "dma", "irq", "packets", "tx")))
        pins = stage.source_pins()
        self.assertEqual(pins[str(stage.PACKAGE / "manifest.json")], stage.MANIFEST_SHA)
        self.assertEqual(pins[str(stage.PACKAGE / "probe.bin")], stage.IMAGE_SHA)
        self.assertEqual(pins[str(stage.case.MAPPING_REPORT)], stage.MAPPING_REPORT_SHA)

    def test_wrong_package_report_and_activation_are_rejected(self):
        with self.assertRaises(ValueError):
            stage.checker.inspect(stage.ROOT / "build/rpi5/gem-cpu-ring-retry-trial-20261014-v7",
                stage.MANIFEST_SHA)
        with self.assertRaises(ValueError):
            stage.checker.inspect(stage.PACKAGE, "0" * 64)
        report = self.report()
        for name, value in (("package", "/wrong/package"),
                ("mapping_report_sha256", "0" * 64),
                ("activation_authorized", True), ("bme", True), ("tx", True)):
            mutated = copy.deepcopy(report)
            mutated[name] = value
            with self.assertRaises(ValueError):
                stage.valid_report(mutated)

    def test_catalog_and_restoration_ancestry_mutations_are_rejected(self):
        accepted = stage.baseline(stage.BASELINE, stage.BASELINE_SEAL, stage.BASELINE_PLAN)
        self.assertTrue(stage.validate_baseline_context(accepted))
        for mutation in ("catalog", "boot", "triple"):
            altered = copy.deepcopy(accepted)
            if mutation == "catalog":
                altered["result"]["next_catalog_sha256"] = "0" * 64
            elif mutation == "boot":
                altered["result"]["publication"]["identity"]["boot_id"] = "0" * 36
            else:
                altered["result"]["publication"]["protected_files_sha256"]["probe.bin"] = "0" * 64
            with self.assertRaises(ValueError):
                stage.validate_baseline_context(altered)
        mapping = json.loads(stage.case.MAPPING_REPORT.read_text())
        mutations = []
        changed = copy.deepcopy(mapping); changed["restoration"]["counts"] = [512, 524]; mutations.append(changed)
        changed = copy.deepcopy(mapping); changed["restoration"]["catalogs"][-1]["sha256"] = "0" * 64; mutations.append(changed)
        changed = copy.deepcopy(mapping); changed["route_dma_irq_queues_packets_tx_activated"] = True; mutations.append(changed)
        for changed in mutations:
            with self.assertRaises(ValueError):
                stage.validate_mapping_prerequisite(changed)

    def test_prepare_is_inert_bounded_and_remote_source_is_closed(self):
        with tempfile.TemporaryDirectory(prefix="cpu-ring-physmap-v1-",
                dir=stage.ROOT / "build/rpi5") as name:
            folder = Path(name)
            folder.rmdir()
            completed = subprocess.run([
                sys.executable, str(Path(stage.__file__).resolve()), "prepare",
                "--baseline", str(stage.BASELINE),
                "--prior-seal-sha256", stage.BASELINE_SEAL,
                "--prior-plan-sha256", stage.BASELINE_PLAN,
                "--linux-boot-id", stage.BASELINE_BOOT,
                "--output", str(folder),
            ], cwd=stage.ROOT, text=True, capture_output=True, timeout=180)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            prepared = json.loads(completed.stdout)
            self.assertEqual(prepared["status"], "prepared_only")
            self.assertEqual(prepared["metrics"]["prior_catalog_count"], 524)
            admission = prepared["metrics"]["recorder_admission"]
            self.assertTrue(admission["modem_gate_bound_before_arm"])
            self.assertTrue(admission["recorder_namespace_bound_without_serial"])
            self.assertEqual(admission["transmitted_bytes"], 0)
            self.assertFalse(admission["hardware_executed"])
            checkpoint = json.loads((folder / "checkpoint.json").read_text())
            pin = prepared["checkpoint_sha256"]
            base = checkpoint["payload"]["media_plan"]
            self.assertTrue(base["no_reboot"])
            self.assertTrue(base["automatic_watchdog_return"] if
                "automatic_watchdog_return" in base else
                base["preflight"]["automatic_watchdog_return_required"])
            plan, plan_sha = stage.engine.plan_from_seal(checkpoint, pin, stage.engine.TRIAL,
                "54" * 16, "/home/sandrzej/xnu-cpu-ring-physmap-v1-offline", base)
            source = stage.engine.remote_source(checkpoint, pin, plan, plan_sha)
            compile(source, "<cpu-ring-physmap-v1-remote>", "exec")
            self.assertEqual(plan["historical_catalog_sha256"], stage.BASELINE_CATALOG_SHA)
            self.assertEqual(plan["media"]["source_sha256"][str(stage.case.MAPPING_REPORT)],
                stage.MAPPING_REPORT_SHA)
            self.assertRegex(hashlib.sha256(source.encode()).hexdigest(), r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
