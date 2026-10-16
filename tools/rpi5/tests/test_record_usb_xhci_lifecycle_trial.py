# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import record_usb_xhci_lifecycle_trial as wrapper


class USBXHCILifecycleRecorderTests(unittest.TestCase):
    def test_wrapper_selects_lifecycle_checker_and_parser(self):
        self.assertEqual(wrapper.lifecycle_check.build.PROFILE,
            "bcm2712-rp1-usb0-xhci-bounded-lifecycle-v1")
        self.assertTrue(callable(wrapper.lifecycle_evidence.parse))


if __name__ == "__main__":
    unittest.main()
