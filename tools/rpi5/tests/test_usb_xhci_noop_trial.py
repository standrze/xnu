# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import usb_xhci_noop_trial_profile as profile


class USBXHCINoopTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = {name: data.decode(errors="replace")
            for name, data in profile.derive().items()}

    def test_exact_bme_lease_and_noop_are_composed(self):
        joined = "\n".join(self.files.values())
        for token in ("rpi5_rp1_usb_bme_enable", "rpi5_rp1_usb_bme_disable",
                "rpi5_rp1_xhci_run_noop", "stageNoOpCommand"):
            self.assertIn(token, joined)

    def test_no_port_or_interrupt_enable_path(self):
        joined = "\n".join(self.files.values())
        self.assertNotIn("PortReg", joined)
        self.assertNotIn("Enable Slot Command", joined)
        self.assertIn("offset==rt+0x20", joined)

    def test_usb_provider_replaces_gem_provider(self):
        header = self.files["BCM2712PCIePHYTransport.h"]
        self.assertIn("BCM2712USBXHCIMemory *dmaMemory", header)
        self.assertNotIn("BCM2712GEMDMAMemory *dmaMemory", header)

    def test_recurring_admission_accepts_only_prepared_or_staged(self):
        progress = self.files["BCM2712PCIeIDTrialProgress.inc"]
        self.assertIn("state!=BCM2712USBXHCIMemory::Prepared &&", progress)
        self.assertIn("state!=BCM2712USBXHCIMemory::Staged", progress)
        self.assertNotIn("state!=BCM2712USBXHCIMemory::Held", progress)


if __name__ == "__main__":
    unittest.main()
