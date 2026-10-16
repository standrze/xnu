# SPDX-License-Identifier: BSD-2-Clause
"""Keep the experimental Pi platform match scoped to BCM2712 DEVELOPMENT."""

from pathlib import Path
import plistlib
import re
import subprocess
import tempfile
import unittest
from tools.rpi5.kernel_config_syntax import build_parser


ROOT = Path(__file__).resolve().parents[3]


class PlatformPersonalityTests(unittest.TestCase):
    def test_storage_config_uses_actual_kernel_grammar_and_lexer(self):
        source = '''
#include <cstdio>
#include <iokit/KernelConfigTables.cpp>
int main() { std::fputs(gIOKernelConfigTables, stdout); }
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, output = work / 'table.cpp', work / 'table'
            program.write_text(source)
            parser = build_parser(work)
            for write in (0, 1):
                subprocess.run(['xcrun', 'clang++', '-std=c++17', '-I', str(ROOT),
                            '-DARM64_BOARD_CONFIG_BCM2712=1', '-DDEVELOPMENT=1',
                            '-DRPI5_STORAGE_PROVIDER=1', '-DRPI5_STORAGE_WRITE_PROVIDER=' + str(write),
                            str(program), '-o', str(output)], check=True)
                table = subprocess.check_output([str(output)])
                result = subprocess.run([str(parser)], input=table, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(b"'IOClass'=BCM2712SDWriteStorage;" in table, bool(write))
                self.assertEqual(b"'IOClass'=BCM2712SDStorage;" in table, not write)
            # Reproduce the actual first-boot failure: underscores terminate an
            # unquoted token in this lexer. The former substring test missed it.
            bad = table.replace(b"'FDisk_partition_scheme'", b'FDisk_partition_scheme')
            self.assertNotEqual(bad, table)
            result = subprocess.run([str(parser)], input=bad, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn(b'OSUnserialize: syntax error', result.stderr)

    def test_storage_matching_is_scoped_and_retains_pinned_partition_data(self):
        # Host-preprocessed table checks, not an OSUnserialize/IOKit runtime test.
        source = '''
#include <cstdio>
#include <iokit/KernelConfigTables.cpp>
int main() { std::fputs(gIOKernelConfigTables, stdout); }
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program, output = work / "storage.cpp", work / "storage"
            program.write_text(source)
            for pi, development, storage, write in ((1, 1, 1, 0), (1, 1, 1, 1), (1, 1, 0, 1),
                                                     (1, 0, 1, 1), (0, 1, 1, 1)):
                flags = ["-DDEVELOPMENT=" + str(development), "-DRPI5_STORAGE_PROVIDER=" + str(storage),
                         "-DRPI5_STORAGE_WRITE_PROVIDER=" + str(write)]
                if pi:
                    flags.append("-DARM64_BOARD_CONFIG_BCM2712=1")
                subprocess.run(["xcrun", "clang++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                                "-I", str(ROOT), *flags, str(program), "-o", str(output)], check=True)
                table = subprocess.check_output([str(output)], text=True)
                enabled = bool(pi and development and storage)
                self.assertEqual('BCM2712SDStorage' in table, bool(enabled and not write))
                self.assertEqual('BCM2712SDWriteStorage' in table, bool(enabled and write))
                for name in ("IOBlockStorageDriver", "IOMediaBSDClient", "IOFDiskPartitionScheme",
                             "com_apple_filesystems_hfs", "com_apple_filesystems_hfs_encodings"):
                    self.assertEqual(name in table, enabled)
                if not enabled:
                    continue
                self.assertIn("'IONameMatch'=sdio1", table)
                self.assertIn("'IOResourceMatch'=IOBSD", table)
                self.assertIn("'IOPropertyMatch'={ Whole=.true.; }", table)
                self.assertIn("'IOResourceMatch'=(IOBSD, 'RPI5HFSEncodingsReady')", table)
                # Text order is not a dependency: the resource must be present
                # in the filesystem match, not only the converter personality.
                hfs = table[table.index("'IOClass'='com_apple_filesystems_hfs';"):]
                self.assertIn("'IOProviderClass'=IOResources", hfs)
                self.assertIn("'IOResourceMatch'=(IOBSD, 'RPI5HFSEncodingsReady')", hfs)
                plist = ROOT / "build/rpi5/gate4-sources/IOStorageFamily/IOStorageFamily-IOStorageFamily-337.100.1/Info.plist"
                if plist.exists():
                    pinned = plistlib.loads(plist.read_bytes())["IOKitPersonalities"]
                    actual = dict(re.findall(r"'(0x[0-9A-F]{2})'='([A-Za-z0-9_]+)';", table))
                    self.assertEqual(actual, pinned["IOFDiskPartitionScheme"]["Content Table"])

    def test_pi_personality_precedes_fallback_only_on_pi_development(self):
        source = '''
#include <cstdio>
#include <iokit/KernelConfigTables.cpp>
int main() { std::fputs(gIOKernelConfigTables, stdout); }
'''
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            program = work / "personality.cpp"
            output = work / "personality"
            program.write_text(source)
            for flags, expected in (
                (["-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=1"], True),
                (["-DARM64_BOARD_CONFIG_BCM2712=1", "-DDEVELOPMENT=0"], False),
                (["-DDEVELOPMENT=1"], False),
            ):
                subprocess.run(["xcrun", "clang++", "-std=c++17", "-Wall",
                                "-Wextra", "-Werror", "-I", str(ROOT), *flags,
                                str(program), "-o", str(output)], check=True)
                table = subprocess.check_output([str(output)], text=True)
                self.assertEqual("BCM2712PlatformExpert" in table, expected)
                self.assertIn("IOPanicPlatform", table)
                if expected:
                    self.assertLess(table.index("BCM2712PlatformExpert"),
                                    table.index("IOPanicPlatform"))
                    self.assertIn("'IONameMatch'     = 'device-tree'", table)
                    self.assertIn("'IOProbeScore'    = 1000:32", table)


if __name__ == "__main__":
    unittest.main()
