# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCINoopTests(unittest.TestCase):
    def test_exact_cpu_owned_image_and_a76_compile(self):
        sources = [
            ROOT / "tools/rpi5/tests/rp1_usb_xhci_noop_host.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_noop.c",
            ROOT / "loader/rpi5/rp1_usb_xhci_dma_layout.c",
        ]
        with tempfile.TemporaryDirectory(prefix="xhci-noop-") as folder:
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
            self.assertIn("NO_MMIO NO_BME NO_DMA", result.stdout)
            for source in sources[1:]:
                target = folder / (source.name + ".o")
                result = subprocess.run(["xcrun", "clang", "-target",
                    "arm64-apple-macos11", "-std=c11", "-O2",
                    "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra",
                    "-Werror", "-I", str(ROOT / "loader/rpi5"), "-c",
                    str(source), "-o", str(target)], capture_output=True,
                    text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
