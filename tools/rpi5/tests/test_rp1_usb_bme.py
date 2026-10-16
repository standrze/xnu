# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


class RP1USBBMETests(unittest.TestCase):
    def test_exact_command_bit_lease(self):
        sources = [
            ROOT / "tools/rpi5/tests/rp1_usb_bme_host.c",
            ROOT / "loader/rpi5/rp1_usb_bme.c",
        ]
        with tempfile.TemporaryDirectory(prefix="rp1-usb-bme-") as folder:
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
            self.assertIn("EXACT_COMMAND_BIT2_ONLY", result.stdout)
            target = folder / "bme.o"
            result = subprocess.run(["xcrun", "clang", "-target",
                "arm64-apple-macos11", "-std=c11", "-O2", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror", "-I",
                str(ROOT / "loader/rpi5"), "-c", str(sources[1]), "-o",
                str(target)], capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
