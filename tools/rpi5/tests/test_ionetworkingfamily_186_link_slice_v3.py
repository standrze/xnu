# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/rpi5/build_ionetworkingfamily_186_link_slice_v3.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ionet_slice_v3", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class IONetworkingFamilyLinkSliceV3Tests(unittest.TestCase):
    def test_manifest_has_exact_twelve_original_units(self):
        module = load_module()
        manifest = json.loads(module.prior.PIN.read_text())
        self.assertEqual(tuple(manifest["implementation_sources"]), module.ALL_UNITS)
        self.assertEqual(len(module.ALL_UNITS), 12)

    def test_compatibility_preinclude_is_linkage_only(self):
        module = load_module()
        text = module.COMPAT_PREINCLUDE
        self.assertIn("#include <sys/mbuf.h>", text)
        self.assertIn("#include <net/if.h>", text)
        self.assertNotIn("#include <net/bpf.h>", text)
        self.assertIn("#define _IP_VHL", text)
        self.assertNotIn("extern \"C\"", text.split("*/", 1)[1])

    def test_command_force_includes_generated_compatibility_header(self):
        module = load_module()
        command = module.command_for(
            ["clang++", "old.cpp", "-c", "-o", "old.o"], "old.cpp",
            Path("new.cpp"), Path("new.o"), Path("include"), Path("compat.h"))
        self.assertEqual(command[command.index("-include") + 1], "compat.h")
        self.assertIn("-Wno-shadow-field", command)
        self.assertIn("-Wno-gnu-variable-sized-type-not-at-end", command)
        self.assertNotIn("-Wl,-kext", command)

    def test_kernel_link_is_distinct_and_default_off(self):
        module = load_module()
        source = SCRIPT.read_text()
        self.assertIn('kernel.ionetworkingfamily186.unstripped', source)
        self.assertIn('"production_file_list_modified": False', source)
        self.assertIn('"service_catalogue_modified": False', source)
        self.assertNotIn("rpi5_gem_network_adapter", source)

    def test_kernel_link_pins_existing_baseline_provider(self):
        module = load_module()
        self.assertEqual(module.prior.sha(module.BASE_BUILD_RECEIPT),
                         module.BASE_BUILD_RECEIPT_SHA256)
        receipt = json.loads(module.BASE_BUILD_RECEIPT.read_text())
        providers = [value.split("=", 1)[1] for value in receipt["command"]
                     if value.startswith("RPI5_CRYPTO_CANDIDATE_OBJECT=")]
        self.assertEqual(len(providers), 1)
        self.assertEqual(module.prior.sha(Path(providers[0])),
                         module.CRYPTO_PROVIDER_SHA256)


if __name__ == "__main__":
    unittest.main()
