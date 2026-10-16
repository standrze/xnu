# SPDX-License-Identifier: BSD-2-Clause
"""Immutable package/checker round trip for queue admission v1."""
import tempfile
from pathlib import Path
import json
import os
import subprocess
import sys
import unittest

from tools.rpi5 import build_gem_queue_admission_candidate as builder
from tools.rpi5 import check_gem_queue_admission_candidate as checker


class GEMQueueAdmissionPackageTests(unittest.TestCase):
    def test_build_and_check_exact_default_off_package(self):
        with tempfile.TemporaryDirectory(
            prefix="gem-queue-package-", dir=builder.ROOT / "build/rpi5"
        ) as name:
            output = Path(name) / "candidate"
            manifest = builder.build(output)
            digest = builder.sha256(output / "manifest.json")
            report = checker.check(output, digest)
            self.assertEqual(report["result"], "SOFTWARE_QUALIFIED_DEFAULT_OFF")
            self.assertFalse(report["bme"])
            self.assertFalse(report["dma"])
            self.assertFalse(report["irq"])
            self.assertFalse(report["packets"])
            self.assertTrue(report["physical_prerequisites_satisfied"])
            self.assertFalse(manifest["production_wired"])
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            direct = subprocess.run(
                [
                    sys.executable,
                    str(checker.__file__),
                    str(output),
                    "--expected-manifest-sha256",
                    digest,
                ],
                cwd=builder.ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=30,
            )
            self.assertEqual(direct.returncode, 0, direct.stderr)
            direct_report = json.loads(direct.stdout)
            self.assertEqual(
                direct_report["result"], "SOFTWARE_QUALIFIED_DEFAULT_OFF"
            )
            self.assertEqual(direct_report["manifest_sha256"], digest)
            with self.assertRaisesRegex(ValueError, "Manifest pin differs"):
                checker.check(output, "0" * 64)


if __name__ == "__main__":
    unittest.main()
