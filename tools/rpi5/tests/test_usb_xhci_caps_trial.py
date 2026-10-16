# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import unittest

from tools.rpi5 import build_gem_dma_batch_trial as composer
from tools.rpi5 import usb_xhci_caps_trial_profile as profile


class USBXHCICapabilityTrialTests(unittest.TestCase):
    def test_profile_is_read_only_and_retains_passed_provider(self):
        files = profile.derive()
        header = files["BCM2712PCIePHYTransport.h"].decode()
        transport = files["BCM2712RP1GEMIdentifyTransport.inc"].decode()
        progress = files["BCM2712PCIeIDTrialProgress.inc"].decode()
        self.assertIn("observePreparedFullProvider()", transport)
        self.assertIn("observeUSB0Capabilities()", transport)
        self.assertLess(transport.index("observePreparedFullProvider()"),
            transport.index("observeUSB0Capabilities()"))
        self.assertIn("rpi5_rp1_xhci_caps_decode", transport)
        self.assertIn("kIODirectionNone", transport)
        self.assertIn("kIOMapInhibitCache", transport)
        self.assertNotIn("usbCapabilityMap->write", transport)
        self.assertNotIn("usbCapabilityMap->set", transport)
        self.assertIn("uint32_t value=*reinterpret_cast<volatile uint32_t *>", transport)
        self.assertIn("usbCapabilityMap->unmap()", transport)
        self.assertIn("usbObservationReads", header)
        self.assertIn("BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA", progress)
        self.assertIn("RPI5XNU:USB_XHCI_CAPS:DECODE", progress)

    def test_frozen_parent_and_new_sources_exist(self):
        self.assertTrue(profile.FROZEN.is_dir())
        self.assertGreater(len(list(profile.FROZEN.iterdir())), 30)
        for name in ("rp1_usb_xhci_caps.c", "rp1_usb_xhci_caps.h",
                "rp1_usb_device_handoff.c", "rp1_usb_device_handoff.h"):
            self.assertTrue((profile.ROOT / "loader/rpi5" / name).is_file())

    def test_loader_declares_only_usb0_in_addition_to_existing_rp1_pages(self):
        original = (composer.BASE / "probe_main.c").read_text()
        parent_text = profile.parent.loader(original)
        transformed = profile.loader(original)
        self.assertIn('rpi5_rp1_device_handoff(', parent_text)
        self.assertNotIn('rpi5_rp1_usb_device_handoff(', parent_text)
        self.assertIn('#include "rp1_usb_device_handoff.h"', transformed)
        self.assertIn('rpi5_rp1_usb_device_handoff(', transformed)
        self.assertIn("RANGES=3 PAGES=70 GEM_CLOCK_USB0_ONLY DECLARATIONS_ONLY RP1_MMIO=0",
            transformed)


if __name__ == "__main__":
    unittest.main()
