# SPDX-License-Identifier: BSD-2-Clause
"""Verify storage source provenance rejects tampering; no kernel or disk proof."""
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_storage_build import ROOT, LOCK, compile_command, source_input, staged_hfs
import build_storage_provider as provider


class StorageAuditTests(unittest.TestCase):
    def fixture(self, cache):
        archive = cache / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as bundle:
            member = tarfile.TarInfo("test-1/example.c")
            member.size = len(b"/* source */\n")
            bundle.addfile(member, io.BytesIO(b"/* source */\n"))
        return {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(), "directory": "test-1"}

    def test_pristine_extraction_and_cached_mutation_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dep = self.fixture(root)
            source, hashes = source_input(root, root / "sources", "test", dep)
            self.assertEqual(set(hashes), {"example.c"})
            self.assertEqual(source_input(root, root / "sources", "test", dep), (source, hashes))
            (source / "example.c").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "differs from pinned"):
                source_input(root, root / "sources", "test", dep)

    def test_bad_archive_and_extra_cached_file_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dep = self.fixture(root)
            bad = dict(dep, sha256="0" * 64)
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                source_input(root, root / "sources", "test", bad)
            self.assertFalse((root / "sources").exists())
            source, _ = source_input(root, root / "sources", "test", dep)
            (source / "unexpected.h").write_bytes(b"unpinned")
            with self.assertRaisesRegex(RuntimeError, "unpinned files"):
                source_input(root, root / "sources", "test", dep)

    def test_compile_screen_retains_kernel_flags_but_isolates_outputs(self):
        template = {"file": "/kernel/IOCPU.cpp", "arguments": [
            "clang", "-xc++", "/kernel/IOCPU.cpp", "-o", "IOCPU.o", "-c", "-MMD",
            "-MF", "IOCPU.d", "-MT", "old-target", "-DKERNEL=1", "--target=arm64-apple-macosx27.0"]}
        command = compile_command(template, Path("/new/source.cpp"), Path("/new/output.o"),
                                  Path("/new/include"), Path("/new"))
        self.assertNotIn(template["file"], command)
        self.assertNotIn("IOCPU.o", command)
        self.assertNotIn("IOCPU.d", command)
        self.assertNotIn("-MMD", command)
        self.assertIn("-DKERNEL=1", command)
        self.assertIn("--target=arm64-apple-macosx27.0", command)
        self.assertEqual(command[-2:], ["-o", "/new/output.o"])

    def test_builtin_paging_calls_real_export_wrapper_only_when_adapted(self):
        template = {"file": "/kernel/memdev.c", "arguments": ["clang", "-c", "/kernel/memdev.c"]}
        args = (template, Path("/new/hfs.c"), Path("/new/hfs.o"), Path("/new/include"), Path("/new/core"))
        pristine = compile_command(*args, hfs=True)
        builtin = compile_command(*args, hfs=True, adapted=True)
        self.assertNotIn("-DRPI5_HFS_BUILTIN=1", pristine)
        self.assertIn("-DRPI5_HFS_BUILTIN=1", builtin)
        self.assertIn("-Dubc_create_upl=ubc_create_upl_external", builtin)
        self.assertIn(str(Path("/new/core/kext-config.h")), builtin)

    def test_storage_profile_is_opt_in_and_preserves_originals(self):
        originals = {name: (ROOT / "config" / name).read_bytes() for name in provider.MASTER_FILES}
        with tempfile.TemporaryDirectory() as temporary:
            profile = provider.prepare_config(Path(temporary))
            target = Path(profile["directory"]) / "MASTER.arm64.bcm2712"
            self.assertIn("config_fse fs_compression ]", target.read_text())
            self.assertIn("options CONFIG_RPI5_STORAGE", target.read_text())
            self.assertTrue(profile["requires_fs_compression"])
            for name, original in originals.items():
                self.assertEqual((ROOT / "config" / name).read_bytes(), original)

    def test_storage_build_requires_fresh_outputs_and_runtime_providers(self):
        for options in (("--profile", "xcode27"), ("--fresh", "--profile", "xcode27")):
            result = subprocess.run([sys.executable, str(ROOT / "tools/rpi5/rpi5.py"), "build",
                                     "--with-storage-provider", *options], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("requires --fresh", result.stderr)

    def test_incomplete_provider_evidence_fails_before_link(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text(json.dumps({"all_screened_units_compiled": True}))
            with mock.patch.object(provider.subprocess, "run") as execute:
                with self.assertRaisesRegex(RuntimeError, "lacks complete"):
                    provider.provider_from_screen(manifest)
                execute.assert_not_called()

    def test_changed_storage_object_fails_before_provider_link(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as temporary:
            run = Path(temporary)
            source = run / "fixture.cpp"
            source.write_bytes(b"/* isolated provenance fixture */\n")
            (run / "fixture.cpp.o").write_bytes(b"changed object")
            report = {"adapted": True, "all_core_units": True, "all_screened_units_compiled": True,
                      "partial_link": {"returncode": 0, "missing_required_definitions": [],
                                       "not_defined_in_reference_kernel": []},
                      "lock_sha256": provider.digest(LOCK),
                      "adaptation_patch_sha256": provider.digest(provider.HFS_PATCH),
                      "startup_patch_sha256": provider.digest(provider.HFS_STARTUP_PATCH),
                      "service_patch_sha256": provider.digest(provider.HFS_SERVICE_PATCH),
                      "compression_screen_header_sha256": provider.digest(provider.COMPRESSION_SCREEN),
                      "results": [{"source": str(source), "source_sha256": provider.digest(source),
                                   "unit": "fixture.cpp", "family": "IOStorageFamily", "object_sha256": "0" * 64}]}
            manifest = run / "manifest.json"
            manifest.write_text(json.dumps(report))
            with mock.patch.object(provider.subprocess, "run") as execute:
                with self.assertRaisesRegex(RuntimeError, "object changed after screen"):
                    provider.provider_from_screen(manifest)
                execute.assert_not_called()

    def hfs_source(self):
        cache = ROOT / "build/rpi5/gate4-reference"
        if not (cache / "hfs.tar.gz").is_file():
            self.skipTest("Pinned HFS archive is not prepared")
        dep = json.loads(LOCK.read_text())["dependencies"]["hfs"]
        return source_input(cache, ROOT / "build/rpi5/gate4-sources", "hfs", dep)

    def pi_screen_fixture(self, run, write_trial=False):
        """Opaque object bytes are only rejection fixtures, never linked."""
        rows = []
        units = provider.PI_STORAGE_WRITE_UNITS if write_trial else provider.PI_STORAGE_UNITS
        inputs = provider.PI_STORAGE_WRITE_INPUTS if write_trial else provider.PI_STORAGE_INPUTS
        for unit in units:
            source = ROOT / "iokit/Kernel" / unit
            obj = run / (unit + ".o")
            obj.write_bytes(b"not a Mach-O; guard-only fixture")
            rows.append({"family": "rpi5-storage", "unit": unit, "source": str(source),
                         "source_sha256": provider.digest(source), "object_sha256": provider.digest(obj)})
        return {"adapted": True, "all_core_units": True, "all_screened_units_compiled": True,
                "write_trial": write_trial,
                "partial_link": {"returncode": 0, "missing_required_definitions": [],
                                 "not_defined_in_reference_kernel": [], "forbidden_profile_definitions": []},
                "lock_sha256": provider.digest(LOCK),
                "adaptation_patch_sha256": provider.digest(provider.HFS_PATCH),
                "startup_patch_sha256": provider.digest(provider.HFS_STARTUP_PATCH),
                "service_patch_sha256": provider.digest(provider.HFS_SERVICE_PATCH),
                "compression_screen_header_sha256": provider.digest(provider.COMPRESSION_SCREEN),
                "pi_storage_input_sha256": {name: provider.digest(ROOT / "iokit/Kernel" / name)
                                            for name in inputs}, "results": rows}

    def test_write_profile_requires_explicit_build_opt_in(self):
        for script, options, message in (
            ('rpi5.py', ['build', '--storage-write-trial'], '--with-storage-provider'),
            ('audit_storage_build.py', ['--write-trial'], '--adapted --all-units'),
            ('audit_storage_build.py', ['--write-trial', '--adapted'], '--adapted --all-units'),
            ('audit_storage_build.py', ['--write-trial', '--all-units'], '--adapted --all-units'),
        ):
            with self.subTest(script=script, options=options):
                result = subprocess.run([sys.executable, str(ROOT / 'tools/rpi5' / script), *options],
                                        text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_write_profile_rejects_ambiguous_or_opposite_evidence_before_link(self):
        for selected in (False, True):
            for recorded in (not selected, 0, 1, None, 'true'):
                with self.subTest(selected=selected, recorded=recorded), tempfile.TemporaryDirectory(
                        dir=ROOT / 'build/rpi5') as temporary:
                    run = Path(temporary)
                    report = self.pi_screen_fixture(run, selected)
                    report['write_trial'] = recorded
                    manifest = run / 'manifest.json'
                    manifest.write_text(json.dumps(report))
                    with mock.patch.object(provider.subprocess, 'run') as execute:
                        with self.assertRaisesRegex(RuntimeError, 'profile does not match'):
                            provider.provider_from_screen(manifest, selected)
                        execute.assert_not_called()

    def test_write_profile_requires_exclusive_class_and_all_write_inputs(self):
        mutations = ('missing-forbidden-proof', 'opposite-class', 'missing-cache-header',
                     'changed-write-header', 'readonly-unit-substitution')
        for mutation in mutations:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(
                    dir=ROOT / 'build/rpi5') as temporary:
                run = Path(temporary)
                report = self.pi_screen_fixture(run, True)
                if mutation == 'missing-forbidden-proof':
                    report['partial_link'].pop('forbidden_profile_definitions')
                elif mutation == 'opposite-class':
                    report['partial_link']['forbidden_profile_definitions'] = [
                        '__ZN16BCM2712SDStorage10gMetaClassE']
                elif mutation == 'missing-cache-header':
                    report['pi_storage_input_sha256'].pop('rpi5_sd_cache.h')
                elif mutation == 'changed-write-header':
                    report['pi_storage_input_sha256']['rpi5_sd_write_policy.h'] = '0' * 64
                else:
                    report['results'][-1] = self.pi_screen_fixture(run)['results'][-1]
                manifest = run / 'manifest.json'
                manifest.write_text(json.dumps(report))
                with mock.patch.object(provider.subprocess, 'run') as execute:
                    with self.assertRaises(RuntimeError):
                        provider.provider_from_screen(manifest, True)
                    execute.assert_not_called()

    def test_pi_unit_omission_and_duplication_fail_before_link(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate), tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as temporary:
                run = Path(temporary)
                report = self.pi_screen_fixture(run)
                if duplicate:
                    report["results"].append(report["results"][0])
                else:
                    report["results"].pop()
                manifest = run / "manifest.json"
                manifest.write_text(json.dumps(report))
                with mock.patch.object(provider.subprocess, "run") as execute:
                    with self.assertRaisesRegex(RuntimeError, "real Pi storage adapter units"):
                        provider.provider_from_screen(manifest)
                    execute.assert_not_called()

    def test_pi_header_missing_or_changed_fails_before_link(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as temporary:
                run = Path(temporary)
                report = self.pi_screen_fixture(run)
                hashes = report["pi_storage_input_sha256"]
                if missing:
                    hashes.pop("rpi5_sd_contract.h")
                else:
                    hashes["rpi5_sd_contract.h"] = "0" * 64
                manifest = run / "manifest.json"
                manifest.write_text(json.dumps(report))
                with mock.patch.object(provider.subprocess, "run") as execute:
                    with self.assertRaisesRegex(RuntimeError, "provenance|SHA-256 mismatch"):
                        provider.provider_from_screen(manifest)
                    execute.assert_not_called()

    def test_pi_substituted_source_path_fails_before_link(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "build/rpi5") as temporary:
            run = Path(temporary)
            report = self.pi_screen_fixture(run)
            copy = run / "substituted.c"
            copy.write_bytes((ROOT / "iokit/Kernel" / provider.PI_STORAGE_UNITS[0]).read_bytes())
            report["results"][0]["source"] = str(copy)
            manifest = run / "manifest.json"
            manifest.write_text(json.dumps(report))
            with mock.patch.object(provider.subprocess, "run") as execute:
                with self.assertRaisesRegex(RuntimeError, "not the real adapter"):
                    provider.provider_from_screen(manifest)
                execute.assert_not_called()

    def test_reviewed_patch_changes_fresh_copy_only(self):
        source, hashes = self.hfs_source()
        with tempfile.TemporaryDirectory() as temporary:
            staged = staged_hfs(source, Path(temporary))
            self.assertNotEqual((staged / "core/hfs_iokit.h").read_bytes(),
                                (source / "core/hfs_iokit.h").read_bytes())
            self.assertEqual(self.hfs_source(), (source, hashes))
            config = (staged / "core/kext-config.h").read_text()
            self.assertIn("#include <quota.h>", config)
            self.assertIn("#define CONFIG_PROTECT 0", config)
            vfsops = (staged / "core/hfs_vfsops.c").read_text()
            guard = vfsops.index("if (vfs_flags(mp) & MNT_CPROTECT)")
            self.assertLess(guard, vfsops.index("retval = copyin(data"))

    @unittest.skipUnless(platform.system() == "Darwin", "Requires native sanitizer compiler")
    def test_actual_header_validator_rejects_protected_media(self):
        source, _ = self.hfs_source()
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary)
            staged = staged_hfs(source, run)
            text = (staged / "core/hfs_vfsutils.c").read_text()
            start = text.index("OSErr hfs_ValidateHFSPlusVolumeHeader(")
            end = text.index("\n}\n", start) + 3
            function = text[start:end]
            harness = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
typedef int OSErr;
typedef uint16_t u_int16_t;
typedef uint32_t u_int32_t;
struct hfsmount { uint32_t hfs_logical_block_size; };
typedef struct { uint16_t signature, version; uint32_t attributes, blockSize; } HFSPlusVolumeHeader;
#define CONFIG_PROTECT 0
#define SWAP_BE16(x) __builtin_bswap16(x)
#define SWAP_BE32(x) __builtin_bswap32(x)
#define kHFSPlusSigWord 0x482b
#define kHFSXSigWord 0x4858
#define kHFSPlusVersion 4
#define kHFSXVersion 5
#define kHFSContentProtectionMask 0x40000000U
#define HFS_MOUNT_DEBUG 0
#define powerof2(x) (((x) & ((x) - 1)) == 0)
''' + function + r'''
int main(void) {
    struct hfsmount mp = { 512 };
    HFSPlusVolumeHeader vh = { SWAP_BE16(kHFSPlusSigWord), SWAP_BE16(4), 0, SWAP_BE32(4096) };
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == 0);
    vh.attributes = SWAP_BE32(kHFSContentProtectionMask);
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == (RPI5_HFS_BUILTIN ? ENOTSUP : 0));
    vh.attributes = 0;
    vh.blockSize = SWAP_BE32(511);
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == EINVAL);
    vh.blockSize = SWAP_BE32(768);
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == EINVAL);
    vh.blockSize = SWAP_BE32(512); mp.hfs_logical_block_size = 4096;
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == EINVAL);
    mp.hfs_logical_block_size = 512;
    vh.signature = SWAP_BE16(kHFSXSigWord); vh.version = SWAP_BE16(5);
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == 0);
    vh.version = SWAP_BE16(4);
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == EINVAL);
    vh.signature = 0;
    assert(hfs_ValidateHFSPlusVolumeHeader(&mp, &vh) == EINVAL);
}
'''
            fixture = run / "validator.c"
            fixture.write_text(harness)
            for builtin in (0, 1):
                executable = run / ("validator-" + str(builtin))
                subprocess.run(["xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                                "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
                                "-DRPI5_HFS_BUILTIN=" + str(builtin), str(fixture), "-o", str(executable)],
                               check=True, capture_output=True)
                subprocess.run([str(executable)], check=True, capture_output=True)


if __name__ == "__main__":
    unittest.main()
