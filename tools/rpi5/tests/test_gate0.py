# SPDX-License-Identifier: BSD-2-Clause
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import platform
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("rpi5", ROOT / "tools/rpi5/rpi5.py")
rpi5 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rpi5)


class ArchiveTests(unittest.TestCase):
    def test_exploratory_profile_is_separate_from_canonical_evidence(self):
        canonical = rpi5.select_profile("canonical")
        exploratory = rpi5.select_profile("xcode27")
        self.assertEqual(canonical, ROOT / "build/rpi5")
        self.assertEqual(exploratory, ROOT / "build/rpi5-xcode27")
        self.assertNotEqual(canonical, exploratory)
        with self.assertRaises(ValueError):
            rpi5.select_profile("unknown")

    def test_xcode27_profile_requires_exact_observed_toolchain(self):
        lock = {"toolchain": {"xcode": "26.6", "xcode_build": "17F113", "sdk": "26.5"}}
        values = {
            ("xcodebuild", "-version"): "Xcode 27.0\nBuild version 27A266a",
            ("xcrun", "--sdk", "macosx", "--show-sdk-version"): "27.0",
            ("xcrun", "--sdk", "macosx", "--show-sdk-path"): "/xcode27.sdk",
            ("xcrun", "clang", "--version"): "clang 27",
        }
        with mock.patch.object(rpi5.platform, "system", return_value="Darwin"), \
                mock.patch.object(rpi5, "capture", side_effect=lambda *args: values[args]):
            selected = rpi5.toolchain(lock, False, "xcode27")
            self.assertFalse(selected["canonical"])
            with self.assertRaisesRegex(RuntimeError, "Toolchain differs from lock"):
                rpi5.toolchain(lock, False, "canonical")
            values[("xcodebuild", "-version")] = "Xcode 27.1\nBuild version 27B123"
            with self.assertRaisesRegex(RuntimeError, "Xcode 27 profile differs"):
                rpi5.toolchain(lock, True, "xcode27")

    def test_prepared_toolchain_ignores_only_optional_host_macho_suffix(self):
        prepared = {"xcode": "27.0", "sdk": "27.0",
                    "host": "macOS-26.6.2-arm64-arm-64bit-Mach-O"}
        current = {**prepared, "host": "macOS-26.6.2-arm64-arm-64bit"}
        self.assertTrue(rpi5.same_prepared_toolchain(prepared, current))
        self.assertFalse(rpi5.same_prepared_toolchain(
            prepared, {**current, "xcode": "27.1"}))
        self.assertFalse(rpi5.same_prepared_toolchain(
            prepared, {**current, "host": "macOS-26.7-arm64-arm-64bit"}))
        self.assertFalse(rpi5.same_prepared_toolchain(
            prepared, {"sdk": "27.0", "host": current["host"]}))

    def test_hash_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "archive"
            path.write_bytes(b"source bytes")
            rpi5.verify_archive(path, hashlib.sha256(b"source bytes").hexdigest())
            with self.assertRaisesRegex(RuntimeError, "SHA-256 mismatch"):
                rpi5.verify_archive(path, "0" * 64)

    def test_archive_traversal_and_links_rejected(self):
        for name, kind in [("../escape", tarfile.REGTYPE),
                           ("/absolute", tarfile.REGTYPE),
                           ("source/link", tarfile.SYMTYPE),
                           ("wrong-root/file", tarfile.REGTYPE)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                archive = Path(tmp) / "source.tar.gz"
                with tarfile.open(archive, "w:gz") as bundle:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/tmp"
                    bundle.addfile(member)
                with self.assertRaisesRegex(RuntimeError, "Unsafe archive entry"):
                    rpi5.unpack_archive(archive, Path(tmp) / "out", "source")
                self.assertFalse((Path(tmp) / "out").exists())

    def test_valid_archive_extracts_without_overwriting_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "source.tar.gz"
            with tarfile.open(archive, "w:gz") as bundle:
                member = tarfile.TarInfo("source/file")
                member.size = 3
                bundle.addfile(member, io.BytesIO(b"abc"))
            target = Path(tmp) / "out"
            rpi5.unpack_archive(archive, target, "source")
            self.assertEqual((target / "source/file").read_bytes(), b"abc")
            with self.assertRaisesRegex(RuntimeError, "already exists"):
                rpi5.unpack_archive(archive, target, "source")


@unittest.skipUnless(platform.system() == "Darwin", "Requires native macOS build tools")
class PlatformTests(unittest.TestCase):
    def test_sdk_version_symlink_becomes_independent_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            original = base / "MacOSX.sdk"
            original.mkdir()
            (original / "header").write_text("original")
            version = base / "MacOSX26.5.sdk"
            version.symlink_to(original.name)
            copy = base / "copy.sdk"
            rpi5.clone_sdk(version, copy)
            self.assertFalse(copy.is_symlink())
            (copy / "header").write_text("overlay")
            self.assertEqual((original / "header").read_text(), "original")

    def test_bcm2712_feature_contract(self):
        command = ["xcrun", "clang", "-E", "-dM", "-x", "c", "-",
                   "-DDEVELOPMENT=1", "-I" + str(ROOT / "pexpert")]
        result = subprocess.run(command, input="#include <pexpert/arm64/BCM2712.h>\n",
                                text=True, capture_output=True, check=True)
        macros = {parts[1]: parts[2] if len(parts) > 2 else ""
                  for line in result.stdout.splitlines()
                  if len(parts := line.split(maxsplit=2)) >= 2}
        self.assertEqual(macros["__ARM_16K_PG__"], "1")
        self.assertEqual(macros["MAX_CPUS"], "4")
        self.assertEqual(macros["MAX_CPU_CLUSTER_PHY_ID"], "3")
        self.assertEqual(macros["NO_CPU_OVRD"], "1")
        for name in ("APPLE_ARM64_ARCH_FAMILY", "__ARM_COHERENT_IO__", "HAS_APPLE_PAC",
                     "__ARM_RANGE_TLBI__", "HAS_ARM_FEAT_SME", "USE_APPLEARMSMP"):
            self.assertNotIn(name, macros)
        command[command.index("-DDEVELOPMENT=1")] = "-DDEVELOPMENT=0"
        result = subprocess.run(command, input="#include <pexpert/arm64/BCM2712.h>\n",
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires the experimental DEVELOPMENT", result.stderr)

    def test_real_doconf_selects_pi_master_without_apple_security_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ | {"OBJROOT": tmp, "SRCROOT": str(ROOT),
                                "SOURCE": str(ROOT / "osfmk")}
            subprocess.run([str(ROOT / "SETUP/config/doconf"), "-cpu", "arm64",
                            "-soc", "bcm2712", "-platform", "MacOSX",
                            "-m", str(ROOT / "config"), "-d", tmp, "DEVELOPMENT"],
                           env=env, cwd=ROOT, check=True, capture_output=True, text=True)
            config = (Path(tmp) / "config.DEVELOPMENT_ARM64").read_text()
            options = {line.split()[1].split("=")[0] for line in config.splitlines()
                       if line.split() and line.split()[0] == "options"}
            for option in ("CONFIG_RPI5_BRINGUP", "DEVELOPMENT", "MOCKFS", "DEVFS",
                           "NOS_ARM_PMAP", "CONFIG_MEMORYSTATUS", "NAMEDSTREAMS",
                           "SOCKETS", "NETWORKING", "INET", "NECP", "TRAFFIC_MGT",
                           "KPERF", "CONFIG_FSE", "CONFIG_COREDUMP"):
                self.assertIn(option, options)
            for option in ("CONFIG_PMAP_PPL", "CONFIG_SPTM", "CONFIG_KERNEL_INTEGRITY",
                           "CONFIG_ENFORCE_SIGNED_CODE", "CONFIG_CPU_COUNTERS"):
                self.assertNotIn(option, options)

    def test_socket_network_dependency_source_selection(self):
        objroot = ROOT / "build/rpi5/obj"
        if not (objroot / "SETUP/config/config").is_file():
            self.skipTest("Run build --target exporthdrs to compile the config tool")
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ | {"OBJROOT": str(objroot), "SRCROOT": str(ROOT),
                                "SOURCE": str(ROOT / "bsd/conf")}
            subprocess.run([str(ROOT / "SETUP/config/doconf"), "-c", "-cpu", "arm64",
                            "-soc", "bcm2712", "-platform", "MacOSX",
                            "-s", str(ROOT / "bsd/conf"), "-m", str(ROOT / "config"),
                            "-d", tmp, "DEVELOPMENT"], env=env, cwd=ROOT,
                           check=True, capture_output=True, text=True)
            generated = (Path(tmp) / "Makefile").read_text()
            objects = generated.split("OBJS=", 1)[1].split("\n\n", 1)[0].split()
            for obj in ("uipc_socket.o", "uipc_usrreq.o", "fifo_vnops.o", "siphash.o",
                        "kern_core.o", "vfs_fsevents.o"):
                self.assertEqual(objects.count(obj), 1, obj)
            for obj in ("tcp_input.o", "ip_input.o", "necp.o", "multi_layer_pkt_log.o", "pf_pbuf.o"):
                self.assertEqual(objects.count(obj), 1, obj)

    def test_public_platform_source_selection(self):
        objroot = ROOT / "build/rpi5/obj"
        if not (objroot / "SETUP/config/config").is_file():
            self.skipTest("Run build --target exporthdrs to compile the config tool")
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ | {"OBJROOT": str(objroot), "SRCROOT": str(ROOT),
                                "SOURCE": str(ROOT / "osfmk/conf")}
            subprocess.run([str(ROOT / "SETUP/config/doconf"), "-c", "-cpu", "arm64",
                            "-soc", "bcm2712", "-platform", "MacOSX",
                            "-s", str(ROOT / "osfmk/conf"),
                            "-m", str(ROOT / "config"), "-d", tmp, "DEVELOPMENT"],
                           env=env, cwd=ROOT, check=True, capture_output=True, text=True)
            generated = (Path(tmp) / "Makefile").read_text()
            objects = generated.split("OBJS=", 1)[1].split("\n\n", 1)[0].split()
            for obj in ("pmap.o", "pmap_data.o", "arm_init.o", "arm_vm_init.o",
                        "start.o", "cswitch.o", "locore.o", "pcb.o"):
                self.assertIn(obj, objects)
                self.assertEqual(objects.count(obj), 1)
            self.assertNotIn("amcc_rorgn_common.o", objects)
            self.assertNotIn("amcc_rorgn_pv_ctrr.o", objects)


if __name__ == "__main__":
    unittest.main()
