# SPDX-License-Identifier: BSD-2-Clause
import json
from pathlib import Path
import unittest

from tools.rpi5 import parse_usb_xhci_caps_trial as caps
from tools.rpi5 import parse_usb_xhci_enumerate_trial as parser

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "build/rpi5/usb-xhci-noop-capture-20261015-v6/serial.bin"
SOURCE_MANIFEST = ROOT / "build/rpi5/usb-xhci-noop-candidate-20261015-v11/manifest.json"
ENUM_MANIFEST = ROOT / "build/rpi5/usb-xhci-enumerate-candidate-20261015-v4/manifest.json"


class USBXHCIEnumerateParserTests(unittest.TestCase):
    @classmethod
    def fixture(cls):
        text = SOURCE.read_text(errors="replace")
        old_marker = json.loads(SOURCE_MANIFEST.read_text())["trial_marker"]
        marker = json.loads(ENUM_MANIFEST.read_text())["trial_marker"]
        text = text.replace(old_marker, marker).replace(
            "USB_XHCI_NOOP", "USB_XHCI_ENUM")
        text = text.replace(
            "BEGIN USB_XHCI_ENUM POLLING ONE_NOOP NO_PORT NO_IRQ BME_LEASE DMA",
            "BEGIN USB_XHCI_ENUM POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA")
        lines = text.splitlines()
        image_line = next(line for line in lines
            if "RPI5XNU:USB_XHCI_ENUM:IMAGE " in line).strip()
        fields = caps._fields(image_line)
        cr = caps._decimal(fields, "CR")
        replacement = [
            f"RPI5XNU:USB_XHCI_ENUM:PLAN ENABLE={cr} ENABLE_CTL=00002401 TD_COUNT=4 TRB_COUNT=12 RING={cr + 0x45000}",
            "RPI5XNU:USB_XHCI_ENUM:RUN STEP=10 ERROR=0 READS=7 WRITES=30 POLLS=9 DELAY_US=0 DMA_CHECKS=15 SLOT=5 PSC=1 EVENT_INDEX=7 HALT_CMD=00000000 HALT_STS=00000011",
            "RPI5XNU:USB_XHCI_ENUM:PORT STEP=4 ERROR=0 PORT=2 OFFSET=00000430 BEFORE=00000e01 AFTER=00200e03 FINAL=00000e03 SPEED=3 LINK=0 WRITES=2 POLLS=2",
            f"RPI5XNU:USB_XHCI_ENUM:DEVICE SLOT=5 PORT=2 SPEED=3 EP0=64 ADDRESS_CMD={cr + 16} VENDOR=1b1c PRODUCT=1baf USB=0200 CONFIG_BYTES=91 INTERFACES=3 INTERFACE=0 ENDPOINT=81 PACKET=16 INTERVAL=4 REPORT=154",
        ]
        for index, line in enumerate(lines):
            if "RPI5XNU:USB_XHCI_ENUM:RUN " in line:
                lines[index:index + 1] = replacement
                break
        return "\n".join(lines), marker

    def test_accepts_exact_enumeration_and_rejects_identity_mutation(self):
        text, marker = self.fixture()
        result = parser.parse(text, marker)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["slot"], 5)
        self.assertEqual(result["keyboard"]["endpoint"], 0x81)
        with self.assertRaisesRegex(ValueError, "K65 identity"):
            parser.parse(text.replace("ENDPOINT=81", "ENDPOINT=82"), marker)


if __name__ == "__main__":
    unittest.main()
