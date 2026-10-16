# SPDX-License-Identifier: BSD-2-Clause
"""Native logic tests only: no target executable, VM or host reboot is run."""

from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "src"


class UserlandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="darwin-vm-userland-tests-")
        cls.shell = Path(cls.tmp.name) / "sh"
        cls.parser = Path(cls.tmp.name) / "parser"
        cls.init = Path(cls.tmp.name) / "init-policy"
        cls.agent_init = Path(cls.tmp.name) / "agent-init-policy"
        flags = ["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror", "-fsanitize=address,undefined"]
        subprocess.run(flags + [str(HERE / "shell_host.c"),
                               *(str(SOURCE / n) for n in ("parser.c", "shell.c", "utilities.c", "poweroff.c")),
                               "-o", str(cls.shell)], check=True, capture_output=True, timeout=60)
        subprocess.run(flags + [str(HERE / "parser_host.c"), str(SOURCE / "parser.c"), "-o", str(cls.parser)],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(flags + [str(HERE / "init_host.c"), str(SOURCE / "init.c"), "-o", str(cls.init)],
                       check=True, capture_output=True, timeout=60)
        subprocess.run(flags + ["-DDARWIN_AGENT_INIT=1", str(HERE / "init_host.c"), str(SOURCE / "init.c"),
                                "-o", str(cls.agent_init)], check=True, capture_output=True, timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def invoke(self, *args, data=None):
        result = subprocess.run([str(self.shell), *args], input=data, capture_output=True, timeout=10,
                                env={"PWD": "/", "PATH": "/bin:/usr/bin"})
        self.assertNotIn(b"Sanitizer", result.stderr)
        return result

    def test_parser_boundaries(self):
        result = subprocess.run([str(self.parser)], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b"PARSER_PASS\n")

    def test_pid1_shutdown_quiesces_without_exit_or_respawn_and_restores_child_mask(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.init), str(mode)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, b"INIT_PASS\n")
                self.assertNotIn(b"Sanitizer", result.stderr)

    def test_agent_pid1_restores_child_mask_reaps_descendants_and_parks_after_agent_failure(self):
        for mode in range(4):
            with self.subTest(mode=mode):
                result = subprocess.run([str(self.agent_init), str(mode)], capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, b"INIT_PASS\n")
                self.assertNotIn(b"Sanitizer", result.stderr)

    def test_nonce_output_is_on_own_lines_and_ready_is_once(self):
        result = self.invoke(data=b"echo DARWIN:CMD:test:START\n/usr/bin/false\necho DARWIN:CMD:test:EXIT:$?\nexit\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines.count(b"DARWIN:SHELL:READY"), 1)
        self.assertIn(b"DARWIN:CMD:test:START", lines)
        self.assertIn(b"DARWIN:CMD:test:EXIT:1", lines)
        self.assertNotIn(b"DARWIN:CMD:test:EXIT:0", lines)
        self.assertNotIn(b"RPI5XNU", result.stdout)

    def test_noninteractive_does_not_claim_console_readiness(self):
        result = self.invoke("-c", "echo actual-exec | /usr/bin/wc -c")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(int(result.stdout.strip()), 12)
        self.assertNotIn(b"DARWIN:SHELL:READY", result.stdout)

    def test_echo_and_cat_use_actual_utility_source(self):
        result = self.invoke("--utility", "echo", "hello", "Darwin")
        self.assertEqual((result.returncode, result.stdout), (0, b"hello Darwin\n"))
        result = self.invoke("--utility", "cat", data=b"source-built\n")
        self.assertEqual((result.returncode, result.stdout), (0, b"source-built\n"))

    def test_poweroff_uses_stubbed_darwin_halt_and_never_claims_returned_success(self):
        result = self.invoke("--utility", "poweroff")
        self.assertEqual(result.returncode, 1)
        self.assertIn(b"HOST_STUB:REBOOT:8:0\n", result.stdout)
        self.assertIn(b"poweroff/reboot: errno 1\n", result.stderr)
        result = self.invoke("--utility", "poweroff", "unexpected")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn(b"HOST_STUB:REBOOT", result.stdout)


if __name__ == "__main__":
    unittest.main()
