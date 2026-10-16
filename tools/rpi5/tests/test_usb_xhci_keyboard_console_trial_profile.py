# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import usb_xhci_keyboard_console_trial_profile as profile


class USBXHCIKeyboardConsoleTrialProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = profile.derive()

    def text(self, name):
        return self.files[name].decode()

    def test_distinct_console_watchdog_preserves_service(self):
        transport = self.text("BCM2712PCIePHYTransport.cpp")
        owner = self.text("rpi5_pcie_watchdog_console_owner.inc")
        irq_owner = self.text("rpi5_pcie_irq_console_owner.inc")
        pe = self.text("pe_fiq.c")
        self.assertIn("pe_rpi5_watchdog_claim_usb_console", transport)
        self.assertNotIn("pe_rpi5_watchdog_claim_pcie(this", transport)
        self.assertIn("rpi5_pcie_watchdog_owner.inc", owner)
        self.assertIn("rpi5_usb_console_wdog_gate", owner)
        self.assertIn("rpi5_pcie_watchdog_console_begin", owner)
        self.assertIn("pe_rpi5_watchdog_check_usb_console", irq_owner)
        self.assertNotIn("pe_rpi5_watchdog_check_pcie(", irq_owner)
        self.assertIn('#include "rpi5_pcie_irq_console_owner.inc"', pe)
        self.assertIn('#include "rpi5_pcie_fw_console_owner.inc"', pe)

    def test_entry_returns_to_iokit_and_starts_worker(self):
        progress = self.text("BCM2712PCIeIDTrialProgress.inc")
        entry = progress[progress.index(
            'extern "C" void rpi5_pcie_id_trial_start(void);'):]
        self.assertIn("rpi5_terminal_watchdog_start()", entry)
        self.assertIn("kernel_thread_start(rpi5_usb_console_entry", entry)
        self.assertIn('serviceMatching("BCM2712PlatformExpert")', entry)
        self.assertIn("waitForService(", entry)
        self.assertLess(entry.index("waitForService("),
            entry.index("rpi5_pcie_id_trial_run();"))
        self.assertIn("transport->runUSBKeyboardConsole()", entry)
        self.assertLess(entry.index("rpi5_pcie_id_trial_run();"),
            entry.index("thread_terminate_self();"))
        self.assertNotIn("__attribute__((noreturn))", entry)
        self.assertNotIn('volatile("wfi"', entry)

    def test_iokit_dispatch_is_at_post_platform_bsd_boundary(self):
        from tools.rpi5 import build_usb_xhci_keyboard_console_trial as build
        source = build._iokitbsd_source()
        self.assertLess(source.index('IOService::publishResource("IOBSD")'),
            source.index("rpi5_pcie_id_trial_start(); /* Platform and BSD"))
        self.assertNotIn("rpi5_pcie_id_trial_start(); /*", source[
            :source.index("IOKitBSDInit( void )")])

    def test_worker_polls_stream_and_injects_console_bytes(self):
        identify = self.text("BCM2712RP1GEMIdentifyTransport.inc")
        self.assertIn("rpi5_rp1_xhci_k65_keyboard_stream_start", identify)
        self.assertIn("rpi5_rp1_xhci_k65_keyboard_stream_poll", identify)
        self.assertIn("cons_cinput((char)bytes[index])", identify)
        self.assertIn("IOSleep(16)", identify)
        self.assertIn("usbKeyboardThread!=current_thread()", identify)
        self.assertIn("usbKeyboardThread=current_thread()", identify)
        self.assertNotIn("kernel_thread_start", identify)
        self.assertNotIn("rpi5_rp1_usb_bme_disable(&usbBME)", identify)

    def test_live_map_and_irq_off_contract(self):
        identify = self.text("BCM2712RP1GEMIdentifyTransport.inc")
        self.assertNotIn("usbCapabilityMap->unmap()", identify)
        self.assertIn("stageK65KeyboardStream", identify)
        self.assertIn("STREAM255 IRQ_OFF", profile.marker("tag"))


if __name__ == "__main__":
    unittest.main()
