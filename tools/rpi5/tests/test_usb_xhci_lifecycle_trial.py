# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import usb_xhci_lifecycle_trial_profile as profile


class USBXHCILifecycleTrialTests(unittest.TestCase):
    def test_profile_preserves_usb1_and_limits_writes(self):
        files = profile.derive()
        header = files["BCM2712PCIePHYTransport.h"].decode()
        transport = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
        progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
        self.assertIn("rpi5_rp1_xhci_halt_reset", transport)
        self.assertIn("usbLifecycleWrite", header)
        self.assertIn("offset!=self->usbCapabilityObserved.capability_length", transport)
        self.assertNotIn("PortReg", transport)
        self.assertNotIn("doorbell", transport.lower())
        self.assertIn("USB_XHCI_LIFECYCLE:STATE", progress)
        self.assertIn("HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA", progress)


if __name__ == "__main__":
    unittest.main()
