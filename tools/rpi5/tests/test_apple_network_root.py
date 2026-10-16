# SPDX-License-Identifier: BSD-2-Clause
"""Original command reuse/preservation checks, not Pi networking evidence."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import prepare_apple_network_root as root
from tools.rpi5.prepare_zsh_trial_root import files_from
from tools.rpi5.ramroot import build
from tools.rpi5.tests.test_prepare_pid1 import fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


class AppleNetworkRootTests(unittest.TestCase):
    def inputs(self):
        binary = bytes(fixture())
        commands = {name: binary for name in ('ifconfig', 'route')}
        pins = {name: sha(binary) for name in commands}
        files = {name: (binary, 0o555) for name in
                 ('/sbin/launchd', '/bin/sh', '/bin/zsh', '/bin/statprobe')}
        files['/etc/zsh-smoke.zsh'] = (b'preserve script\n', 0o444)
        return build(files)[0], commands, pins, files

    def test_additions_preserve_every_recovery_file_and_mode(self):
        baseline, commands, pins, original = self.inputs()
        image, report = root.prepare(baseline, commands, sha(baseline), pins)
        actual = files_from(image)
        self.assertEqual({path: value for path, value in actual.items()
                          if path not in ('/sbin/ifconfig', '/sbin/route')}, original)
        for name, data in commands.items():
            self.assertEqual(actual['/sbin/' + name], (data, 0o555))
            self.assertNotIn('/bin/' + name, actual)
        self.assertEqual(report['command_install_paths'],
                         {'ifconfig': '/sbin/ifconfig', 'route': '/sbin/route'})
        self.assertFalse(report['complete_darwin_layout'])
        self.assertEqual(report['output_sha256'], sha(image))
        for field in ('pi_executed', 'networking_proven', 'isa_and_abi_compatibility_proven',
                      'boot_package_preflight_passed', 'vm_init_or_poweroff_imported',
                      'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(report[field], field)

    def test_wrong_hash_dynamic_binary_and_unexpected_commands_reject(self):
        baseline, commands, pins, _ = self.inputs()
        with self.assertRaises(ValueError): root.prepare(baseline, commands, '0' * 64, pins)
        for name in commands:
            bad_pins = {**pins, name: '0' * 64}
            with self.assertRaises(ValueError): root.prepare(baseline, commands, sha(baseline), bad_pins)
            bad = bytearray(commands[name]); bad[24] |= 4  # MH_DYLDLINK
            binaries = {**commands, name: bytes(bad)}
            with self.assertRaises(ValueError):
                root.prepare(baseline, binaries, sha(baseline), {**pins, name: sha(bad)})
        with self.assertRaises(ValueError):
            root.prepare(baseline, {**commands, 'launchd': commands['route']}, sha(baseline), pins)

    def test_collision_missing_recovery_and_wrong_modes_reject(self):
        _, commands, pins, original = self.inputs()
        for name in ('/sbin/ifconfig', '/sbin/route'):
            image = build({**original, name: (b'keep me', 0o444)})[0]
            with self.assertRaises(ValueError): root.prepare(image, commands, sha(image), pins)
        for name in ('/sbin/launchd', '/bin/sh', '/bin/zsh', '/bin/statprobe'):
            for mode in (None, 0o444):
                files = original.copy()
                if mode is None: del files[name]
                else: files[name] = (files[name][0], mode)
                with self.assertRaises(ValueError):
                    image = build(files)[0]
                    root.prepare(image, commands, sha(image), pins)

    def test_actual_source_receipts_binary_pins_and_original_constructors(self):
        commands, snapshots, provenance = root.load_inputs()
        image, report = root.prepare(root.PI_ROOT.read_bytes(), commands, root.ROOT_PIN,
                                     {name: pins[0] for name, pins in root.PINS.items()})
        self.assertEqual(report['output_nodes'], 27)
        self.assertEqual(provenance['commit'], root.SOURCE_PIN)
        self.assertEqual(provenance['original_ifconfig_constructors']['count'], 9)
        self.assertGreater(len(snapshots), 100)
        prepared = root.ROOT / 'build/rpi5/apple-network-root-darwin-20261012/ramdisk.bin'
        self.assertEqual(image, prepared.read_bytes())
        self.assertEqual(sha(root.PI_ROOT.read_bytes()), root.ROOT_PIN)

    def test_receipt_or_binary_pin_drift_rejects(self):
        for position in (0, 1):
            pins = copy.deepcopy(root.PINS)
            changed = list(pins['ifconfig']); changed[position] = '0' * 64
            pins['ifconfig'] = tuple(changed)
            with patch.object(root, 'PINS', pins), self.assertRaises(ValueError): root.load_inputs()

    def test_cli_prepares_once_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='apple-net-root-test-', dir=root.ROOT / 'build/rpi5') as temporary:
            output = Path(temporary) / 'new'
            command = [sys.executable, str(root.ROOT / 'tools/rpi5/prepare_apple_network_root.py'),
                       '--output-dir', str(output)]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            image = (output / 'ramdisk.bin').read_bytes()
            report = json.loads((output / 'manifest.json').read_text())
            self.assertEqual(report['output_sha256'], sha(image))
            self.assertTrue(report['original_commands_unchanged'])
            for name, audit in report['instruction_inventories'].items():
                self.assertEqual(audit['command'], name)
                self.assertEqual(audit['binary_sha256'], root.PINS[name][0])
                self.assertFalse(audit['pi_executed'])
                self.assertFalse(audit['isa_compatibility_proven'])
                self.assertGreater(audit['trap_count'], 0)
            again = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(image, (output / 'ramdisk.bin').read_bytes())


if __name__ == '__main__':
    unittest.main()
