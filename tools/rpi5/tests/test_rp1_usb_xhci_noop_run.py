# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCINoopRunTests(unittest.TestCase):
    def test_polling_noop_success_and_faults(self):
        sources = [
            ROOT / "tools/rpi5/tests/rp1_usb_xhci_noop_run_host.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop_run.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
        ]
        with tempfile.TemporaryDirectory(prefix="xhci-noop-run-") as folder:
            folder = Path(folder)
            executable = folder / "host"
            result = subprocess.run(["xcrun", "clang", "-std=c11", "-O1",
                "-g", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I",
                str(ROOT / "loader/rpi5"), *map(str, sources), "-o",
                str(executable)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([executable], capture_output=True,
                text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("write_faults=16", result.stdout)
            self.assertIn("IRQ_OFF PORTS_UNTOUCHED", result.stdout)
            target = folder / "noop-run.o"
            result = subprocess.run(["xcrun", "clang", "-target",
                "arm64-apple-macos11", "-std=c11", "-O2", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-I",
                str(ROOT / "loader/rpi5"), "-c", str(sources[1]), "-o",
                str(target)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
