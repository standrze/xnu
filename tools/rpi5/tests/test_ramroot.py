# SPDX-License-Identifier: BSD-2-Clause
"""Shared kernel-parser and host-packager checks; not a filesystem boot test."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from tools.rpi5.ramroot import build, inspect, inspect_init, PAGE
from tools.rpi5.tests.test_prepare_pid1 import fixture

ROOT = Path(__file__).resolve().parents[3]


class RamrootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.exe = Path(cls.tmp.name) / "parser"
        source = Path(cls.tmp.name) / "parser.c"
        source.write_text('''
#include <stdio.h>
#include <stdlib.h>
#include <miscfs/mockfs/rpi5_ramroot_format.h>
int main(int argc, char **argv) {
    uint8_t page[RPI5_RFS_PAGE]; uint32_t count = 123;
    if (argc != 2 || fread(page, 1, sizeof(page), stdin) != sizeof(page)) return 2;
    int error = rpi5_rfs_validate(page, strtoull(argv[1], NULL, 10), &count);
    if (error && count != 123) return 3;
    return error ? 1 : 0;
}
''')
        subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", "-I", str(ROOT / "bsd"),
                        str(source), "-o", str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def native(self, image):
        result = subprocess.run([str(self.exe), str(len(image))], input=image[-PAGE:],
                                capture_output=True)
        self.assertIn(result.returncode, (0, 1), result.stderr.decode())
        self.assertEqual(result.stderr, b"")
        return result.returncode == 0

    def image(self):
        return build({"/sbin/launchd": (bytes(fixture()), 0o555),
                      "/bin/child": (bytes(fixture()), 0o555),
                      "/etc/motd": (b"RPI5 RAM ROOT\n", 0o444),
                      "/etc/empty": (b"", 0o444),
                      "/etc/boundary": (b"x" * (PAGE - 4) + b"BOUNDARY", 0o444)})

    def test_native_parser_and_roundtrip(self):
        image, report = self.image()
        self.assertTrue(self.native(image))
        self.assertEqual(inspect(image), report)
        self.assertEqual(inspect_init(image), report)
        self.assertEqual(image[:512], fixture())
        self.assertNotEqual(next(e["offset"] for e in report["entries"] if e["path"] == "/bin/child"), 0)
        self.assertEqual(inspect_init(bytes(fixture()))["entry_pc"], 0x100000190)

    def test_malformed_metadata_native_and_host(self):
        image, report = self.image()
        entries = report["entries"]
        index = {entry["path"]: i for i, entry in enumerate(entries)}
        def record(path, field):
            return 32 + index[path] * 128 + field
        changes = [(8, "I", 2), (12, "I", 33), (12, "I", 0), (16, "Q", 1),
                   (24, "Q", 1), (32, "I", 1),
                   (record("/bin", 0), "I", index["/bin"]),
                   (record("/bin/child", 8), "Q", 0),
                   (record("/bin/child", 8), "Q", 1),
                   (record("/bin/child", 16), "Q", (1 << 64) - 1),
                   (record("/bin/child", 24), "I", 0o777),
                   (record("/bin/child", 28), "I", 1),
                   (record("/bin/child", 96), "I", 1),
                   (record("/etc", 16), "Q", 1),
                   (record("/sbin/launchd", 24), "I", 0o444),
                   (record("/etc/motd", 0), "I", index["/dev"]),
                   (PAGE - 4, "I", 1)]
        for offset, fmt, value in changes:
            bad = bytearray(image)
            struct.pack_into("<" + fmt, bad, len(image) - PAGE + offset, value)
            with self.subTest(offset=offset, value=value):
                self.assertFalse(self.native(bad))
                with self.assertRaises(ValueError):
                    inspect(bytes(bad))

    def test_path_and_bounds_rejection(self):
        base = {"/sbin/launchd": (bytes(fixture()), 0o555)}
        for name in ("relative", "/dev/x", "/dev", "/a/../x", "/a//x", "/a/./x",
                     "/sbin", "/" + "a" * 64):
            with self.subTest(name=name), self.assertRaises(ValueError):
                build(base | {name: (b"x", 0o444)})
        with self.assertRaises(ValueError):
            build(base | {f"/file{i}": (b"x", 0o444) for i in range(32)})


if __name__ == "__main__":
    unittest.main()
