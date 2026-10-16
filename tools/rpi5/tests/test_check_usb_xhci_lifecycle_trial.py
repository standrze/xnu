# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import check_usb_xhci_lifecycle_trial as check


class CheckUSBXHCILifecycleTrialTests(unittest.TestCase):
    def test_exact_candidate_passes(self):
        package = check.build.ROOT / "build/rpi5/usb-xhci-lifecycle-candidate-20261014-v2"
        result = check.check(package)
        self.assertTrue(result["accepted"], result["errors"])
        self.assertTrue(result["software_only"])


if __name__ == "__main__":
    unittest.main()
