# SPDX-License-Identifier: BSD-2-Clause
"""Native shell/utility logic fixtures, explicitly not physical XNU evidence."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.rpi5.hfs_read_results import frame_markers, parse_file
import hashlib

ROOT = Path(__file__).resolve().parents[3]
USER = ROOT / "tools/rpi5/user"
HERE = Path(__file__).parent

class ShellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.shell = Path(cls.tmp.name) / "sh"
        cls.parser = Path(cls.tmp.name) / "parser"
        flags = ["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined"]
        subprocess.run(flags + [str(HERE / "shell_host.c"), str(USER / "parser.c"),
                               str(USER / "shell.c"), str(USER / "utilities.c"), "-o", str(cls.shell)], check=True)
        subprocess.run(flags + [str(HERE / "parser_host.c"), str(USER / "parser.c"), "-o", str(cls.parser)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_shell(self, command, status=0):
        result = subprocess.run([str(self.shell), "-c", command], capture_output=True, timeout=10,
                                env={"PWD": "/", "PATH": "/bin:/usr/bin"})
        self.assertEqual(result.returncode, status, result.stderr.decode())
        self.assertNotIn(b"Sanitizer", result.stderr)
        return result

    def test_parser_boundaries_and_random_inputs(self):
        result = subprocess.run([str(self.parser)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(result.stdout, b"PARSER_PASS\n")

    def test_real_external_exec_quote_pipeline(self):
        result = self.run_shell("echo 'hello world' | /usr/bin/wc -c")
        self.assertEqual(int(result.stdout.strip()), 12)

    def test_conditionals_and_exact_wait_status(self):
        # macOS installs these in /usr/bin; target RAM root uses /bin.
        self.assertEqual(self.run_shell("/usr/bin/false && echo BAD || echo GOOD").stdout, b"GOOD\n")
        self.assertEqual(self.run_shell("/usr/bin/true || echo BAD && echo GOOD").stdout, b"GOOD\n")
        self.run_shell("/usr/bin/false", 1)
        self.run_shell("no_such_rpi5_program", 127)

    def test_cd_and_builtin_redirection_restore(self):
        result = self.run_shell("cd /etc; pwd > /dev/null; pwd; cd /no_such_directory || echo RECOVERED")
        self.assertEqual(result.stdout, b"/etc\nRECOVERED\n")

    def test_script_and_input_redirect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "script"
            path.write_text("echo SCRIPT\nfalse || echo RECOVERED\npwd\n")
            result = subprocess.run([str(self.shell), str(path)], capture_output=True, timeout=10,
                                    env={"PWD": "/"})
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, b"SCRIPT\nRECOVERED\n/\n")
            result = self.run_shell(f"cat < '{path}' | /usr/bin/wc -l")
            self.assertEqual(int(result.stdout.strip()), 3)

    def test_utility_streams_and_errors(self):
        for name, data, expected in (("cat", b"one two\n", b"one two\n"),
                                     ("wc", b"one two\n", b"1 2 8\n"),
                                     ("hexdump", b"\x00\xff\n", b"00 ff 0a \n")):
            result = subprocess.run([str(self.shell), "--utility", name], input=data, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(result.stdout, expected)
        result = subprocess.run([str(self.shell), "--utility", "sleep", "3601"], capture_output=True)
        self.assertEqual(result.returncode, 2)

    def test_actual_hexdump_utility_matches_complete_file_parser(self):
        # Compile and execute the target's unchanged utilities.c against the
        # native POSIX adapter, rather than generating our own matching grammar.
        # This is host transport-format evidence only, not an HFS mount/read.
        nonce = 'H0123456789abcdef'
        begin, end = frame_markers(nonce)
        for data in (b'', b'\x00\xff\n', bytes(range(16)),
                     bytes(range(256)) * 129 + b'GATE4 END\n'):
            with self.subTest(size=len(data)):
                result = subprocess.run([str(self.shell), '--utility', 'hexdump'], input=data,
                                        capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertNotIn(b'Sanitizer', result.stderr)
                response = begin + b'\n' + result.stdout + end + b'\nxnu:/# '
                entry = {'path': '/etc/cross-page.bin', 'bytes': len(data),
                         'sha256': hashlib.sha256(data).hexdigest()}
                self.assertEqual(parse_file(response, entry, nonce)['sha256'], entry['sha256'])

    def test_syntax_failure_executes_nothing(self):
        result = self.run_shell("echo BAD; echo 'unterminated", 2)
        self.assertEqual(result.stdout, b"")

if __name__ == "__main__":
    unittest.main()
