# SPDX-License-Identifier: BSD-2-Clause
"""Synthetic format/pin failures; no Pi boot or source authenticity claim."""
import hashlib
import unittest

from tools.rpi5.check_zsh_ramroot import check
from tools.rpi5.ramroot import build
from tools.rpi5.tests.test_prepare_pid1 import fixture


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ZshRamrootTests(unittest.TestCase):
    def root(self, shell=None):
        exe = bytes(fixture())
        files = {"/sbin/launchd": (exe, 0o555)}
        if shell is not None:
            files["/bin/zsh"] = shell
        return build(files)[0]

    def test_pinned_structural_preflight_is_not_hardware_proof(self):
        exe = bytes(fixture())
        root = self.root((exe, 0o555))
        result = check(root, exe, digest(root), digest(exe))
        self.assertTrue(result["passed"])
        self.assertEqual(result["format"], "RPI5RFS1")
        for field in ("pi_executed", "source_provenance_audited",
                      "isa_and_syscall_compatibility_proven"):
            self.assertFalse(result[field])
        self.assertEqual(result["sd_actions"], 0)

    def test_wrong_pins_and_malformed_root_rejected(self):
        exe = bytes(fixture())
        root = self.root((exe, 0o555))
        for rh, zh in (("0" * 64, digest(exe)), (digest(root), "0" * 64),
                       ("bad", digest(exe)), (digest(root), "A" * 64)):
            with self.subTest(rh=rh, zh=zh), self.assertRaises(ValueError):
                check(root, exe, rh, zh)
        bad = root[:-1] + b"x"
        with self.assertRaises(ValueError):
            check(bad, exe, digest(bad), digest(exe))

    def test_missing_nonexecutable_or_mismatched_shell_rejected(self):
        exe = bytes(fixture())
        for root in (self.root(), self.root((exe, 0o444))):
            with self.assertRaises(ValueError):
                check(root, exe, digest(root), digest(exe))
        other = exe + bytes(8)  # Still structurally valid, different payload.
        root = self.root((other, 0o555))
        with self.assertRaises(ValueError):
            check(root, exe, digest(root), digest(exe))


if __name__ == "__main__":
    unittest.main()
