# SPDX-License-Identifier: BSD-2-Clause
import unittest

from tools.rpi5 import parse_usb_xhci_lifecycle_trial as parser
from tools.rpi5.tests import test_parse_usb_xhci_caps_trial as parent


MARKER = ("RPI5XNU:USB_XHCI_LIFECYCLE:ENTRY TAG=test CPUS=1 "
    "HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA")


def transcript():
    text = parent.transcript().replace(parent.MARKER, MARKER, 1).replace(
        "BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA",
        "BEGIN USB_XHCI_LIFECYCLE HALT_RESET_ONLY NO_PORT NO_IRQ NO_BME NO_DMA", 1).replace(
        "USB_XHCI_CAPS:STATE STEP=6", "USB_XHCI_CAPS:STATE STEP=8", 1)
    row = ("RPI5XNU:USB_XHCI_LIFECYCLE:STATE STEP=5 ERROR=0 READS=9 WRITES=2 "
        "POLLS=5 DELAY_US=1300 OP=00000020 CMD0=00000001 STS0=00000000 "
        "HALT_CMD=00000000 HALT_STS=00000001 RESET_CMD=00000002 "
        "CMD1=00000000 STS1=00000001")
    return text.replace("RPI5XNU:USB_XHCI_CAPS:DECODE ", row + "\nRPI5XNU:USB_XHCI_CAPS:DECODE ", 1)


class USBXHCILifecycleParserTests(unittest.TestCase):
    def test_exact_lifecycle_passes(self):
        result = parser.parse(transcript(), MARKER)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["controller_reset"])
        self.assertEqual(result["lifecycle"]["writes"], 2)

    def test_mutations_fail_closed(self):
        original = transcript()
        for changed in (
            original.replace("ERROR=0 READS=9 WRITES=2",
                             "ERROR=0 READS=9 WRITES=3", 1),
            original.replace("STS1=00000001", "STS1=00000801", 1),
            original.replace("RESET_CMD=00000002", "RESET_CMD=00000003", 1),
            original.replace("HALT_RESET_ONLY", "READ_ONLY", 1),
        ):
            with self.assertRaises(ValueError):
                parser.parse(changed, MARKER)


if __name__ == "__main__":
    unittest.main()
