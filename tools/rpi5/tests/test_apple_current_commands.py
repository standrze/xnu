# SPDX-License-Identifier: BSD-2-Clause
"""Current Apple command logic/providers on native files, plus static Pi audit."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from tools.rpi5 import build_apple_current_commands as builder
from tools.rpi5.prepare_pid1 import inspect as inspect_macho


class CurrentCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ.get('RPI5_CURRENT_COMMANDS', str(
            builder.ROOT / 'build/rpi5/apple-current-commands-qg7qd51g')))
        cls.manifest = json.loads((cls.package / 'manifest.json').read_text())
        builder.verify(cls.manifest['source_inputs_sha256'] |
                       cls.manifest['headers_sha256'] | cls.manifest['generated_sha256'])
        cls.temp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.temp.name).resolve()
        cls.physical = cls.base / 'physical'
        cls.physical.mkdir()
        cls.logical = cls.base / 'logical'
        cls.logical.symlink_to(cls.physical, target_is_directory=True)
        cls.environment = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
                               UBSAN_OPTIONS='halt_on_error=1', LC_ALL='C', TZ='UTC0')
        cls.environment.pop('COMMAND_MODE', None)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def run_native(self, name, arguments, pwd=None, code=0, expected=None):
        env = dict(self.environment)
        env.pop('PWD', None)
        if pwd is not None:
            env['PWD'] = str(pwd)
        program = self.manifest['programs'][name]['native_executable']
        self.assertIsNotNone(program)
        result = subprocess.run([program, *arguments], cwd=self.physical, env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertNotIn('Sanitizer', result.stderr)
        self.assertNotIn('runtime error:', result.stderr)
        if expected is not None:
            self.assertEqual(result.stdout, expected)
        if code == 0:
            self.assertEqual(result.stderr, '')
        return result

    def test_current_pwd_logical_physical_and_option_precedence(self):
        physical = str(self.physical) + '\n'
        logical = str(self.logical) + '\n'
        for args, pwd, result in (
            ([], None, physical), ([], self.logical, logical),
            (['-L'], self.logical, logical), (['-P'], self.logical, physical),
            (['-L', '-P'], self.logical, physical),
            (['-P', '-L'], self.logical, logical),
            ([], '/', physical), ([], 'relative', physical),
            (['--'], self.logical, logical),
        ):
            with self.subTest(arguments=args, pwd=pwd):
                self.run_native('pwd', args, pwd, expected=result)

    def test_current_pwd_failures_are_real_errors(self):
        for args in (['-Q'], ['operand']):
            with self.subTest(arguments=args):
                result = self.run_native('pwd', args, code=1, expected='')
                self.assertIn('usage: pwd [-L | -P]', result.stderr)
        # Preserve Apple's deliberate no-fallback rule for ENAMETOOLONG.
        result = self.run_native('pwd', [], '/' + 'x' * 2048, code=1, expected='')
        self.assertIn('File name too long', result.stderr)

    def test_current_date_readonly_host_behavior_not_target_readiness(self):
        cases = (
            (['-u', '-r', '0', '+%Y-%m-%dT%H:%M:%SZ'], '1970-01-01T00:00:00Z\n'),
            (['-u', '-r', '0', '-v+1d', '+%F'], '1970-01-02\n'),
            (['-u', '-r', '0', '-Iseconds'], '1970-01-01T00:00:00+00:00\n'),
            (['-u', '-j', '-f', '%Y-%m-%d', '2024-02-29', '+%F'], '2024-02-29\n'),
        )
        for args, expected in cases:
            with self.subTest(arguments=args):
                self.run_native('date', args, expected=expected)
        self.assertFalse(self.manifest['programs']['date']['static_link_complete'])
        self.assertIn('_clock_settime', self.manifest['programs']['date']['missing_symbols'])

    @unittest.expectedFailure
    def test_original_date_nanosecond_candidate_is_not_safe_to_ship(self):
        # Preserved original current source: known strftime_ns cursor over-read.
        # A separately derived overlay must fix this; never weaken its gate.
        self.run_native('date', ['-u', '-r', '0', '-Ins'],
                        expected='1970-01-01T00:00:00,000000000+00:00\n')

    def test_pwd_real_complete_static_target_and_actual_provider_map(self):
        record = self.manifest['programs']['pwd']
        self.assertTrue(record['static_link_complete'])
        path = Path(record['static_executable'])
        self.assertEqual(inspect_macho(path.read_bytes()), record['macho_audit'])
        undefined = subprocess.run(['xcrun', 'nm', '-u', str(path)],
                                   capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(undefined.stdout, '')
        linkmap = (self.package / 'pwd.map').read_text()
        for name in ('_start', '_darwin_static_start', '_zsh_main', '_darwin_network_command_main',
                     '_getopt', '_err', '_getprogname', '__NSGetProgname', '_vasprintf', '_getcwd', '_stat'):
            self.assertRegex(linkmap, re.compile(r'^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*\d+\]\s+' + re.escape(name) + '$', re.M))
        self.assertIn('libapple-posix.a(getcwd.o)', linkmap)
        self.assertIn('current-libc-getopt.o', linkmap)
        self.assertIn('current-libc-err.o', linkmap)
        self.assertIn('current-openssh-asprintf.o', linkmap)
        self.assertFalse(record['pi_executed'])


if __name__ == '__main__':
    unittest.main()
