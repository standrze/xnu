# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCIKeyboardInputTests(unittest.TestCase):
    def test_polling_k65_first_report_and_decoder_failure(self):
        sources = [
            ROOT / "tools/rpi5/tests/rp1_usb_xhci_keyboard_input_host.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_keyboard_input.c",
            ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.c",
            ROOT / "loader/rpi5/usb_hid_boot_setup.c",
            ROOT / "loader/rpi5/usb_hid_boot_keyboard.c",
            ROOT / "loader/rpi5/usb_xhci_device_context.c",
            ROOT / "loader/rpi5/usb_xhci_control_transfer.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
        ]
        with tempfile.TemporaryDirectory(
                prefix="usb-xhci-keyboard-input-") as folder:
            executable = Path(folder) / "host"
            result = subprocess.run(["xcrun", "clang", "-std=c11", "-O1",
                "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I",
                str(ROOT / "loader/rpi5"), *map(str, sources), "-o",
                str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("XHCI_KEYBOARD_INPUT_PASS", result.stdout)

            for source in sources[1:]:
                target = Path(folder) / (source.stem + ".o")
                result = subprocess.run(["xcrun", "clang", "-target",
                    "arm64-apple-macos11", "-std=c11", "-O2",
                    "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra",
                    "-Werror", "-I", str(ROOT / "loader/rpi5"), "-c",
                    str(source), "-o", str(target)], capture_output=True,
                    text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
