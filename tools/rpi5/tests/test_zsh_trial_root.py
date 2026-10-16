# SPDX-License-Identifier: BSD-2-Clause
import hashlib
import unittest

from tools.rpi5.prepare_zsh_trial_root import files_from, prepare, SMOKE
from tools.rpi5.ramroot import build
from tools.rpi5.tests.test_prepare_pid1 import fixture


def sha(data):
    return hashlib.sha256(data).hexdigest()


class ZshTrialRootTests(unittest.TestCase):
    def roots(self, extra=None, terminfo=True):
        executable = bytes(fixture())
        pi = {name: (executable, 0o555) for name in
              ("/sbin/launchd", "/bin/sh", "/bin/echo", "/bin/uname")}
        pi["/etc/motd"] = (b"Pi recovery\n", 0o444)
        pi.update(extra or {})
        vm = {"/sbin/launchd": (executable, 0o555), "/bin/zsh": (executable, 0o555),
              "/bin/poweroff": (executable, 0o555)}
        if terminfo:
            vm["/etc/terminfo/64/dumb"] = (b"terminal fixture", 0o444)
        return build(pi)[0], build(vm)[0], executable

    def test_preserves_every_pi_file_and_excludes_vm_bootstrap(self):
        pi, vm, executable = self.roots()
        image, report = prepare(pi, vm, executable, sha(pi), sha(vm), sha(executable))
        files = files_from(image)
        for name, record in files_from(pi).items():
            self.assertEqual(files[name], record)
        self.assertNotIn("/bin/poweroff", files)
        self.assertEqual(files["/etc/zsh-smoke.zsh"], (SMOKE, 0o444))
        self.assertEqual(files["/bin/zsh"], (executable, 0o555))
        self.assertFalse(report["pi_executed"])
        self.assertFalse(report["boot_package_preflight_passed"])

    def test_refuses_collisions_and_missing_terminal_data(self):
        for path in ("/bin/zsh", "/etc/zsh-smoke.zsh", "/etc/terminfo/64/dumb"):
            pi, vm, executable = self.roots({path: (b"preserve me", 0o444)})
            with self.subTest(path=path), self.assertRaises(ValueError):
                prepare(pi, vm, executable, sha(pi), sha(vm), sha(executable))
        pi, vm, executable = self.roots(terminfo=False)
        with self.assertRaises(ValueError):
            prepare(pi, vm, executable, sha(pi), sha(vm), sha(executable))

    def test_refuses_wrong_pins_and_missing_pi_recovery_shell(self):
        pi, vm, executable = self.roots()
        with self.assertRaises(ValueError):
            prepare(pi, vm, executable, "0" * 64, sha(vm), sha(executable))
        files = files_from(pi)
        del files["/bin/sh"]
        pi = build(files)[0]
        with self.assertRaises(ValueError):
            prepare(pi, vm, executable, sha(pi), sha(vm), sha(executable))


if __name__ == "__main__":
    unittest.main()
