# SPDX-License-Identifier: BSD-2-Clause
"""V2 transport tests, including isolated execution of the remote program."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.rpi5 import stage_gem_cpu_ring_physmap_trial_v2 as stage


class CPURingPhysmapTransportV2Tests(unittest.TestCase):
    def report(self):
        return stage.checker.inspect(stage.PACKAGE, stage.MANIFEST_SHA)

    def test_exact_v2_namespace_package_and_activation_boundary(self):
        report = self.report()
        self.assertTrue(stage.valid_report(report))
        self.assertEqual(stage.CONTROLLER, "gem-cpu-ring-physmap-three-target-controller-v2")
        self.assertEqual(stage.DESCRIPTOR, "gem-cpu-ring-physmap-fixed53-v2")
        self.assertEqual(stage.engine.TRIAL, "gem-cpu-ring-physmap-triple-trial-v2")
        self.assertTrue(report["self_contained_remote_transport_required"])
        self.assertTrue(report["zero_serial_transmit"])
        self.assertFalse(report["activation_authorized"])
        self.assertTrue(all(report[name] is False for name in
            ("bme", "queues", "dma", "irq", "packets", "tx")))
        pins = stage.source_pins()
        self.assertEqual(pins[str(stage.PACKAGE / "manifest.json")], stage.MANIFEST_SHA)
        self.assertEqual(pins[str(stage.case.MAPPING_REPORT)], stage.MAPPING_REPORT_SHA)
        direct = {
            stage.ROOT / "tools/rpi5/gem_cpu_ring_physmap_media_v2.py":
                hashlib.sha256((stage.ROOT / "tools/rpi5/gem_cpu_ring_physmap_media_v2.py").read_bytes()).hexdigest(),
            stage.ROOT / "tools/rpi5/gem_cpu_ring_retry_media_v2.py":
                "058a8870c22634a119e50d9ef9de7dde1d79b07d3f978f6204a9c9038e5669d7",
            stage.ROOT / "tools/rpi5/gem_cpu_batch_media_v1.py":
                "51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b",
        }
        for path, digest in direct.items():
            self.assertEqual(pins[str(path)], digest)

    def test_package_report_activation_and_ancestry_mutations(self):
        with self.assertRaises(ValueError):
            stage.checker.inspect(stage.ROOT / "build/rpi5/gem-cpu-ring-retry-trial-20261014-v7",
                stage.MANIFEST_SHA)
        report = self.report()
        for name, value in (("package", "/wrong/package"),
                ("mapping_report_sha256", "0" * 64),
                ("activation_authorized", True), ("dma", True), ("tx", True)):
            changed = copy.deepcopy(report); changed[name] = value
            with self.assertRaises(ValueError):
                stage.valid_report(changed)
        accepted = stage.baseline(stage.BASELINE, stage.BASELINE_SEAL, stage.BASELINE_PLAN)
        for mutation in ("catalog", "boot", "triple"):
            changed = copy.deepcopy(accepted)
            if mutation == "catalog":
                changed["result"]["next_catalog_sha256"] = "0" * 64
            elif mutation == "boot":
                changed["result"]["publication"]["identity"]["boot_id"] = "0" * 36
            else:
                changed["result"]["publication"]["protected_files_sha256"]["probe.bin"] = "0" * 64
            with self.assertRaises(ValueError):
                stage.validate_baseline_context(changed)

    def test_failed_v1_publish_evidence_is_retained(self):
        failed = stage.ROOT / "build/rpi5/gem-cpu-ring-physmap-v1-installed"
        stderr = failed / "remote.stderr"
        outcome = failed / "outcome-unknown.json"
        self.assertEqual(hashlib.sha256(stderr.read_bytes()).hexdigest(),
            "aef0b5e11b258ca0311538d6484b6978dfade31e4211165f3dbf78a78f1b584f")
        self.assertIn("gem_cpu_ring_retry_media_v2.py", stderr.read_text())
        self.assertIn("FileNotFoundError", stderr.read_text())
        self.assertTrue(outcome.is_file())
        self.assertFalse((failed / "result.json").exists())
        self.assertFalse((failed / "completion.json").exists())

    def test_generated_remote_executes_without_any_mac_path_read(self):
        prepared = stage.ROOT / "build/rpi5/gem-cpu-ring-physmap-v2-prepared-r6"
        checkpoint = json.loads((prepared / "checkpoint.json").read_text())
        pin = stage.seals.digest(checkpoint)
        self.assertEqual(pin, "304e3a6b4360b8e4452959b1915a4d573bfe5ad65846e08044588e931e44e27a")
        base = checkpoint["payload"]["media_plan"]
        plan, plan_sha = stage.engine.plan_from_seal(checkpoint, pin, stage.engine.TRIAL,
            "55" * 16, "/home/sandrzej/xnu-cpu-ring-physmap-v2-isolated", base)
        source = stage.engine.remote_source(checkpoint, pin, plan, plan_sha)
        immediate = "gem_cpu_ring_physmap_media_v2._embedded_retry_source="
        base_assignment = "gem_cpu_ring_physmap_media_v2._embedded_parent_source="
        source_rows = source.splitlines()
        self.assertEqual(sum(row.startswith(immediate) for row in source_rows), 1)
        self.assertEqual(sum(row.startswith(base_assignment) for row in source_rows), 1)
        lines = source.splitlines()
        self.assertTrue(lines[-1].startswith(
            "print(json.dumps(gem_cpu_ring_physmap_media_v2.execute("))
        lines[-1] = ("gem_cpu_ring_physmap_media_v2.validate_plan(PLAN);"
            "print(json.dumps({'status':'remote-modules-loaded'}))")
        guard = """import builtins, io, os, pathlib, sys
_repo = '/Users/stephen/Documents/ChatGPT/xnu'
_original_read_bytes = pathlib.Path.read_bytes
_original_read_text = pathlib.Path.read_text
_original_builtin_open = builtins.open
_original_io_open = io.open
_original_os_open = os.open
_original_stat = os.stat
_original_lstat = os.lstat
_original_scandir = os.scandir
_original_listdir = os.listdir
_original_readlink = os.readlink
def _reject(value):
    try: value = os.fspath(value)
    except TypeError: return
    if isinstance(value, bytes): value = os.fsdecode(value)
    if isinstance(value, str) and (value == _repo or value.startswith(_repo + '/')):
        raise AssertionError('Repository path access: ' + value)
def _audit(event, args):
    if event in ('open', 'os.stat', 'os.lstat', 'os.scandir', 'os.listdir',
            'os.readlink', 'os.mkdir', 'os.remove', 'os.rename', 'os.rmdir',
            'os.link', 'os.symlink'):
        for value in args: _reject(value)
sys.addaudithook(_audit)
def _guard_bytes(self):
    _reject(self)
    return _original_read_bytes(self)
def _guard_text(self, *args, **kwargs):
    _reject(self)
    return _original_read_text(self, *args, **kwargs)
def _builtin_open(path, *args, **kwargs):
    _reject(path); return _original_builtin_open(path, *args, **kwargs)
def _io_open(path, *args, **kwargs):
    _reject(path); return _original_io_open(path, *args, **kwargs)
def _os_open(path, *args, **kwargs):
    _reject(path); return _original_os_open(path, *args, **kwargs)
def _stat(path, *args, **kwargs):
    _reject(path); return _original_stat(path, *args, **kwargs)
def _lstat(path, *args, **kwargs):
    _reject(path); return _original_lstat(path, *args, **kwargs)
def _scandir(path='.'):
    _reject(path); return _original_scandir(path)
def _listdir(path='.'):
    _reject(path); return _original_listdir(path)
def _readlink(path, *args, **kwargs):
    _reject(path); return _original_readlink(path, *args, **kwargs)
pathlib.Path.read_bytes = _guard_bytes
pathlib.Path.read_text = _guard_text
builtins.open = _builtin_open
io.open = _io_open
os.open = _os_open
os.stat = _stat
os.lstat = _lstat
os.scandir = _scandir
os.listdir = _listdir
os.readlink = _readlink
"""
        safe_source = guard + "\n".join(lines) + "\n"
        with tempfile.TemporaryDirectory(prefix="cpu-ring-physmap-remote-v2-") as directory:
            before = tuple(Path(directory).iterdir())
            completed = subprocess.run([sys.executable, "-I", "-"],
                input=safe_source, text=True, capture_output=True,
                cwd=directory, timeout=90, env={"PATH": os.environ.get("PATH", "")})
            after = tuple(Path(directory).iterdir())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {"status": "remote-modules-loaded"})
        self.assertEqual(before, after)

        # Both derivation parents are necessary and independently byte
        # authenticated.  Removal or one-byte corruption must fail before any
        # publisher operation can execute.
        validated_rows = list(lines)
        def removed_assignment(token):
            candidate = [row for row in validated_rows if not row.startswith(token)]
            self.assertEqual(len(candidate), len(validated_rows) - 1)
            return "\n".join(candidate) + "\n"
        def corrupted_assignment(token):
            candidate = list(validated_rows)
            indexes = [index for index, row in enumerate(candidate)
                if row.startswith(token)]
            self.assertEqual(len(indexes), 1)
            index = indexes[0]
            self.assertIn("BSD-2-Clause", candidate[index])
            candidate[index] = candidate[index].replace(
                "BSD-2-Clause", "BSD-2-Clausf", 1)
            return "\n".join(candidate) + "\n"
        mutation_sources = tuple(guard + candidate for candidate in (
            removed_assignment(immediate),
            removed_assignment(base_assignment),
            corrupted_assignment(immediate),
            corrupted_assignment(base_assignment),
        ))
        for candidate in mutation_sources:
            with tempfile.TemporaryDirectory(prefix="cpu-ring-physmap-remote-v2-mut-") as directory:
                before = tuple(Path(directory).iterdir())
                rejected = subprocess.run([sys.executable, "-I", "-"], input=candidate,
                    text=True, capture_output=True, cwd=directory, timeout=90,
                    env={"PATH": os.environ.get("PATH", "")})
                after = tuple(Path(directory).iterdir())
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
