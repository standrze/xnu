# SPDX-License-Identifier: BSD-2-Clause
import struct
import subprocess
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_probe import inspect


def fixture():
    data = bytearray(512)
    data[:7] = b"\x7fELF\x02\x01\x01"
    struct.pack_into("<HHIQQQIHHHHHH", data, 16, 2, 183, 1, 0x200000, 64, 128, 0, 64, 56, 1, 64, 1, 0)
    struct.pack_into("<IIQQQQQQ", data, 64, 1, 5, 256, 0x200000, 0x200000, 4, 4, 1)
    struct.pack_into("<IIQQQQIIQQ", data, 128, 0, 2, 0, 0, 288, 24, 0, 0, 8, 24)
    data[256:260] = b"test"
    return data


class ProbeBuildTests(unittest.TestCase):
    def test_hfs_readonly_requires_separate_sd_recovery_image(self):
        script = Path(__file__).resolve().parents[1] / "build_probe.py"
        result = subprocess.run([sys.executable, str(script), "--load-address", "0x9000000",
                                 "--gate4-hfs-readonly"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--gate4-hfs-readonly requires --gate4-sd-readonly", result.stderr)

    def test_sd_readonly_requires_explicit_storage_recovery_image(self):
        script = Path(__file__).resolve().parents[1] / "build_probe.py"
        base = [sys.executable, str(script), "--load-address", "0x9000000",
                "--gate4-sd-readonly"]
        result = subprocess.run(base, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--gate4-sd-readonly requires --gate4-storage", result.stderr)
        result = subprocess.run([*base, "--gate4-storage"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--gate4-storage requires", result.stderr)

    def test_gate4_binding_snapshot_requires_serial_recovery_image(self):
        script = Path(__file__).resolve().parents[1] / "build_probe.py"
        result = subprocess.run([sys.executable, str(script), "--load-address", "0x9000000",
                                 "--gate4-storage"], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--gate4-storage requires", result.stderr)

    def test_serial_terminal_requires_separate_smp_transfer_image(self):
        script = Path(__file__).resolve().parents[1] / "build_probe.py"
        base = [sys.executable, str(script), "--load-address", "0x9000000",
                "--kernel", "missing-kernel", "--init", "missing-init", "--transfer"]
        missing_smp = subprocess.run([*base, "--serial-terminal"], capture_output=True, text=True)
        self.assertNotEqual(missing_smp.returncode, 0)
        self.assertIn("--gate3-cpu-on-all", missing_smp.stderr)
        qualification = subprocess.run([*base, "--gate3-cpu-on-all", "--serial-terminal",
                                        "--gate3-qualification-config", "1_34"],
                                       capture_output=True, text=True)
        self.assertNotEqual(qualification.returncode, 0)
        self.assertIn("cannot be combined", qualification.stderr)

    def test_valid(self):
        self.assertFalse(inspect(fixture(), b"test", 0x200000)["board_placement_verified"])

    def test_rejects_bad_artifacts(self):
        for offset, fmt, value in [(16, "<H", 3), (18, "<H", 62), (24, "<Q", 0), (64, "<I", 2), (68, "<I", 7), (104, "<Q", 3), (132, "<I", 4)]:
            with self.subTest(offset=offset):
                data = fixture()
                struct.pack_into(fmt, data, offset, value)
                with self.assertRaises(ValueError):
                    inspect(data, b"test", 0x200000)
        for raw in (b"bad!", b"test!", b"tes"):
            with self.assertRaises(ValueError):
                inspect(fixture(), raw, 0x200000)
        data = fixture()
        struct.pack_into("<Q", data, 160, 48)
        with self.assertRaisesRegex(ValueError, "undefined"):
            inspect(data, b"test", 0x200000)

    def test_truncation(self):
        for length in range(312):
            with self.assertRaises(ValueError):
                inspect(fixture()[:length], b"test", 0x200000)
