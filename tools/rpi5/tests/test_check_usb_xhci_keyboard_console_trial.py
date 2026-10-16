# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import json
import tempfile
import unittest

from tools.rpi5 import check_usb_xhci_keyboard_console_trial as check


class CheckUSBXHCIKeyboardConsoleTrialTests(unittest.TestCase):
    def test_exact_candidate_passes(self):
        package = check.build.ROOT / (
            "build/rpi5/usb-xhci-keyboard-console-candidate-20261016-v13")
        result = check.check(package)
        self.assertTrue(result["accepted"], result["errors"])
        self.assertTrue(result["software_only"])
        self.assertFalse(result["hardware_executed"])
        self.assertFalse(result["staged"])

    def test_wrong_package_fails_closed(self):
        with tempfile.TemporaryDirectory(dir=check.build.ROOT / "build/rpi5",
                prefix="not-usb-keyboard-console-") as name:
            path = Path(name)
            (path / "manifest.json").write_text(json.dumps({"profile": "wrong"}))
            result = check.check(path)
            self.assertFalse(result["accepted"])
            self.assertIn("distinct USB keyboard console package required",
                result["errors"])


if __name__ == "__main__":
    unittest.main()
