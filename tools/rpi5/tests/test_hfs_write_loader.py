# SPDX-License-Identifier: BSD-2-Clause
"""Loader profile rejection and real preprocessing, not board boot proof."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]


class HFSWriteLoaderTests(unittest.TestCase):
    def test_write_profile_rejects_missing_storage_and_readonly_combinations(self):
        for flags in ([], ['--gate4-storage', '--gate4-sd-readonly'],
                      ['--gate4-storage', '--gate4-hfs-readonly']):
            result = subprocess.run([sys.executable, str(ROOT / 'tools/rpi5/build_probe.py'),
                                     '--load-address', '0x9000000', '--gate4-hfs-write-trial', *flags],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('requires --gate4-storage and excludes read-only flags', result.stderr)

    def test_actual_preprocessor_keeps_write_boot_arguments_and_markers_exclusive(self):
        base = ['xcrun', 'clang', '--target=aarch64-none-elf', '-E', '-P',
                '-I' + str(ROOT / 'loader/rpi5/freestanding'), '-DRPI5_SERIAL_TERMINAL=1',
                '-DRPI5_GATE4_STORAGE=1']
        for write, read in ((0, 0), (0, 1), (1, 0), (1, 1)):
            result = subprocess.run([*base, '-DRPI5_GATE4_HFS_WRITE_TRIAL=' + str(write),
                                     '-DRPI5_GATE4_SD_READONLY=' + str(read),
                                     '-DRPI5_GATE4_HFS_READONLY=' + str(read),
                                     str(ROOT / 'loader/rpi5/probe_main.c')], capture_output=True, text=True)
            if write and read:
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Write trial requires distinct', result.stderr)
                continue
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(' bcm2712_sd_write_trial=1' in result.stdout, bool(write))
            self.assertEqual(' bcm2712_sd_readonly=1' in result.stdout, bool(read))
            self.assertEqual('RPI5XNU:BL33:HFS_WRITE_TRIAL' in result.stdout, bool(write))
            self.assertEqual('RPI5XNU:BL33:HFS_READONLY_TRIAL' in result.stdout, bool(read))


if __name__ == '__main__':
    unittest.main()
