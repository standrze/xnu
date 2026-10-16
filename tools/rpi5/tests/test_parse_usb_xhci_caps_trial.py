import unittest
from pathlib import Path

from tools.rpi5 import parse_usb_xhci_caps_trial as parser


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "build/rpi5/gem-full-provider-trial-capture-20261014-v12/serial.bin"
MARKER = "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG=test CPUS=1 READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA"


def transcript():
    text = BASE.read_text(errors="replace").replace(
        "RPI5XNU:FULL_PROVIDER:ENTRY TAG=", "RPI5XNU:USB_XHCI_CAPS:ENTRY TAG=", 1)
    marker_line = next(line for line in text.splitlines()
                       if line.startswith("RPI5XNU:USB_XHCI_CAPS:ENTRY TAG="))
    text = text.replace(marker_line, MARKER, 1).replace(
        "RPI5XNU:PCIEID:BEGIN FULL_PROVIDER PREFERRED_RAM_ONLY NO_QUEUE NO_BME NO_DMA",
        "RPI5XNU:PCIEID:BEGIN USB_XHCI_CAPS READ_ONLY NO_RESET NO_PORT NO_IRQ NO_BME NO_DMA", 1)
    rows = "\n".join((
        "RPI5XNU:USB_XHCI_CAPS:STATE STEP=6 ERROR=0 READS=16 PHYSICAL=133146083328 BYTES=1048576",
        "RPI5XNU:USB_XHCI_CAPS:RAW0 CAP=01100020 HCS1=02000820 HCS2=00000000 HCS3=00000000 HCC1=0240fe6d DBOFF=00001000 RTSOFF=00002000 HCC2=00000000",
        "RPI5XNU:USB_XHCI_CAPS:RAW1 CAP=01100020 HCS1=02000820 HCS2=00000000 HCS3=00000000 HCC1=0240fe6d DBOFF=00001000 RTSOFF=00002000 HCC2=00000000",
        "RPI5XNU:USB_XHCI_CAPS:DECODE VERSION=0110 CAPLEN=32 SLOTS=32 INTRS=8 PORTS=2 SCRATCH=0 DB=00001000 RT=00002000 XECP=00000900 AC64=1 CSZ64=1 PPC=1",
    ))
    return text.replace("RPI5XNU:PCIEID:END ", rows + "\nRPI5XNU:PCIEID:END ", 1)


class USBXHCICapabilityParserTests(unittest.TestCase):
    def test_exact_evidence_passes(self):
        result = parser.parse(transcript(), MARKER)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["decode"]["version"], 0x110)
        self.assertEqual(result["full_provider"]["packet_span_records"], 128)

    def test_mutations_fail_closed(self):
        original = transcript()
        mutations = (
            original.replace("USB_XHCI_CAPS:STATE STEP=6 ERROR=0 READS=16",
                             "USB_XHCI_CAPS:STATE STEP=6 ERROR=0 READS=15", 1),
            original.replace("RAW1 CAP=01100020", "RAW1 CAP=01100024", 1),
            original.replace("VERSION=0110", "VERSION=0100", 1),
            original.replace("NO_RESET", "RESET", 1),
            original.replace(MARKER, MARKER + "\n" + MARKER, 1),
        )
        for changed in mutations:
            with self.subTest(changed=changed[:80]), self.assertRaises(ValueError):
                parser.parse(changed, MARKER)


if __name__ == "__main__":
    unittest.main()
