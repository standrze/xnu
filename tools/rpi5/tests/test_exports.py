# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
import tempfile
import subprocess
import platform
import os
import plistlib
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "audit_exports", Path(__file__).resolve().parents[1] / "audit_exports.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
policy_spec = importlib.util.spec_from_file_location(
    "export_policy", Path(__file__).resolve().parents[1] / "export_policy.py")
policy = importlib.util.module_from_spec(policy_spec)
policy_spec.loader.exec_module(policy)


class ExportAuditTests(unittest.TestCase):
    def test_combined_policy_uses_generated_features_and_keeps_unreviewed_apis(self):
        root = Path(__file__).resolve().parents[3]
        config = 'export CONFIG_DEFINES = -DDEVELOPMENT -DCONFIG_RPI5_BRINGUP\n'
        for filename, count in (("Private.exports", 40), ("Private.arm64.exports", 73)):
            text = (root / "config" / filename).read_text()
            output = policy.apply_reviewed_policy(text, filename=filename,
                                                  config_text=config,
                                                  ecc_header='#define CONFIG_ECC_LOGGING 0\n')
            self.assertEqual(len(text.splitlines()) - len(output.splitlines()), count)
            if filename == "Private.exports":
                self.assertNotIn("_load_trust_cache\n", output)
                self.assertEqual(len(policy.PI_UNAVAILABLE_TRUST_EXPORTS), 8)
            else:
                self.assertNotIn("_pmap_iommu_init\n", output)
                self.assertIn("_pmap_cache_attributes\n", output)
                self.assertEqual(len(policy.PI_UNAVAILABLE_IOMMU_EXPORTS), 16)
                self.assertEqual(len(policy.PI_APPLE_DEVICE_EXPORTS), 30)
                self.assertNotIn("_sptm_gen3dart_init\n", output)
                self.assertEqual(len(policy.PI_UNAVAILABLE_UAT_EXPORTS), 19)
                self.assertNotIn("__ZTV26IOUnifiedAddressTranslator\n", output)
                self.assertIn("__ZN24IOBufferMemoryDescriptor18initWithGuardPagesEP4taskjy\n", output)
        with self.assertRaises(ValueError):
            policy.apply_reviewed_policy("", filename="unknown.exports",
                                          config_text=config, ecc_header="")

    def test_generated_feature_reader_rejects_ambiguous_config(self):
        config = 'export CONFIG_DEFINES = -DDEVELOPMENT -DCONFIG_RPI5_BRINGUP -DSKYWALK -DOTHER="a b"\n'
        ecc = '#define CONFIG_ECC_LOGGING 0\n'
        features = policy.generated_features(config, ecc)
        self.assertTrue(features["SKYWALK"])
        self.assertFalse(features["FS_COMPRESSION"])
        self.assertFalse(features["CONFIG_ECC_LOGGING"])
        for invalid in ("", config + config, config.replace("-DSKYWALK", "-DSKYWALK=2"),
                        config.replace("-DDEVELOPMENT", ""), config + "export CONFIG_DEFINES =\n"):
            with self.assertRaises(ValueError):
                policy.generated_features(invalid, ecc)
        with self.assertRaises(ValueError):
            policy.generated_features(config, "")

    def test_diagnostic_policy_requires_explicit_feature_evidence(self):
        root = Path(__file__).resolve().parents[3]
        for filename in ("Private.exports", "Private.arm64.exports"):
            text = (root / "config" / filename).read_text()
            features = {f: False for f in policy.DIAGNOSTIC_EXPORTS}
            args = dict(filename=filename, board="BCM2712", development=True)
            output = policy.diagnostic_policy(text, features=features, **args)
            expected = set().union(*(exports for source, exports in
                                    policy.DIAGNOSTIC_EXPORTS.values() if source == filename))
            self.assertEqual(set(text.splitlines()) - set(output.splitlines()), expected)
            enabled = {f: True for f in features}
            self.assertEqual(policy.diagnostic_policy(text, features=enabled, **args), text)
            with self.assertRaises(ValueError):
                policy.diagnostic_policy(text, features={}, **args)
            with self.assertRaises(ValueError):
                policy.diagnostic_policy(text, features={f: 0 for f in features}, **args)

    def test_skywalk_policy_preserves_other_network_exports(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "config/Private.exports").read_text()
        args = dict(board="BCM2712", development=True, skywalk=False)
        output = policy.skywalk_policy(text, **args)
        removed = set(text.splitlines()) - set(output.splitlines())
        self.assertEqual(removed, policy.SKYWALK_EXPORTS)
        self.assertEqual(len(removed), 4)
        self.assertEqual(policy.skywalk_policy(text, **{**args, "skywalk": True}), text)
        self.assertEqual(policy.skywalk_policy(text, **{**args, "board": "T8103"}), text)
        combined = policy.compression_policy(output, board="BCM2712",
                                             development=True, fs_compression=False)
        self.assertEqual(set(text.splitlines()) - set(combined.splitlines()),
                         policy.SKYWALK_EXPORTS | policy.COMPRESSION_EXPORTS)
        with self.assertRaises(ValueError):
            policy.skywalk_policy(text, **{**args, "development": False})
        with self.assertRaises(ValueError):
            policy.skywalk_policy(text.replace("_nxioctl_kernel\n", ""), **args)

    def test_compression_policy_is_explicit_and_preserves_other_exports(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "config/Private.exports").read_text()
        args = dict(board="BCM2712", development=True, fs_compression=False)
        output = policy.compression_policy(text, **args)
        removed = [line for line in text.splitlines() if line not in output.splitlines()]
        self.assertEqual(set(removed), policy.COMPRESSION_EXPORTS)
        self.assertEqual(len(removed), 27)
        self.assertIn("_load_trust_cache\n", output)
        self.assertEqual(policy.compression_policy(text, **{**args, "board": "T8103"}), text)
        self.assertEqual(policy.compression_policy(text, **{**args, "fs_compression": True}), text)
        for changed in (text.replace("_decmpfs_init\n", ""), text + "\n_decmpfs_init\n"):
            with self.assertRaises(ValueError):
                policy.compression_policy(changed, **args)
        with self.assertRaises(ValueError):
            policy.compression_policy(text, **{**args, "development": False})

    @unittest.skipUnless(platform.system() == "Darwin", "Requires Xcode tools")
    def test_pi_disabled_compression_does_not_export_zero_aliases(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "bsd/kern/decmpfs.c").read_text()
        disabled = text[text.index("#if !FS_COMPRESSION"):text.index("#else /* FS_COMPRESSION */")]
        disabled += "\n#endif\n"
        with tempfile.TemporaryDirectory() as directory:
            obj = Path(directory) / "compression.o"
            for pi in (False, True):
                flags = ["-DARM64_BOARD_CONFIG_BCM2712=1"] if pi else []
                subprocess.run(["xcrun", "clang", "-x", "c", "-c", "-",
                                "-DFS_COMPRESSION=0", *flags, "-o", str(obj)],
                               input=disabled, text=True, capture_output=True, check=True)
                result = subprocess.run(["xcrun", "nm", "-g", str(obj)],
                                        text=True, capture_output=True, check=True)
                zeros = module.absolute_zero_symbols(result.stdout)
                if pi:
                    self.assertEqual(zeros, [])
                    self.assertNotIn("_decmpfs_init", result.stdout)
                else:
                    self.assertEqual(len(zeros), 24)
                    self.assertIn("_decmpfs_init", zeros)

    def test_absolute_zero_is_not_a_callable_provider(self):
        output = ("0000000000000000 A _fake_function\n"
                  "0000000000000000 T _text_at_zero\n"
                  "0000000000000001 A _constant\n"
                  "                 U _undefined\n")
        self.assertEqual(module.absolute_zero_symbols(output), ["_fake_function"])

    def test_sdk_platform_does_not_select_pi_kpi_platform(self):
        root = Path(__file__).resolve().parents[3]
        text = (root / "config/Makefile").read_text()
        start = text.index("ifeq ($(CURRENT_MACHINE_CONFIG),BCM2712)")
        end = text.index("EXPORTS_FILES +=", start)
        fragment = text[start:end]
        for board, expected in (("BCM2712", "BCM2712"), ("T8103", "MacOSX")):
            makefile = ("CURRENT_MACHINE_CONFIG := " + board + "\n"
                        "PLATFORM := MacOSX\nEXPORT_SOURCE_ARCH_CONFIG_LC := arm64\n"
                        "SYMBOL_COMPONENT_LIST := Private Unsupported\n"
                        f"SOURCE := {root}/config\n" + fragment +
                        '\n.PHONY: probe\nprobe:\n\t@echo $(EXPORT_SOURCE_PLATFORM)\n'
                        '\t@echo $(EXPORTS_FILES)\n')
            result = subprocess.run(["make", "-f", "-", "probe"], input=makefile,
                                    text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.splitlines()[0], expected)
            self.assertIn("Private.arm64.exports", result.stdout)
            self.assertEqual("Private.arm64.MacOSX.exports" in result.stdout,
                             board != "BCM2712")

    def test_removed_export_input_rebuilds_symbolset_metadata(self):
        root = Path(__file__).resolve().parents[3]
        source = (root / 'config/Makefile').read_text()
        self.assertIn('RPI5_EXPORT_RULE_DEPS := $(SOURCE)/Makefile', source)
        start = source.index('define symbol_set_plist_template')
        fragment = source[start:source.index('endef', start) + len('endef')]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            info = path / 'System/Test.kext/Info.plist'
            info.parent.mkdir(parents=True)
            info.write_bytes(plistlib.dumps({
                'CFBundleIdentifier': 'test.symbols', 'CFBundleVersion': '1',
                'OSBundleCompatibleVersion': '1'}))
            base = path / 'base.exports'
            removed = path / 'removed.exports'
            base.write_text('_base\n')
            removed.write_text('_removed\n')
            rules = path / 'selection.mk'
            rules.write_text(f'Test_EXPORTS := {base} {removed}\n')
            makefile = path / 'Makefile'
            makefile.write_text(
                f'TARGET := {path}\nSOURCE := {root}/config\n'
                f'RPI5_EXPORT_RULE_DEPS := {rules}\nPLUTIL := plutil\n'
                'KEXT_PLIST_LIST := System/Test.kext/Info.plist\n'
                'LOG_SYMBOLSETPLIST := true\n'
                f'include {rules}\n' + fragment +
                '\n$(eval $(call symbol_set_plist_template,Test))\n')
            # Run the real generator and validate its plist output.
            output = path / 'Test.symbolset.plist'
            command = ['make', '-f', str(makefile), str(output)]
            subprocess.run(command, check=True, capture_output=True)
            self.assertIn('_removed', str(plistlib.loads(output.read_bytes())))
            rules.write_text(f'Test_EXPORTS := {base}\n')
            old = rules.stat().st_mtime - 5
            os.utime(output, (old, old))
            subprocess.run(command, check=True, capture_output=True)
            symbols = plistlib.loads(output.read_bytes())['Symbols']
            self.assertEqual(symbols, [{'SymbolName': '_base'}])

    def test_aliases_patterns_and_source_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.exports"
            path.write_text("# comment\n_present\n_public: _implementation\n"
                            "_family*\n_absent\n_missing_alias:_absent_target\n")
            before = path.read_bytes()
            missing = module.audit([path], {"_present", "_implementation", "_family_one"})
            self.assertEqual([r["line"] for r in missing], [5, 6])
            self.assertEqual(missing[1]["provider"], "_absent_target")
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_syntax_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.exports"
            for text in ("_a:_b:_c", "_a:", ":_b", "_a _b"):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    module.audit([path], {"_a", "_b"})
