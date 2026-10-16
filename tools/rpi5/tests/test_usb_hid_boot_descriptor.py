# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class USBHIDBootDescriptorTests(unittest.TestCase):
    def test_k65_boot_interface_selection_and_faults(self):
        sources = [ROOT / "tools/rpi5/tests/usb_hid_boot_descriptor_host.c",
            ROOT / "loader/rpi5/usb_hid_boot_descriptor.c"]
        with tempfile.TemporaryDirectory(prefix="usb-k65-descriptor-") as folder:
            executable = Path(folder) / "host"
            command = ["xcrun", "clang", "-std=c11", "-O1", "-g",
                "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined",
                "-I", str(ROOT / "loader/rpi5"), *map(str, sources),
                "-o", str(executable)]
            result = subprocess.run(command, capture_output=True, text=True,
                timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True, text=True,
                timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("USB_K65_DESCRIPTOR_PASS", result.stdout)
            target = Path(folder) / "descriptor.o"
            result = subprocess.run(["xcrun", "clang", "-target",
                "arm64-apple-macos11", "-std=c11", "-O2", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-I",
                str(ROOT / "loader/rpi5"), "-c", str(sources[1]), "-o",
                str(target)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
