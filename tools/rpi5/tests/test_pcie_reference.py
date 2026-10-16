# SPDX-License-Identifier: BSD-2-Clause
"""Allowlist, stable-boot and native topology/resource checks; no Pi access."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from tools.rpi5 import pcie_reference_core as core
from tools.rpi5 import capture_pcie_reference as controller
from tools.rpi5.fdt import parse
from tools.rpi5.tests.test_pcie_fdt import _synthetic_tree

ROOT = Path(__file__).resolve().parents[3]


def properties():
    nodes = {}

    def walk(node, path):
        nodes[path] = node["properties"]
        for child in node["children"]:
            walk(child, path.rstrip("/") + "/" + child["name"])

    walk(_synthetic_tree(), "/")

    def read(node, name):
        return nodes[node].get(name)

    return core.collect_properties(read)


def reference():
    identity = {"root": core.ROOT_IDENTITY, "hostname": "kamidana",
                "boot_id": "36ac234c-2a31-4b30-bb5d-de87fa5bd8e2", "kernel": "synthetic-test"}
    snapshot = {"of_properties_hex": properties(),
                "pci_config_first64_hex": (
                    "e41d010006041000000000020000000000004100000000000000400000000000"
                    "000000000000000000000000000000000000000040000000000000002c010000"),
                "resource": (
                    "0x0000001f00410000 0x0000001f00413fff 0x0000000000040200\n"
                    "0x0000001f00000000 0x0000001f003fffff 0x0000000000040200\n"
                    "0x0000001f00400000 0x0000001f0040ffff 0x0000000000040200\n" +
                    "\n".join(["0x0 0x0 0x0"] * 4))}
    return {"schema_version": 1, "identity_before": identity,
            "identity_after": copy.deepcopy(identity), "first": snapshot,
            "second": copy.deepcopy(snapshot), "pci_bdf": "0002:01:00.0",
            "pci_config_writes": 0, "mmio_accesses": 0, "sd_actions": 0,
            "network_changes": 0, "reboots": 0}


class PCIeReferenceTests(unittest.TestCase):
    def test_only_exact_allowlisted_properties_are_requested(self):
        requested = []

        def read(node, name):
            requested.append((node, name))
            raise FileNotFoundError

        captured = core.collect_properties(read)
        expected = [(node, name) for node, names in core.PROPERTIES.items() for name in names]
        self.assertEqual(requested, expected)
        self.assertEqual(len(captured), 12)
        for node, fields in captured.items():
            self.assertNotIn("chosen", node)
            self.assertTrue(all(value is None for value in fields.values()))
            self.assertTrue(set(fields).isdisjoint({"rng-seed", "kaslr-seed", "serial-number",
                                                   "mac-address", "local-mac-address"}))
        self.assertIn("interrupts-extended", captured[core.GEM])
        self.assertIn("interrupt-parent", captured["/axi"])

    def test_encoder_roundtrip_and_fail_closed_allowlist(self):
        values = properties()
        parsed = parse(core.encode_properties(values))
        self.assertEqual(parsed["reservations"], [])
        self.assertEqual(parsed["root"]["properties"]["compatible"],
                         b"raspberrypi,5-model-b\0brcm,bcm2712\0")
        invalid = []
        missing = copy.deepcopy(values); del missing["/axi"]; invalid.append(missing)
        secret = copy.deepcopy(values); secret["/chosen"] = {}; invalid.append(secret)
        extra = copy.deepcopy(values); extra["/"]["rng-seed"] = "00"; invalid.append(extra)
        missing = copy.deepcopy(values); del missing["/"]["status"]; invalid.append(missing)
        for bad_hex in ("0", "zz", "0A", "00" * 4097, False):
            bad = copy.deepcopy(values); bad["/"]["status"] = bad_hex; invalid.append(bad)
        for bad in invalid:
            with self.assertRaises(ValueError):
                core.encode_properties(bad)
        with self.assertRaises(ValueError):
            core.collect_properties(lambda node, name: bytes(4097))
        with self.assertRaises(PermissionError):
            core.collect_properties(lambda node, name: (_ for _ in ()).throw(PermissionError()))

    def test_capture_identity_resources_and_change_rejection(self):
        good = reference()
        self.assertEqual(core.validate_capture(good),
                         {"pci_base": 0, "size": 0x400000, "cpu_base": 0x1f00000000})
        mutations = []
        bad = copy.deepcopy(good); bad["identity_after"]["boot_id"] = "other"; mutations.append(bad)
        bad = copy.deepcopy(good); bad["identity_before"]["root"] = "/dev/mmcblk0p2"; mutations.append(bad)
        bad = copy.deepcopy(good); bad["second"]["of_properties_hex"]["/"]["status"] = "00"; mutations.append(bad)
        for name in ("sd_actions", "mmio_accesses", "pci_config_writes", "network_changes", "reboots"):
            bad = copy.deepcopy(good); bad[name] = 1; mutations.append(bad)
            bad = copy.deepcopy(good); bad[name] = False; mutations.append(bad)
        for header in ("00" * 64, good["first"]["pci_config_first64_hex"][:-2],
                       good["first"]["pci_config_first64_hex"][:8] + "0000" +
                       good["first"]["pci_config_first64_hex"][12:]):
            bad = copy.deepcopy(good)
            bad["first"]["pci_config_first64_hex"] = bad["second"]["pci_config_first64_hex"] = header
            mutations.append(bad)
        for resource in ("0x0 0x0 0x0", good["first"]["resource"].replace("0x0000000000040200", "0x0")):
            bad = copy.deepcopy(good)
            bad["first"]["resource"] = bad["second"]["resource"] = resource
            mutations.append(bad)
        for bad in mutations:
            with self.assertRaises(ValueError):
                core.validate_capture(bad)

    def test_native_filtered_topology_and_resource_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            binary = work / "pcie-reference"
            subprocess.run([
                "xcrun", "clang", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-fsanitize=address,undefined", "-I", str(ROOT / "loader/rpi5"),
                str(ROOT / "tools/rpi5/pcie_reference_host.c"),
                *[str(ROOT / "loader/rpi5" / name) for name in
                  ("fdt.c", "fdt_reg.c", "pcie_fdt.c", "pcie_resource_plan.c")],
                "-o", str(binary),
            ], check=True, timeout=60)
            path = work / "filtered.dtb"
            path.write_bytes(core.encode_properties(properties()))
            good = subprocess.run([str(binary), str(path), "0", "0x400000", "0x1f00000000"],
                                  capture_output=True, text=True, timeout=30)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["gem_cpu_start"], 0x1f00100000)
            wrong = subprocess.run([str(binary), str(path), "0", "0x400000", "0x1f00400000"],
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(wrong.returncode, 4)
            for node, name, value in ((core.GEM, "interrupts-extended", "00000003"),
                                       ("/axi", "interrupt-parent", "00000001"),
                                       (core.BRIDGE, "status", b"disabled\0".hex())):
                bad = properties(); bad[node][name] = value
                path.write_bytes(core.encode_properties(bad))
                rejected = subprocess.run([str(binary), str(path), "0", "0x400000", "0x1f00000000"],
                                          capture_output=True, timeout=30)
                self.assertEqual(rejected.returncode, 3)

    def test_default_plan_never_contacts_ssh_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "new-plan"
            command = ["python3", str(ROOT / "tools/rpi5/capture_pcie_reference.py"),
                       "--output-dir", str(output)]
            first = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertTrue(json.loads(first.stdout)["plan_only"])
            self.assertEqual([path.name for path in output.iterdir()], ["plan.json"])
            digest = hashlib.sha256((output / "plan.json").read_bytes()).hexdigest()
            second = subprocess.run(command, capture_output=True, timeout=30)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(hashlib.sha256((output / "plan.json").read_bytes()).hexdigest(), digest)

    def test_source_drift_prevents_ssh_and_unknown_timeout_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "drift"
            with mock.patch("sys.argv", ["capture", "--execute", "--output-dir", str(output)]), \
                    mock.patch.object(controller, "hashes", side_effect=[{"source": "before"}, {"source": "after"}]), \
                    mock.patch.object(controller.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "source changed before SSH"):
                    controller.main()
            self.assertEqual(run.call_count, 1)  # Native compile only.
            self.assertFalse(json.loads((output / "result.json").read_text())["ssh_attempted"])

            output = Path(directory) / "timeout"
            timeout = subprocess.TimeoutExpired("ssh", 45, output=b"partial-reference")
            with mock.patch("sys.argv", ["capture", "--execute", "--output-dir", str(output)]), \
                    mock.patch.object(controller.subprocess, "run", side_effect=[
                        subprocess.CompletedProcess([], 0), timeout,
                    ]) as run:
                with self.assertRaises(subprocess.TimeoutExpired):
                    controller.main()
            self.assertEqual(run.call_count, 2)  # Compile, one SSH; no retry.
            command = run.call_args_list[1].args[0]
            self.assertEqual(command[0], "ssh")
            self.assertEqual(command[-2:], [core.HOST, "sudo -n python3 -"])
            result = json.loads((output / "result.json").read_text())
            self.assertFalse(result["passed"])
            self.assertEqual(result["remote_outcome"], "unknown")
            self.assertEqual((output / "partial.stdout").read_bytes(), b"partial-reference")


if __name__ == "__main__":
    unittest.main()
