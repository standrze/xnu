# SPDX-License-Identifier: BSD-2-Clause
"""Native Darwin data/cleanup tests and A76 link; never Pi/NIC acceptance."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.rpi5 import prepare_socketprobe_root as preparation
from tools.rpi5 import check_socketprobe_package as package
from tools.rpi5.prepare_zsh_trial_root import files_from
from tools.rpi5.ramroot import build
from tools.rpi5.tests.test_prepare_pid1 import fixture

ROOT = Path(__file__).resolve().parents[3]


@unittest.skipUnless(sys.platform == 'darwin', 'Native Darwin socket ABI required')
class SocketprobeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.program = Path(cls.temporary.name)/'socketprobe-native'
        subprocess.run(['xcrun', 'clang', '-std=c11', '-Wall', '-Wextra', '-Werror',
                        '-DRPI5_SOCKETPROBE_HOST_TEST',
                        str(ROOT/'tools/rpi5/user/socketprobe.c'),
                        str(ROOT/'tools/rpi5/tests/socketprobe_native.c'),
                        '-o', str(cls.program)], check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def native(self, mode, scenario='none', status=0, fail_at=None):
        args = [str(self.program), mode, scenario]
        if fail_at is not None:
            args.append(str(fail_at))
        result = subprocess.run(args, capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, status, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'NATIVE:CALLS=\d+:LEAKS=0:VIOLATIONS=0\n$')
        return result.stdout

    def test_actual_host_unix_udp_tcp_payload_and_halfclose(self):
        for mode, operations in (('unix', 26), ('inet', 62)):
            with self.subTest(mode=mode):
                output = self.native(mode)
                self.assertEqual(output.count('STREAM_PAYLOAD_MATCH=32\n'), 3)
                self.assertIn('STREAM_EOF=0\n', output)
                self.assertIn(f'OPERATIONS={operations}\n', output)
                self.assertIn('SOCKETPROBE:PASS\n', output)
                self.assertIn('END:NOT_ETHERNET_OR_SSH_PROOF\n', output)
                if mode == 'inet':
                    self.assertEqual(output.count('UDP_PAYLOAD_AND_PEER_MATCH=32\n'), 2)
                    self.assertIn('UDP_PASS\n', output)
                    self.assertIn('TCP_PASS\n', output)

    def test_partial_io_is_finite_and_does_not_drop_or_duplicate_bytes(self):
        for mode, operations in (('unix', 206), ('inet', 242)):
            with self.subTest(mode=mode):
                output = self.native(mode, 'partial-two')
                self.assertIn(f'OPERATIONS={operations}\n', output)
                self.assertNotIn('CALL_BOUND', output)
                self.assertEqual(output.count('STREAM_PAYLOAD_MATCH=32\n'), 3)
                output = self.native(mode, 'partial-one', 1)
                self.assertNotIn('SOCKETPROBE:PASS\n', output)
                self.assertLess(int(re.search(r'OPERATIONS=(\d+)', output)[1]), 256)

    def test_every_native_operation_failure_closes_each_owned_descriptor_once(self):
        # Includes all partial-I/O poll/read/write positions, connect/accept,
        # shutdown and uncertain-close outcomes, without syscall retries.
        for mode, count in (('unix', 206), ('inet', 242)):
            for index in range(1, count + 1):
                with self.subTest(mode=mode, fail_at=index):
                    output = self.native(mode, 'partial-two', 1, index)
                    self.assertIn('SOCKETPROBE:FAIL\n', output)
                    self.assertNotIn('SOCKETPROBE:PASS\n', output)

    def test_invalid_returns_data_guards_and_poll_refusals_fail_closed(self):
        cases = {
            'unix': ('payload', 'read-overrun', 'bad-eof', 'nonblock', 'pair-alias',
                     'pair-stdio', 'poll-timeout', 'poll-error'),
            'inet': ('payload', 'read-overrun', 'bad-eof', 'nonblock', 'socket-alias',
                     'socket-stdio', 'accept-alias', 'udp-payload', 'udp-peer',
                     'udp-length', 'udp-overrun', 'length-overrun', 'address',
                     'name-length', 'so-error', 'so-error-length', 'short-udp',
                     'poll-timeout', 'poll-error'),
        }
        for mode, scenarios in cases.items():
            for scenario in scenarios:
                with self.subTest(mode=mode, scenario=scenario):
                    output = self.native(mode, scenario, 1)
                    self.assertNotIn('SOCKETPROBE:PASS\n', output)
        output = self.native('not-a-mode', status=2)
        self.assertEqual(output, 'NATIVE:CALLS=0:LEAKS=0:VIOLATIONS=0\n')

    def test_root_preserves_files_and_darwin_local_helper_placement(self):
        exe = bytes(fixture())
        files = {name: (exe, 0o555) for name in (
            '/sbin/launchd', '/bin/sh', '/bin/zsh', '/sbin/ifconfig', '/sbin/route')}
        files['/etc/zsh-smoke.zsh'] = (b'keep unchanged\n', 0o444)
        baseline = build(files)[0]
        pin = hashlib.sha256(baseline).hexdigest()
        image, report = preparation.prepare(baseline, exe, pin)
        actual = files_from(image)
        self.assertEqual(actual.pop(preparation.INSTALL_PATH), (exe, 0o555))
        self.assertEqual(actual, files)
        self.assertFalse(report['pi_executed'])
        self.assertFalse(report['socket_semantics_proven'])
        for data, binary, digest in ((baseline, exe, '0'*64),
                                     (baseline, b'invalid', pin)):
            with self.assertRaises(ValueError): preparation.prepare(data, binary, digest)
        for collision in (preparation.INSTALL_PATH, '/usr/local'):
            data = build({**files, collision: (b'collision', 0o444)})[0]
            with self.subTest(path=collision), self.assertRaises(ValueError):
                preparation.prepare(data, exe, hashlib.sha256(data).hexdigest())

    def test_dependency_parser_retains_escaped_spaces(self):
        self.assertEqual(preparation.dependencies('thing.o: /a\\ b.h \\\n /c.h\n'),
                         {Path('/a b.h'), Path('/c.h')})
        with self.assertRaises(ValueError): preparation.dependencies('not dependencies')

    def test_real_a76_static_link_pins_all_preserved_bytes_and_sysent(self):
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)/'root'
            command = [sys.executable, str(ROOT/'tools/rpi5/prepare_socketprobe_root.py'),
                       '--output-dir', str(out)]
            subprocess.run(command, check=True, capture_output=True, timeout=30)
            report = json.loads((out/'manifest.json').read_text())
            image = (out/'ramdisk.bin').read_bytes()
            original = files_from(preparation.ACCEPTED_ROOT.read_bytes())
            actual = files_from(image)
            actual.pop(preparation.INSTALL_PATH)
            self.assertEqual(actual, original)
            self.assertEqual(report['output_nodes'], 32)
            self.assertEqual(hashlib.sha256(image).hexdigest(), report['output_sha256'])
            self.assertEqual(subprocess.check_output(['xcrun', 'nm', '-u', str(out/'socketprobe')],
                                                    text=True).strip(), '')
            self.assertEqual(len(report['linked_sysent']['calls']), 17)
            self.assertGreater(len(report['sdk_headers_sha256']), 10)
            self.assertFalse(report['kernel_syscall_hang_contained'])
            for path, pin in report['sdk_headers_sha256'].items():
                self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), pin)
            for field in ('pi_executed', 'socket_semantics_proven', 'nic_ready', 'ssh_proven',
                          'networking_proven', 'durability', 'sd_actions', 'serial_actions', 'reboots'):
                self.assertFalse(report[field], field)
            again = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual((out/'ramdisk.bin').read_bytes(), image)

    def test_wrong_kernel_and_handler_pins_reject(self):
        with patch.object(preparation.metadata, 'KERNEL_SHA', '0'*64):
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                preparation.kernel_calls()
        with patch.dict(preparation.CALLS, {230: '_nosys'}):
            with self.assertRaisesRegex(ValueError, 'Unexpected linked'):
                preparation.kernel_calls()

    def test_prepared_boot_package_preserves_recovery_and_disclaims_hardware(self):
        candidate = ROOT/'build/rpi5/bl33-probe-tt7iq4m9'
        report = package.inspect(candidate)
        self.assertTrue(report['preflight_pass'])
        self.assertEqual(len(report['checks']), 34)
        self.assertEqual(report['image_sha256'],
                         'ccb961bc36be8befad08b5a1b1dbc0d0bff4dc5a2fa25e27f341336770105d04')
        for field in ('pi_executed', 'socket_semantics_proven', 'nic_ready', 'ssh_proven',
                      'networking', 'durability', 'sd_actions', 'serial_actions', 'reboots'):
            self.assertFalse(report[field], field)
        with self.assertRaises(ValueError): package.inspect(package.ACCEPTED)

    def test_package_rejects_individual_changed_pins(self):
        for name in ('INIT_SHA', 'PROBE_SHA', 'ROOT_RECEIPT_SHA'):
            with self.subTest(pin=name), patch.object(package, name, '0'*64):
                with self.assertRaises(ValueError):
                    package.inspect(ROOT/'build/rpi5/bl33-probe-tt7iq4m9')


if __name__ == '__main__':
    unittest.main()
