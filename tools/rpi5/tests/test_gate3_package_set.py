# SPDX-License-Identifier: BSD-2-Clause
"""Standalone package mixing must fail before any SD staging."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "check_gate3_package_set.py"
SPEC = importlib.util.spec_from_file_location("gate3_package_set", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Gate3PackageSetTests(unittest.TestCase):
    def fixture(self, root):
        kernel = root / "kernel"
        init = root / "init"
        kernel.write_bytes(b"kernel")
        init.write_bytes(b"init")
        packages = {}
        for role, flag in MODULE.ROLES.items():
            directory = root / role
            directory.mkdir()
            image = directory / "probe.bin"
            image.write_bytes(role.encode())
            manifest = {name: name == flag for name in MODULE.EXCLUSIVE}
            manifest.update({
                "xnu_transfer_enabled": True, "gate3_cpu_on_all": True,
                "gate3_register_cpus": False, "gate3_register_boot_cpu": False,
                "gate3_cpu_on_1": False,
                "gate3_xnupost_index": 0, "gate3_xnupost_config": "",
                "gate3_qualification_config": "", "gate3_soak_seconds": 0,
                "embedded_kernel": {"sha256": MODULE.sha256(kernel)},
                "embedded_init": {"sha256": MODULE.sha256(init)},
                "sha256": {str(image): MODULE.sha256(image)},
            })
            (directory / "manifest.json").write_text(json.dumps(manifest))
            packages[role] = directory
        return packages, kernel, init

    def test_coherent_set_passes(self):
        with tempfile.TemporaryDirectory() as temporary:
            packages, kernel, init = self.fixture(Path(temporary))
            self.assertTrue(MODULE.inspect(packages, kernel, init)["package_set_pass"])

    def test_mixed_kernel_wrong_flag_and_modified_image_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            packages, kernel, init = self.fixture(Path(temporary))
            directory = packages["user_tlb"]
            manifest_path = directory / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["embedded_kernel"]["sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(manifest))
            self.assertFalse(MODULE.inspect(packages, kernel, init)["package_set_pass"])
            manifest["embedded_kernel"]["sha256"] = MODULE.sha256(kernel)
            manifest["gate3_tlb_trial"] = True
            manifest_path.write_text(json.dumps(manifest))
            self.assertFalse(MODULE.inspect(packages, kernel, init)["package_set_pass"])
            manifest["gate3_tlb_trial"] = False
            manifest_path.write_text(json.dumps(manifest))
            (directory / "probe.bin").write_bytes(b"changed")
            self.assertFalse(MODULE.inspect(packages, kernel, init)["package_set_pass"])

    def test_missing_selector_and_wrong_manifest_path_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            packages, kernel, init = self.fixture(Path(temporary))
            manifest_path = packages["inventory"] / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            del manifest["gate3_register_cpus"]
            manifest_path.write_text(json.dumps(manifest))
            self.assertFalse(MODULE.inspect(packages, kernel, init)["package_set_pass"])
            manifest["gate3_register_cpus"] = False
            digest = next(iter(manifest["sha256"].values()))
            manifest["sha256"] = {"/tmp/unrelated/probe.bin": digest}
            manifest_path.write_text(json.dumps(manifest))
            self.assertFalse(MODULE.inspect(packages, kernel, init)["package_set_pass"])


if __name__ == "__main__":
    unittest.main()
