# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCICapabilityTests(unittest.TestCase):
    def test_decoder_faults_and_a76_target(self):
        source = ROOT / "loader/rpi5/rp1_usb_xhci_caps.c"
        host = Path(__file__).with_name("rp1_usb_xhci_caps_host.c")
        include = ROOT / "loader/rpi5"
        with tempfile.TemporaryDirectory(prefix="rpi5-xhci-caps-") as name:
            folder = Path(name)
            executable = folder / "host"
            command = [
                "xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(include), str(host),
                str(source), "-o", str(executable),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RP1_USB_XHCI_CAPS_PASS", result.stdout)

            target = folder / "rp1_usb_xhci_caps.o"
            command = [
                "xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding",
                "-fno-builtin", "-fno-stack-protector", "-O2", "-Wall", "-Wextra",
                "-Werror", "-I", str(include), "-c", str(source), "-o", str(target),
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertGreater(target.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
