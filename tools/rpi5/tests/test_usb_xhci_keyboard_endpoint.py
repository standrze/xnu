# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class USBXHCIKeyboardEndpointTests(unittest.TestCase):
    def test_exact_k65_endpoint_context_and_interrupt_transfer(self):
        sources = [
            ROOT / "tools/rpi5/tests/usb_xhci_keyboard_endpoint_host.c",
            ROOT / "loader/rpi5/usb_xhci_keyboard_endpoint.c",
            ROOT / "loader/rpi5/usb_xhci_device_context.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
        ]
        with tempfile.TemporaryDirectory(prefix="usb-xhci-keyboard-endpoint-") as folder:
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
            self.assertIn("USB_XHCI_KEYBOARD_ENDPOINT_PASS", result.stdout)

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
