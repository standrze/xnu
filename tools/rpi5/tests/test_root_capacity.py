# SPDX-License-Identifier: BSD-2-Clause
"""Exercise the actual expanded C parser and preserved host packer."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.rpi5 import root_capacity_profile as profile
from tools.rpi5 import ramroot as original
from tools.rpi5.tests.test_prepare_pid1 import fixture


class CapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        header = cls.directory / 'miscfs/mockfs/rpi5_ramroot_format.h'
        header.parent.mkdir(parents=True)
        header.write_bytes(profile.kernel_header())
        cls.binary = cls.directory / 'parser'
        source = Path(__file__).with_name('root_capacity_parser.c')
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I', str(cls.directory),
                        str(source), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native(self, image):
        result = subprocess.run([str(self.binary), str(len(image))], input=image[-original.PAGE:], capture_output=True)
        self.assertEqual(result.stderr, b'')
        self.assertIn(result.returncode, (0, 1))
        return result.returncode == 0

    def files(self, count):
        # /, /dev, /sbin and /sbin/launchd are four nodes.
        return {'/sbin/launchd': (bytes(fixture()), 0o555),
                **{f'/f{i}': (bytes([i % 256]), 0o444) for i in range(count - 4)}}

    def test_capacity_boundaries_and_preserved_profile(self):
        for count in (4, 32, 33, 95, 96):
            with self.subTest(count=count):
                image, report = profile.build(self.files(count))
                self.assertEqual(len(report['entries']), count)
                self.assertEqual(profile.inspect(image), report)
                self.assertTrue(self.native(image))
                if count <= 32:
                    self.assertEqual(original.build(self.files(count)), (image, report))
                else:
                    with self.assertRaises(ValueError):
                        original.inspect(image)
        self.assertEqual(original.MAX_NODES, 32)
        with self.assertRaises(ValueError):
            profile.build(self.files(97))

    def test_full_page_count_corruption_and_duplicate_rejection(self):
        image, report = profile.build(self.files(96))
        for count in (0, 3, 97, 127, 128, 0xffffffff):
            damaged = bytearray(image)
            struct.pack_into('<I', damaged, len(image) - original.PAGE + 12, count)
            self.assertFalse(self.native(damaged))
            with self.assertRaises(ValueError):
                profile.inspect(damaged)
        for offset in (32 + 95 * 128 + 96, 32 + 96 * 128, original.PAGE - 1):
            damaged = bytearray(image)
            damaged[-original.PAGE + offset] = 1
            self.assertFalse(self.native(damaged))
            with self.assertRaises(ValueError):
                profile.inspect(damaged)
        self.assertEqual(profile.files_from(image), self.files(96))


if __name__ == '__main__':
    unittest.main()
