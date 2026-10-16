# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCIPortResetTests(unittest.TestCase):
    def test_port_two_reset_success_and_fail_closed_paths(self):
        sources = [
            ROOT / "tools/rpi5/tests/rp1_usb_xhci_port_reset_host.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_port_reset.c",
        ]
        with tempfile.TemporaryDirectory(prefix="usb-xhci-port-") as folder:
            executable = Path(folder) / "host"
            result = subprocess.run(["xcrun", "clang", "-std=c11", "-O1",
                "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I",
                str(ROOT / "loader/rpi5"), *map(str, sources), "-o",
                str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True, text=True,
                timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("XHCI_PORT_RESET_PASS", result.stdout)

            target = Path(folder) / "port-reset.o"
            result = subprocess.run(["xcrun", "clang", "-target",
                "arm64-apple-macos11", "-std=c11", "-O2", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-I",
                str(ROOT / "loader/rpi5"), "-c", str(sources[1]), "-o",
                str(target)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
