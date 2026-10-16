# SPDX-License-Identifier: BSD-2-Clause
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5.tests.test_pcie_fdt import _cells, _encode_fdt, _synthetic_tree


ROOT = Path(__file__).resolve().parents[3]


class RP1USBDeviceHandoffTests(unittest.TestCase):
    def test_exact_usb0_window_and_atomic_rejections(self):
        tree = _synthetic_tree()
        bad = copy.deepcopy(tree)
        bad["children"][1]["children"][0]["properties"]["ranges"] = _cells(
            0x02000000, 0, 0, 0x20, 0, 0, 0xfffffffc,
            0x43000000, 4, 0, 0x1c, 0, 3, 0)
        with tempfile.TemporaryDirectory(prefix="rp1-usb-device-handoff-") as directory:
            work = Path(directory)
            executable = work / "host"
            names = (
                "rp1_usb_device_handoff", "rp1_device_handoff",
                "pcie_device_handoff", "pcie_fdt", "fdt", "fdt_reg",
                "memory_type", "board_tree", "cpu_tree", "serial_tree", "apple_dt",
            )
            compiled = subprocess.run([
                "xcrun", "clang", "-std=c11", "-O2", "-Wall", "-Wextra",
                "-Werror", "-fsanitize=address,undefined",
                "-I", str(ROOT / "loader/rpi5"),
                str(Path(__file__).with_name("rp1_usb_device_handoff_host.c")),
                *[str(ROOT / "loader/rpi5" / (name + ".c")) for name in names],
                "-o", str(executable),
            ], capture_output=True, text=True, timeout=60)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            cases = (
                (_encode_fdt(tree), "accept", "RP1_USB_DEVICE_PASS EXACT_USB0_PAGES=64"),
                (_encode_fdt(bad), "reject", "RP1_USB_DEVICE_REJECT"),
                (b"not fdt", "reject", "RP1_USB_DEVICE_REJECT"),
            )
            for index, (data, mode, marker) in enumerate(cases):
                fixture = work / (str(index) + ".dtb")
                fixture.write_bytes(data)
                result = subprocess.run([executable, fixture, mode],
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(marker, result.stdout)


if __name__ == "__main__":
    unittest.main()
