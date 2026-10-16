# SPDX-License-Identifier: BSD-2-Clause
import json
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/rpi5"))
import build_pthread_provider as provider


class ProviderPinTests(unittest.TestCase):
    def test_permanent_pthread_sysctl_is_not_registered_late(self):
        lock = json.loads(provider.LOCK.read_text())
        stage, source, _ = provider.prepare_source(
            ROOT / "build/rpi5-xcode27", lock)
        del stage
        support = (source / "kern/kern_support.c").read_text()
        self.assertIn("SYSCTL_INT(_kern, OID_AUTO, pthread_mutex_default_policy", support)
        self.assertNotIn("sysctl_register_oid(&sysctl__kern_pthread_mutex_default_policy)",
                         support)

    def test_ramdisk_root_does_not_require_block_storage_class(self):
        service = (ROOT / "iokit/Kernel/IOService.cpp").read_text()
        self.assertIn("assert(ioblockstoragedriverClass || !root);", service)
        self.assertIn("assert(iomediaClass || !parent);", service)
        self.assertIn("if (wasHiding && iomediaClass)", service)

    def test_unavailable_amfi_entitlement_queries_fail_closed(self):
        source = (ROOT / "iokit/bsddev/IOKitBSDInit.cpp").read_text()
        checks = source.count("|| amfi == NULL")
        self.assertEqual(checks, 5)

    def test_registration_precedes_late_read_only_lockdown(self):
        startup = (ROOT / "osfmk/kern/startup.c").read_text()
        registration = startup.index("if (pthread_start(NULL, NULL) != KERN_SUCCESS)")
        lockdown = startup.index("PE_lockdown_iokit();")
        self.assertLess(registration, lockdown)
        self.assertNotIn("pthread_start(NULL, NULL)",
                         (ROOT / "bsd/kern/bsd_init.c").read_text())

    def test_pthread_boot_build_requires_crypto_startup(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/rpi5/rpi5.py"), "build",
             "--profile", "xcode27", "--with-pthread-provider"],
            capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires --activate-crypto", result.stderr)

    def test_archive_hash_mismatch_stops_before_extraction(self):
        lock = json.loads(provider.LOCK.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            (build / f"{lock['libpthread']['tag']}.tar.gz").write_bytes(b"wrong archive")
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                provider.prepare_source(build, lock)
            self.assertFalse((build / "pthread-provider").exists())

    def test_stage_key_tracks_patches_and_header(self):
        initial = provider.provider_key("a", {"source": "b"}, "c")
        self.assertEqual(initial, provider.provider_key("a", {"source": "b"}, "c"))
        self.assertNotEqual(initial, provider.provider_key("a", {"source": "changed"}, "c"))
        self.assertNotEqual(initial, provider.provider_key("a", {"source": "b"}, "changed"))

    def test_missing_archive_is_fetched_and_verified_before_install(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / "pinned.tar.gz"
            payload = b"pinned source"
            pinned = {"sha256": hashlib.sha256(payload).hexdigest(),
                      "url": "https://example.invalid/pinned.tar.gz"}

            def fake_curl(command, **kwargs):
                Path(command[command.index("--output") + 1]).write_bytes(payload)
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(provider.subprocess, "run", side_effect=fake_curl):
                provider.fetch_archive_if_missing(archive, pinned)
            self.assertEqual(archive.read_bytes(), payload)


@unittest.skipUnless(platform.system() == "Darwin", "Requires Xcode 27")
class ProviderBuildTests(unittest.TestCase):
    def test_cached_patched_source_mutation_is_rejected(self):
        build = ROOT / "build/rpi5-xcode27"
        archive = build / "libpthread-539.100.4.tar.gz"
        if not archive.is_file():
            self.skipTest("Gate 2 libpthread archive is not prepared")
        lock = json.loads(provider.LOCK.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            isolated = Path(temporary)
            shutil.copyfile(archive, isolated / archive.name)
            stage, source, _ = provider.prepare_source(isolated, lock)
            target = source / "kern/kern_init.c"
            target.write_bytes(target.read_bytes() + b"\n")
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                provider.prepare_source(isolated, lock)

    def test_real_sources_compile_with_pinned_archive_and_48_byte_layout(self):
        build = ROOT / "build/rpi5-xcode27"
        database = build / "obj/DEVELOPMENT_ARM64_BCM2712/compile_commands.json"
        archive = build / "libpthread-539.100.4.tar.gz"
        if not database.is_file() or not archive.is_file():
            self.skipTest("Gate 2 Xcode 27 inputs are not prepared")
        report = provider.compile_provider(build, build / "obj")
        self.assertEqual(len(report["commands"]), 3)
        self.assertTrue(all(command["exit_code"] == 0 for command in report["commands"]))
        self.assertTrue(all(not Path(command["log"]).read_text().strip()
                            for command in report["commands"]))
        symbols = subprocess.check_output(["nm", "-gU", report["object"]], text=True)
        self.assertIn("_pthread_start", symbols)
        self.assertIn("_rpi5_pthread_kern", symbols)
        self.assertNotIn(" _pthread_kern\n", symbols)
        self.assertNotIn("___dso_handle", report["undefined_symbols"])


if __name__ == "__main__":
    unittest.main()
