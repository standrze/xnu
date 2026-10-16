#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Apple Libc-167 FILE-free perror and genuine writev provider tests."""

import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import unittest

from tools.rpi5 import build_apple_ssh_perror as build
from tools.rpi5.tests.test_apple_pthread_startup_contract import validate_closure


PACKAGE = Path(os.environ["RPI5_PERROR_PACKAGE"]).resolve() if os.environ.get("RPI5_PERROR_PACKAGE") else None
PIN = os.environ.get("RPI5_PERROR_MANIFEST_SHA256")


def closure(manifest):
    base = json.loads((build.BASE / "manifest.json").read_text())
    expected = build.merge({str(build.BASE / "manifest.json"): build.BASE_SHA},
                           *[base[key] for key in ("source_inputs_sha256", "headers_sha256", "generated_sha256")])
    for path in (Path(build.__file__).resolve(), build.LOCK, build.ARCHIVE, build.SOURCE, build.SYSCALL, build.HARNESS,
                 build.TEST, build.CLOSURE_TEST, build.ROOT / "tools/rpi5/prepare_pid1.py"):
        expected[str(path)] = build.sha(path)
    tools = {
        str(Path(subprocess.check_output(["xcrun", "--find", name], text=True).strip()).resolve()): None
        for name in ("clang", "ar", "nm", "ld", "llvm-objdump")
    }
    tools[str(Path("/usr/bin/xcrun").resolve())] = None
    tools = {name: build.sha(name) for name in tools}
    expected = build.merge(expected, tools)
    if manifest["source_inputs_sha256"] != expected or manifest["tools_sha256"] != tools:
        raise ValueError("Complete source/tool closure")
    if set(manifest["dependency_records"]) != {"target-perror", "target-writev", "host-perror", "host-harness"}:
        raise ValueError("Complete compile membership")
    headers = {}
    for label, row in manifest["dependency_records"].items():
        raw = (PACKAGE / (label + ".d")).read_text().replace("\\\n", " ").partition(":")[2]
        actual = {str(Path(name).resolve()): build.sha(Path(name).resolve()) for name in shlex.split(raw)}
        if row != {"scanned_sha256": actual, "consumed_sha256": actual}:
            raise ValueError("Compiler dependency closure")
        headers.update(actual)
    if headers != manifest["headers_sha256"]:
        raise ValueError("Complete header union")
    validate_closure(PACKAGE, manifest)


class AppleOpenSSHPerrorTests(unittest.TestCase):
    def setUp(self):
        if PACKAGE is None or PIN is None:
            self.fail("Supply retained package and manifest pin")
        self.assertEqual(build.sha(PACKAGE / "manifest.json"), PIN)
        self.manifest = json.loads((PACKAGE / "manifest.json").read_text())

    def test_exact_source_header_generated_membership(self):
        closure(self.manifest)
        for key in ("source_inputs_sha256", "headers_sha256", "generated_sha256", "tools_sha256"):
            bad = copy.deepcopy(self.manifest)
            bad[key].pop(next(iter(bad[key])))
            with self.subTest(key=key), self.assertRaises(ValueError):
                closure(bad)

    def test_exact_apple_source_is_file_free_and_writev_is_real_syscall(self):
        lock = json.loads(build.LOCK.read_text())
        pin = next(row for row in lock["sources"] if row["tag"] == build.LIBC167_TAG)
        self.assertEqual(pin["commit"], build.LIBC167_COMMIT)
        self.assertEqual(pin["archiveSHA256"], build.LIBC167_ARCHIVE_SHA)
        self.assertEqual(build.sha(build.ARCHIVE), build.LIBC167_ARCHIVE_SHA)
        self.assertEqual(build.sha(build.SOURCE), build.SOURCE_SHA)
        with tarfile.open(build.ARCHIVE, "r:gz") as archive:
            archived = archive.extractfile("Libc-Libc-167/stdio.subproj/perror.c")
            self.assertIsNotNone(archived)
            self.assertEqual(build.SOURCE.read_bytes(), archived.read())
        source = build.SOURCE.read_text()
        for forbidden in (r"\bFILE\b", r"\bstderr\b", r"\b_file\b", r"\bFLOCKFILE\b", r"\b__sflush\b"):
            self.assertIsNone(re.search(forbidden, source))
        assembly = build.SYSCALL.read_text()
        self.assertIn("__SYSCALL2(_writev, writev, 3, cerror_nocancel)", assembly)
        self.assertNotIn("fixture", assembly)
        self.assertTrue(self.manifest["original_source_unchanged"])
        self.assertFalse(self.manifest["source_accesses_FILE"])
        self.assertEqual(self.manifest["object_exports"], {"perror": ["_perror"], "writev": ["_writev"]})

    def test_exact_full_client_delta_and_forced_archive_owners(self):
        base = json.loads((build.BASE / "manifest.json").read_text())
        expected = list(next(c["command"] for c in base["commands"] if c["stdout"].endswith("/target-link.stdout")))
        self.assertEqual(self.manifest["original_full_client_link_command"], expected)
        actual = next(c for c in self.manifest["commands"] if c["stdout"].endswith("/target-link.stdout"))
        expected[expected.index("-o") + 1] = str(PACKAGE / "NOT_RUN_ssh")
        expected[expected.index("-map") + 1] = str(PACKAGE / "target.map")
        expected.append(self.manifest["target_archive"])
        self.assertEqual(actual["command"], expected)
        self.assertNotEqual(actual["returncode"], 0)
        missing = sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:', Path(actual["stderr"]).read_text(), re.M)))
        self.assertEqual(missing, self.manifest["target_missing_symbols"])
        self.assertEqual(len(missing), 34)
        self.assertEqual(set(base["target_missing_symbols"]) - set(missing), {"_perror"})
        self.assertFalse(set(missing) - set(base["target_missing_symbols"]))
        self.assertEqual(self.manifest["target_duplicate_symbols"], [])
        target = PACKAGE / "NOT_RUN_perror_contract"
        self.assertEqual(subprocess.check_output(["xcrun", "nm", "-ju", target], text=True), "")
        for symbol in ("_perror", "_writev"):
            self.assertIn(symbol, self.manifest["forced_live_exports"])
            self.assertTrue(self.manifest["live_symbol_owners"][symbol].startswith(self.manifest["target_archive"] + "("))

    def test_native_iovec_shape_errno_and_failure_oracles(self):
        process = subprocess.run([PACKAGE / "perror-host"], capture_output=True, text=True, timeout=20)
        self.assertEqual((process.returncode, process.stdout, process.stderr), (0, self.manifest["native_stdout"], ""))
        process = subprocess.run([PACKAGE / "perror-host", "bad"], capture_output=True, text=True, timeout=20)
        self.assertEqual(process.returncode, 37)
        self.assertTrue(self.manifest["native_asan_ubsan_pass"])
        self.assertEqual(self.manifest["native_boundaries"], ["errno", "strerror", "writev capture"])

    def test_scope_and_service_boundaries_remain_explicit(self):
        self.assertTrue(self.manifest["resolver_notify_service_gates_unchanged"])
        for key in ("accepted_runtime_modified", "provider_stubs", "optional_features_removed", "target_executed", "full_client_qualified"):
            self.assertIs(self.manifest[key], False)
        self.assertEqual(self.manifest["filesystem_layout"], ["/usr/bin/ssh", "/usr/sbin/sshd", "/usr/libexec", "/private/etc/ssh"])


if __name__ == "__main__":
    unittest.main()
