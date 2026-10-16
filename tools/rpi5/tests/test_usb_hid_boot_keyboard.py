# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class USBHIDBootKeyboardTests(unittest.TestCase):
    def test_host_faults_and_a76_target(self):
        source = ROOT / "loader/rpi5/usb_hid_boot_keyboard.c"
        host = Path(__file__).with_name("usb_hid_boot_keyboard_host.c")
        include = ROOT / "loader/rpi5"
        with tempfile.TemporaryDirectory(prefix="rpi5-usb-hid-") as name:
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
            self.assertIn("USB_HID_BOOT_KEYBOARD_PASS", result.stdout)

            target = folder / "usb_hid_boot_keyboard.o"
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
