# SPDX-License-Identifier: BSD-2-Clause
"""Real static userland builds; no execution, device, mount or persistence proof."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5.ramroot import inspect

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / 'tools/rpi5/build_userland.py'


class HFSWriteUserlandTests(unittest.TestCase):
    def test_conflicting_profiles_fail_before_output_creation(self):
        for flags in (['--sd-read-trial'], ['--hfs-read-trial'],
                      ['--sd-read-trial', '--hfs-read-trial']):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as temporary:
                out = Path(temporary) / 'not-created'
                result = subprocess.run([sys.executable, str(BUILDER), '--output-dir', str(out),
                                         '--hfs-write-trial', *flags], capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('cannot be combined', result.stderr)
                self.assertFalse(out.exists())

    def test_actual_default_readonly_and_write_archives_are_disjoint_profiles(self):
        if not (ROOT / 'build/rpi5/gate4-reference/hfs.tar.gz').exists():
            self.skipTest('Pinned HFS archive is not prepared')
        with tempfile.TemporaryDirectory() as temporary:
            for profile, flags in (('default', []), ('read', ['--sd-read-trial', '--hfs-read-trial']),
                                   ('write', ['--hfs-write-trial'])):
                with self.subTest(profile=profile):
                    out = Path(temporary) / profile
                    subprocess.run([sys.executable, str(BUILDER), '--output-dir', str(out), *flags],
                                   check=True, capture_output=True, timeout=60)
                    manifest = json.loads((out / 'manifest.json').read_text())
                    image = (out / 'ramdisk.bin').read_bytes()
                    entries = {e['path']: e for e in inspect(image)['entries']}
                    symbols = set(subprocess.check_output(['xcrun', 'nm', '-jU', str(out / 'userland')],
                                                         text=True).splitlines())
                    self.assertEqual(manifest['hfs_write_trial'], profile == 'write')
                    for name in ('hfsrw', 'hfswrite'):
                        enabled = profile == 'write'
                        self.assertEqual('/bin/' + name in entries, enabled)
                        self.assertEqual('_' + name + '_main' in symbols, enabled)
                        if enabled:
                            self.assertEqual(entries['/bin/' + name]['mode'], 0o555)
                    for name in ('sdread', 'hfsro'):
                        self.assertEqual('/bin/' + name in entries, profile == 'read')
                        self.assertEqual('_' + name + '_main' in symbols, profile == 'read')
                    self.assertEqual(b'RPI5XNU:HFSWRITE:BATCH_FSYNCED' in image, profile == 'write')
                    self.assertEqual(b'RPI5XNU:HFSRW:MOUNTED' in image, profile == 'write')
                    self.assertEqual('/mnt/hfs/.anchor' in entries, profile != 'default')
                    for command in manifest['commands'][:-1]:
                        self.assertIn('-DRPI5_HFS_WRITE_TRIAL=' + str(int(profile == 'write')), command)


if __name__ == '__main__':
    unittest.main()
