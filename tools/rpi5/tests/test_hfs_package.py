# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic HFS package identity failures; no staging or hardware evidence."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_hfs_read_package as checker


class HFSPackageTests(unittest.TestCase):
    def check(self, fault=''):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            package = work / 'package'; package.mkdir()
            init = work / 'ramdisk.bin'; init.write_bytes(b'RPI5XNU:HFSRO:MOUNTED')
            (work / 'manifest.json').write_text(json.dumps({'hfs_read_trial': fault != 'userland-flag'}))
            image = checker.HFS_LOADER + b' bcm2712_hfs=1 bcm2712_sd_readonly=1\0'
            if fault == 'loader-marker': image = image.replace(checker.HFS_LOADER, b'')
            if fault == 'boot-argument': image = image.replace(b'bcm2712_hfs=1', b'bcm2712_hfs=0')
            (package / 'probe.bin').write_bytes(image)
            command = ['clang', 'probe_main.c', '-DRPI5_GATE4_HFS_READONLY=1']
            if fault == 'compile-flag': command.pop()
            (package / 'manifest.json').write_text(json.dumps({
                'gate4_hfs_readonly': fault != 'manifest-flag', 'commands': [command]}))
            provider = work / 'provider.json'
            provider.write_text(json.dumps({'adapted': True, 'service_patch_sha256':
                checker.sha256(Path(checker.__file__).with_name('patches') / 'hfs-builtin-service.patch')
                if fault != 'service-patch' else '0' * 64}))
            build = work / 'build.json'
            build.write_text(json.dumps({'storage_provider': {'screen_manifest': str(provider),
                'screen_manifest_sha256': checker.sha256(provider) if fault != 'screen-hash' else '0' * 64}}))
            entries = [{'path': '/bin/hfsro', 'type': 'file', 'mode': 0o555},
                       {'path': '/mnt/hfs', 'type': 'directory', 'mode': 0o555},
                       {'path': '/mnt/hfs/.anchor', 'type': 'file', 'mode': 0o444, 'size': 0}]
            if fault == 'missing-utility': entries.pop(0)
            if fault == 'utility-mode': entries[0]['mode'] = 0o444
            if fault == 'mountpoint': entries[1]['type'] = 'file'
            if fault == 'anchor': entries[-1]['type'] = 'directory'
            names = ('com_apple_filesystems_hfs', 'com_apple_filesystems_hfs_encodings')
            symbols = '\n'.join('__ZN' + str(len(name)) + name + '10gMetaClassE' for name in names)
            if fault == 'class': symbols = ''
            syntax = {'syntax_pass': fault != 'syntax', 'required_fragments_present':
                      {key: fault != 'ordering' for key in checker.REQUIRED_HFS_CONFIG}}
            if fault == 'missing-fragments': syntax['required_fragments_present'] = {}
            base = {'checks': {'sd_checks': fault != 'sd'}, 'preflight_pass': True}
            with mock.patch.object(checker, 'sd_inspect', return_value=copy.deepcopy(base)), \
                 mock.patch.object(checker, 'ramroot_inspect', return_value={'entries': entries}), \
                 mock.patch.object(checker, 'inspect_kernel_config', return_value=syntax), \
                 mock.patch.object(checker.subprocess, 'check_output', return_value=symbols):
                return checker.inspect(package, work / 'kernel', init, work / 'gate3', work / 'shell', build)

    def test_complete_fixture_passes_only_host_identity_checks(self):
        report = self.check()
        self.assertTrue(report['preflight_pass'])
        self.assertTrue(report['hfs_readonly_trial'])
        self.assertIn('not HFS registration', report['scope'])

    def test_missing_or_changed_evidence_rejects_before_staging(self):
        for fault in ('manifest-flag', 'compile-flag', 'loader-marker', 'boot-argument',
                      'class', 'syntax', 'ordering', 'missing-fragments', 'service-patch',
                      'screen-hash', 'userland-flag', 'missing-utility', 'utility-mode',
                      'mountpoint', 'anchor', 'sd'):
            with self.subTest(fault=fault):
                self.assertFalse(self.check(fault)['preflight_pass'])

    def test_userland_hfs_flag_requires_sd_trial_before_creating_outputs(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'not-created'
            result = subprocess.run([sys.executable, str(Path(checker.__file__).with_name('build_userland.py')),
                                     '--output-dir', str(output), '--hfs-read-trial'],
                                    capture_output=True, text=True)
            self.assertFalse(output.exists())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--hfs-read-trial requires --sd-read-trial', result.stderr)
