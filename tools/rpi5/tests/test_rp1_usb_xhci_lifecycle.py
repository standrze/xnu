# SPDX-License-Identifier: BSD-2-Clause
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]


class RP1USBXHCILifecycleTests(unittest.TestCase):
    def test_bounded_halt_reset_and_target_compile(self):
        with tempfile.TemporaryDirectory(prefix="rp1-xhci-lifecycle-") as directory:
            work = Path(directory)
            executable = work / "host"
            sources = [
                Path(__file__).with_name("rp1_usb_xhci_lifecycle_host.c"),
                ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.c",
                ROOT / "loader/rpi5/rp1_usb_xhci_caps.c",
            ]
            compiled = subprocess.run([
                "xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra",
                "-Werror", "-fsanitize=address,undefined",
                "-I", str(ROOT / "loader/rpi5"), *map(str, sources),
                "-o", str(executable),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([executable], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("RP1_XHCI_LIFECYCLE_PASS", result.stdout)
            target = work / "lifecycle.o"
            freestanding = subprocess.run([
                "xcrun", "clang", "--target=aarch64-none-elf", "-mcpu=cortex-a76",
                "-mstrict-align", "-mgeneral-regs-only", "-ffreestanding",
                "-fno-builtin", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "loader/rpi5"), "-c",
                str(ROOT / "loader/rpi5/rp1_usb_xhci_lifecycle.c"),
                "-o", str(target),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(freestanding.returncode, 0, freestanding.stderr)
            self.assertTrue(target.is_file())


if __name__ == "__main__":
    unittest.main()
