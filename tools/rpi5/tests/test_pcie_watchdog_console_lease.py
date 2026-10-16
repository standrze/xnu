# SPDX-License-Identifier: BSD-2-Clause
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class PCIeWatchdogConsoleLeaseTests(unittest.TestCase):
    def test_host_policy(self):
        with tempfile.TemporaryDirectory(prefix="pcie-console-watchdog-") as td:
            binary = Path(td) / "watchdog-console"
            subprocess.run([
                "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "loader/rpi5"),
                str(ROOT / "tools/rpi5/tests/pcie_watchdog_console_lease_host.c"),
                str(ROOT / "loader/rpi5/pcie_watchdog_console_lease.c"),
                "-o", str(binary),
            ], check=True)
            output = subprocess.check_output([binary], text=True)
            self.assertIn("PCIE_WATCHDOG_CONSOLE_LEASE_PASS", output)

    def test_policy_has_no_write_surface(self):
        header = (ROOT / "loader/rpi5/pcie_watchdog_console_lease.h").read_text()
        source = (ROOT / "loader/rpi5/pcie_watchdog_console_lease.c").read_text()
        self.assertNotIn("write_countdown", header)
        self.assertNotIn("write_countdown", source)
        self.assertNotIn("0x5a000000", source)
        self.assertIn("terminal_active", header)


if __name__ == "__main__":
    unittest.main()
