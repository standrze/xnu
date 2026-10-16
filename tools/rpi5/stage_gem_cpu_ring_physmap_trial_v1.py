#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Catalog524 to physmap CPU-owned rings and exact automatic restoration."""
import hashlib
import json
from pathlib import Path
import types

_parent = Path(__file__).with_name("stage_gem_cpu_ring_retry_trial_v2.py")
_PARENT_SHA = "32bca55bffed390617fef31706ef66e0fd7f9ce0ae06ed02d283aca081fc980a"
_raw_parent = _parent.read_bytes()
if hashlib.sha256(_raw_parent).hexdigest() != _PARENT_SHA:
    raise ValueError("Frozen CPU-ring retry controller changed")
_text = _raw_parent.decode()
for _old, _new in (
    ("stage_gem_cpu_ring_retry_trial_v2.py", "stage_gem_cpu_ring_physmap_trial_v1.py"),
    ("serial_gem_cpu_ring_retry_trial_v2.py", "serial_gem_cpu_ring_physmap_trial_v1.py"),
    ("gem_cpu_ring_retry_evidence_v2.py", "gem_cpu_ring_physmap_evidence_v1.py"),
    ("arm_gem_cpu_ring_retry_reboot_v2.py", "arm_gem_cpu_ring_physmap_reboot_v1.py"),
    ("serial_gem_cpu_ring_retry_trial_v2", "serial_gem_cpu_ring_physmap_trial_v1"),
    ("gem_cpu_ring_retry_evidence_v2", "gem_cpu_ring_physmap_evidence_v1"),
    ("arm_gem_cpu_ring_retry_reboot_v2", "arm_gem_cpu_ring_physmap_reboot_v1"),
    ("gem_cpu_ring_retry_media_v2", "gem_cpu_ring_physmap_media_v1"),
    ("gem_cpu_ring_retry_case_v1", "gem_cpu_ring_physmap_case_v1"),
    ("check_gem_cpu_ring_retry_trial", "check_gem_cpu_ring_physmap_transport_v1"),
    ("gem_cpu_ring_retry_serial", "gem_cpu_ring_physmap_serial_v1"),
    ("gem-cpu-ring-retry-successor-three-target-controller-v2", "gem-cpu-ring-physmap-three-target-controller-v1"),
    ("gem-cpu-ring-retry-successor-three-target-v2", "gem-cpu-ring-physmap-three-target-v1"),
    ("gem-cpu-ring-retry-successor-independent-return-v2", "gem-cpu-ring-physmap-independent-return-v1"),
    ("rpi5-gem-cpu-ring-retry-successor-three-target-chain-v2", "rpi5-gem-cpu-ring-physmap-three-target-chain-v1"),
    ("gem-cpu-ring-retry-successor", "gem-cpu-ring-physmap"),
    ("gem-cpu-ring-retry-fixed53", "gem-cpu-ring-physmap-fixed53-v1"),
    ("ring-only retry successor", "physmap-enabled CPU-owned-ring trial"),
):
    if _old not in _text:
        raise ValueError("Exact CPU-ring physmap controller boundary changed: " + _old)
    _text = _text.replace(_old, _new)
_parent_main = "if __name__=='__main__':raise SystemExit(main())"
if _text.count(_parent_main) != 2 or not _text.rstrip().endswith(_parent_main):
    raise ValueError("Frozen CPU-ring retry main boundary changed")
_text = _text.rsplit(_parent_main, 1)[0] + "if False:raise SystemExit(main())\n"
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())

from tools.rpi5 import stage_gem_physmap_mapping_trial_v5 as baseline_stage
from tools.rpi5 import check_gem_cpu_ring_physmap_trial as package_checker
from tools.rpi5 import check_gem_cpu_ring_physmap_transport_v1 as checker
from tools.rpi5 import gem_cpu_ring_physmap_case_v1 as case
from tools.rpi5 import gem_cpu_ring_physmap_media_v1 as engine
from tools.rpi5 import gem_cpu_ring_physmap_serial_v1 as protocol

PACKAGE = case.PACKAGE
MANIFEST_SHA = case.MANIFEST_SHA
IMAGE_SHA = case.IMAGE_SHA
TAG = case.TAG
REPORT = case.REPORT
REPORT_SHA = case.REPORT_SHA

BASELINE = ROOT / "build/rpi5/gem-physmap-mapping-v5-restored"
BASELINE_SEAL = "91a00c05d5bee963e87e316a4748eeee4e38be706a8f6c6432238f3047180c00"
BASELINE_PLAN = "0192c6a07d6947c41443aa24b18f1432a867c9f8c9676773a29e7b6a097e5058"
BASELINE_RESULT = "f379d91a3ebf20f3105b38a349980581e3c12bafab630c7503d690de7ad1d930"
BASELINE_BOOT = "2d237d96-a323-4df7-a8b4-ad9b4eb5f477"
BASELINE_CATALOG = 524
BASELINE_CATALOG_SHA = "5aa6a9e2f2c94090e6ded0dfa27129d26924f8ea98479f6aebb61e97d4d54c20"
MAPPING_REPORT_SHA = "fca45a8a3c17d9d5d7ef9acbf2d879c6c8adf351f82465d75727b5789ff8b5f6"
CONTROLLER = "gem-cpu-ring-physmap-three-target-controller-v1"
DESCRIPTOR = "gem-cpu-ring-physmap-fixed53-v1"

_physmap_generated_prepare_install = prepare_install
_SOURCE_EXPECTATIONS = None


def validate_mapping_prerequisite(report):
    return checker.validate_mapping_report(report)


def validate_baseline_context(accepted):
    result = accepted.get("result", {})
    publication = result.get("publication", {})
    files = publication.get("protected_files_sha256", {})
    if (publication.get("identity", {}).get("boot_id") != BASELINE_BOOT or
            len(result.get("next_catalog", [])) != BASELINE_CATALOG or
            result.get("next_catalog_sha256") != BASELINE_CATALOG_SHA or
            any(files.get(name) != value[1] for name, value in GOOD.items())):
        raise ValueError("Exact catalog524 normal triple restoration required")
    mapping = json.loads(case.MAPPING_REPORT.read_text())
    validate_mapping_prerequisite(mapping)
    return True


def baseline(directory, seal_sha, plan_sha):
    if (Path(directory).resolve(), seal_sha, plan_sha) != (BASELINE, BASELINE_SEAL, BASELINE_PLAN):
        raise ValueError("Exact catalog524 mapping restoration required")
    if sha(BASELINE / "result.json") != BASELINE_RESULT:
        raise ValueError("Catalog524 restoration result changed")
    accepted = baseline_stage.restoration(directory, seal_sha, plan_sha)
    validate_baseline_context(accepted)
    return accepted


def valid_report(report):
    if (case.FROZEN is not True or sha(case.REPORT) != case.REPORT_SHA or
            sha(case.MAPPING_REPORT) != MAPPING_REPORT_SHA):
        raise ValueError("Exact CPU-ring package/mapping receipts required")
    retained = json.loads(case.REPORT.read_text())
    if not engine.same(retained, package_checker.check(PACKAGE, MANIFEST_SHA)):
        raise ValueError("Retained CPU-ring package report differs")
    expected = checker.inspect(PACKAGE, MANIFEST_SHA)
    if not engine.same(report, expected):
        raise ValueError("Exact physmap CPU-ring admission report required")
    if (report.get("activation_authorized") is not False or
            report.get("zero_serial_transmit") is not True or
            any(report.get(name) is not False for name in
                ("bme", "queues", "dma", "irq", "packets", "tx"))):
        raise ValueError("CPU-ring transport activation boundary differs")
    return True


def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(name) != digest for name, digest in _SOURCE_EXPECTATIONS.items()):
            raise ValueError("CPU-ring physmap transport source changed after inventory")
        return dict(_SOURCE_EXPECTATIONS)
    names = (
        "stage_gem_cpu_ring_physmap_trial_v1.py",
        "serial_gem_cpu_ring_physmap_trial_v1.py",
        "gem_cpu_ring_physmap_evidence_v1.py",
        "arm_gem_cpu_ring_physmap_reboot_v1.py",
        "gem_cpu_ring_physmap_media_v1.py",
        "gem_cpu_ring_physmap_case_v1.py",
        "gem_cpu_ring_physmap_serial_v1.py",
        "check_gem_cpu_ring_physmap_transport_v1.py",
        "build_gem_cpu_ring_physmap_trial.py",
        "check_gem_cpu_ring_physmap_trial.py",
    )
    _SOURCE_EXPECTATIONS = (
        baseline_stage.source_pins() | engine.source_pins() |
        {str(_parent): _PARENT_SHA} |
        {str(ROOT / "tools/rpi5" / name): sha(ROOT / "tools/rpi5" / name) for name in names} |
        {
            str(CONFIG): engine.TRIAL_CONFIG_SHA,
            str(GOOD["config.txt"][0]): engine.ORIGINAL_CONFIG_SHA,
            str(case.REPORT): case.REPORT_SHA,
            str(case.MAPPING_REPORT): case.MAPPING_REPORT_SHA,
            str(PACKAGE / "manifest.json"): MANIFEST_SHA,
            str(PACKAGE / "probe.bin"): IMAGE_SHA,
            str(BASELINE / "result.json"): BASELINE_RESULT,
        }
    )
    if any(sha(name) != digest for name, digest in _SOURCE_EXPECTATIONS.items()):
        raise ValueError("CPU-ring physmap source inventory differs")
    return dict(_SOURCE_EXPECTATIONS)


def get_descriptor(kind):
    if kind != DESCRIPTOR or case.FROZEN is not True:
        raise ValueError("Fixed physmap CPU-ring case required")
    return {"hardware_allowed": True, "protocol": protocol, "record": {
        "package": str(PACKAGE),
        "package_manifest_sha256": MANIFEST_SHA,
        "marker": checker.inspect(PACKAGE, MANIFEST_SHA)["trial_marker"],
        "firmware_sha256": case.FIRMWARE_SHA,
        "mapping_report_sha256": MAPPING_REPORT_SHA,
        "activation_authorized": False,
    }}


def prepare_install(directory, prior_seal, prior_plan, boot):
    if boot != BASELINE_BOOT:
        raise ValueError("Exact current catalog524 Linux boot witness required")
    return _physmap_generated_prepare_install(directory, prior_seal, prior_plan, boot)


_scope = globals()
for _name in ("sealed_operation", "load_installation", "prepare_restore",
        "restoration", "dispatch", "launch", "replay", "main"):
    _fn = _scope[_name]
    if hasattr(_fn, "__code__"):
        _scope[_name] = types.FunctionType(_fn.__code__, _scope, argdefs=_fn.__defaults__)

if __name__ == "__main__":
    raise SystemExit(main())
