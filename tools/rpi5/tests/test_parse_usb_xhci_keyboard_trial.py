# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import unittest

from tools.rpi5.parse_usb_xhci_keyboard_trial import parse


ROOT = Path(__file__).resolve().parents[3]


class USBXHCIKeyboardParserTests(unittest.TestCase):
    def fixture(self):
        path = ROOT / "build/rpi5/usb-xhci-enumerate-capture-20261015-v1/serial.bin"
        text = path.read_bytes().decode(errors="replace")
        text = text.replace("USB_XHCI_ENUM", "USB_XHCI_KBD")
        text = text.replace(
            "POLLING PORT2 SLOT ADDRESS EP0 K65 NO_IRQ BME_LEASE DMA",
            "POLLING PORT2 SLOT ADDRESS EP0 K65 DCI3 HID_SETUP REPORT8 "
            "NO_IRQ BME_LEASE DMA")
        text = text.replace("TRIAL_STEP=6 TRIAL_ERROR=0",
            "TRIAL_STEP=8 TRIAL_ERROR=0")
        enumeration_run = next(line for line in text.splitlines()
            if "RPI5XNU:USB_XHCI_KBD:RUN " in line)
        text = text.replace(enumeration_run, enumeration_run.replace(
            "HALT_CMD=00000000 HALT_STS=00000011",
            "HALT_CMD=00000001 HALT_STS=00000010 LIVE=1"))
        device = next(line for line in text.splitlines()
            if "RPI5XNU:USB_XHCI_KBD:DEVICE " in line)
        rp1 = 68909694976
        rows = (
            f"{device}\n"
            "RPI5XNU:USB_XHCI_KBD:KBD_PLAN SLOT=1 DCI=3 "
            f"COMMAND={rp1 + 0x1020} SETUP_FIRST=12 SETUP_COUNT=3 "
            f"REPORT_DMA={rp1 + 0x49000} REPORT_BYTES=8\n"
            "RPI5XNU:USB_XHCI_KBD:KBD_RUN STEP=7 ERROR=0 READS=5 "
            "WRITES=14 POLLS=6 DELAY_US=0 DMA_CHECKS=9 EVENT_INDEX=12 "
            f"PSC=0 SLOT=1 DCI=3 TRANSFER=3 EVENT_PARAM={rp1 + 0x47000} "
            "EVENT_STATUS=01000000 EVENT_CONTROL=01038001 "
            "REPORT=0000000000000000 OUTPUT_COUNT=0 "
            "OUTPUT0=00 HALT_CMD=00000000 HALT_STS=00000011"
        )
        text = text.replace(device, rows)
        marker = next(line.strip() for line in text.splitlines()
            if "RPI5XNU:USB_XHCI_KBD:ENTRY " in line)
        return text, marker

    def test_accepts_exact_first_report_and_rejects_dci_mutation(self):
        text, marker = self.fixture()
        result = parse(text, marker)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["endpoint_id"], 3)
        self.assertEqual(result["interrupt_reports"], 1)
        self.assertEqual(result["report"], "0000000000000000")
        with self.assertRaisesRegex(ValueError, "plan differs"):
            parse(text.replace("KBD_PLAN SLOT=1 DCI=3",
                "KBD_PLAN SLOT=1 DCI=2"), marker)


if __name__ == "__main__":
    unittest.main()
