# SPDX-License-Identifier: BSD-2-Clause
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "tools/rpi5/build_ionetworkingfamily_186_link_slice.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ionet_slice", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class IONetworkingFamilyLinkSliceTests(unittest.TestCase):
    def test_manifest_covers_every_implementation_unit(self):
        module = load_module()
        manifest = json.loads(module.PIN.read_text())
        self.assertEqual(
            set(manifest["implementation_sources"]),
            set(module.BUILDABLE) | set(module.BLOCKED),
        )
        self.assertEqual(len(module.BUILDABLE), 9)
        self.assertEqual(len(module.BLOCKED), 3)
        self.assertFalse(manifest["whole_family_compatibility_proven"])

    def test_command_is_default_off_compile_only(self):
        module = load_module()
        command = module.command_for(
            ["clang++", "old.cpp", "-c", "-o", "old.o"],
            "old.cpp", Path("new.cpp"), Path("new.o"), Path("headers"),
        )
        self.assertIn("-c", command)
        self.assertNotIn("old.cpp", command)
        self.assertNotIn("old.o", command)
        self.assertNotIn("-Wl,-kext", command)
        self.assertNotIn("rpi5_gem_network_adapter", " ".join(command))

    def test_source_hash_mismatch_is_detectable(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "IONetworkData.cpp"
            path.write_text("changed\n")
            self.assertNotEqual(
                module.sha(path),
                json.loads(module.PIN.read_text())["implementation_sources"][path.name],
            )


if __name__ == "__main__":
    unittest.main()
