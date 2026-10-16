# SPDX-License-Identifier: BSD-2-Clause
"""Small focused controls for the new manifest/runner boundary; no VM claims."""
import json
from pathlib import Path
import tempfile
import unittest

from pack_darwin_workload import entry_script, validate_spec
from workload_runner import digest, outcome, package_manifest


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads((Path(__file__).resolve().parent.parent / "examples/counter/workload.json").read_text())

    def test_valid_manifest_and_literal_script(self):
        validated = validate_spec(self.spec)
        script = entry_script(validated).decode()
        self.assertIn("exec /bin/zsh -f /app/counter.zsh 'argument with spaces'", script)
        self.assertIn("builtin cd -- /data || exit 125", script)
        self.assertNotIn("eval ", script)

    def test_invalid_manifest_boundaries(self):
        for change in ({"entrypoint": ["zsh"]}, {"cwd": "/data/../"}, {"network": "host"},
                       {"resources": {"cpus": 2}}, {"env": {"DYLD_INSERT_LIBRARIES": "x"}},
                       {"entrypoint": ["/bin/zsh", "\0"]}, {"unknown": True},
                       {"files": [{"source": "x", "path": "/sbin/launchd"}]},
                       {"files": [{"source": "x", "path": "/app/entry.zsh"}]}):
            with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                validate_spec(self.spec | change)

    def result(self):
        return {"started": True, "guestStopped": True, "termination": "guestStopped", "agent": {
            "protocolValid": True, "handshakeCompleted": True, "shutdownAcknowledged": True,
            "commands": [{"terminalObserved": True, "cleanupVerified": True, "stdoutEOF": True,
                          "stderrEOF": True, "exitStatus": 7}]}}

    def test_nonzero_is_completed_not_success(self):
        record = outcome(self.result(), 7)
        self.assertEqual((record["state"], record["runner_exit_code"]), ("exited", 7))
        self.assertTrue(record["managed_completion_verified"])

    def test_missing_stop_or_stream_cannot_pass(self):
        result = self.result()
        result["guestStopped"] = False
        self.assertEqual(outcome(result, 7)["state"], "failed")
        result = self.result()
        result["agent"]["commands"][0]["stderrEOF"] = False
        self.assertEqual(outcome(result, 7)["state"], "failed")

    def test_cancel_and_deadline_distinct(self):
        result = self.result()
        result["termination"] = "interrupted"
        result["agent"]["commands"][0]["cancelled"] = True
        self.assertEqual(outcome(result, 1, True)["runner_exit_code"], 130)
        result["termination"] = "timedOut"
        self.assertEqual(outcome(result, 1)["runner_exit_code"], 124)

    def test_package_hash_and_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            package = Path(temporary)
            names = ("container", "darwin", "support/workspace_launcher.py", "workload.json", "efi-template.img",
                     "loader-template.efi", "kernel.macho", "ramdisk.bin", "data-template.raw")
            for name in names:
                path = package / name
                path.parent.mkdir(exist_ok=True)
                path.write_text("placeholder")
            (package / "workload.json").write_text(json.dumps({"resources": {"cpus": 1, "memory_mib": 512}}))
            manifest = {"format": "darwin-workload-package-1", "immutable_sha256": {name: digest(package / name) for name in names}}
            (package / "manifest.json").write_text(json.dumps(manifest))
            package_manifest(package)
            (package / "ramdisk.bin").write_text("changed")
            with self.assertRaisesRegex(RuntimeError, "input changed"):
                package_manifest(package)
            (package / "ramdisk.bin").unlink()
            (package / "ramdisk.bin").symlink_to(package / "kernel.macho")
            with self.assertRaisesRegex(RuntimeError, "symlink rejected"):
                package_manifest(package)


if __name__ == "__main__":
    unittest.main()
