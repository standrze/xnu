#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Catalog500 to the discard-only physmap verifier and exact restoration."""
import hashlib
import json
from pathlib import Path
import types

_parent = Path(__file__).with_name("stage_gem_mapping_predicate_trial_v3.py")
_raw = _parent.read_bytes()
_PARENT_SHA = "12773aaacb2424b8f1c5cc7d3902110d7f9af2800279fbbbc538d525a95375d0"
if hashlib.sha256(_raw).hexdigest() != _PARENT_SHA:
    raise ValueError("Frozen mapping-predicate controller changed")
_text = _raw.decode()
for _old, _new in (
    ("stage_gem_mapping_predicate_trial_v3.py", "stage_gem_physmap_mapping_trial_v4.py"),
    ("serial_gem_mapping_predicate_trial_v3.py", "serial_gem_physmap_mapping_trial_v4.py"),
    ("gem_mapping_predicate_evidence_v3.py", "gem_physmap_mapping_evidence_v4.py"),
    ("arm_gem_mapping_predicate_reboot_v3.py", "arm_gem_physmap_mapping_reboot_v4.py"),
    ("serial_gem_mapping_predicate_trial_v3", "serial_gem_physmap_mapping_trial_v4"),
    ("gem_mapping_predicate_evidence_v3", "gem_physmap_mapping_evidence_v4"),
    ("arm_gem_mapping_predicate_reboot_v3", "arm_gem_physmap_mapping_reboot_v4"),
    ("gem_mapping_predicate_media_v1", "gem_physmap_mapping_media_v1"),
    ("gem_mapping_predicate_case_v1", "gem_physmap_mapping_case_v1"),
    ("gem_mapping_predicate_check_v3", "gem_physmap_mapping_check_v1"),
    ("gem_mapping_predicate_serial_v3", "gem_physmap_mapping_serial_v4"),
    ("gem_mapping_predicate_profile", "gem_physmap_mapping_verification_profile"),
    ("build_gem_mapping_predicate_trial", "build_gem_physmap_mapping_verification"),
    ("check_gem_mapping_predicate_trial", "check_gem_physmap_mapping_verification"),
    ("qualify_gem_mapping_predicate_transport_v3.py", "qualify_gem_physmap_mapping_transport_v4.py"),
    ("test_gem_mapping_predicate_transport_v3.py", "test_gem_physmap_mapping_transport_v4.py"),
    ("gem-mapping-predicate-three-target-controller-v3", "gem-physmap-mapping-three-target-controller-v4"),
    ("gem-mapping-predicate-three-target-v3", "gem-physmap-mapping-three-target-v4"),
    ("gem-mapping-predicate-independent-return-v3", "gem-physmap-mapping-independent-return-v4"),
    ("rpi5-gem-mapping-predicate-three-target-chain-v3", "rpi5-gem-physmap-mapping-three-target-chain-v4"),
    ("gem-mapping-predicate-v3", "gem-physmap-mapping-v4"),
    ("gem_mapping_predicate", "gem_physmap_mapping"),
    ("mapping-predicate v3", "physmap mapping v4"),
    ("gem-mapping-predicate-fixed54", "gem-physmap-mapping-fixed59"),
):
    if _old not in _text:
        raise ValueError("Exact physmap controller derivation boundary changed: " + _old)
    _text = _text.replace(_old, _new)
_parent_main = "if __name__=='__main__':raise SystemExit(main())"
if _text.count(_parent_main) != 2 or not _text.rstrip().endswith(_parent_main):
    raise ValueError("Physmap controller main boundary changed")
_head, _tail = _text.rsplit(_parent_main, 1)
_text = _head + "if False:raise SystemExit(main())" + _tail
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())
__doc__ = ("One bounded page-granular physmap verification, three guarded SD targets and zero UART TX. "
    "The exact catalog500 restoration is the only intake. The image must emit four alias rows and one "
    "page-table row, then prove Discarded before route; all originals are explicitly restored.")

for _name in ("inventory", "PREPARED", "PREPARED_PREFIX", "return_positions", "health"):
    if not hasattr(protocol, _name):
        setattr(protocol, _name, getattr(protocol.old, _name))


def transport():
    if __package__:
        from . import serial_gem_physmap_mapping_trial_v4
        from . import gem_physmap_mapping_evidence_v4
        from . import arm_gem_physmap_mapping_reboot_v4
    else:
        import serial_gem_physmap_mapping_trial_v4
        import gem_physmap_mapping_evidence_v4
        import arm_gem_physmap_mapping_reboot_v4
    return gem_physmap_mapping_evidence_v4


BASELINE = ROOT / "build/rpi5/gem-mapping-predicate-restored-20261014"
BASELINE_SEAL = "beb6c83c7a719a7bf140b5b48b32c9c4500b73ea4fbcffe7e84006cb0a204cc9"
BASELINE_PLAN = "da1df6b95c5251a23f18dc3e586a97cefc2b2448db40ce8f872ecbd4eabdbd63"
BASELINE_RESULT = "539aa40fa080cca5973c99782a04f2d0129d181e9c8d38be630807f60cfa492b"
BASELINE_BOOT = "a6c96368-1ef6-4c34-be8e-7efdd97a9395"
BASELINE_CATALOG = 500
BASELINE_CATALOG_SHA = "3fb9b00235759812efa3627104c9dd5158551c3ea981d47b540d333fe0e02186"
CONTROLLER = "gem-physmap-mapping-three-target-controller-v4"
DESCRIPTOR = "gem-physmap-mapping-fixed59"
_SOURCE_EXPECTATIONS = None


def package_graph(directory, _prior):
    """Pin the v9 package and every in-tree file named by its manifest.

    The predecessor graph parser has one historical compiler include-directory
    exception tied to an older package.  V9 is instead admitted by its strict
    checker and this byte inventory; no referenced file is normalized.
    """
    directory = Path(directory).resolve()
    if directory != PACKAGE or sha(directory / "manifest.json") != MANIFEST_SHA:
        raise ValueError("Exact v9 package graph required")
    pins = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            pins[str(path.resolve())] = sha(path)
    manifest = json.loads((directory / "manifest.json").read_text())
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.startswith("/"):
            path = Path(value)
            if ".." in path.parts:
                raise ValueError("Noncanonical v9 manifest reference")
            if path.is_file() and path.is_relative_to(ROOT):
                pins[str(path)] = sha(path)
    walk(manifest)
    return pins


def source_pins():
    global _SOURCE_EXPECTATIONS
    if _SOURCE_EXPECTATIONS is not None:
        if any(sha(n) != h for n, h in _SOURCE_EXPECTATIONS.items()):
            raise ValueError("Physmap transport source changed after inventory")
        return dict(_SOURCE_EXPECTATIONS)
    names = (
        "stage_gem_physmap_mapping_trial_v4.py", "serial_gem_physmap_mapping_trial_v4.py",
        "gem_physmap_mapping_evidence_v4.py", "arm_gem_physmap_mapping_reboot_v4.py",
        "gem_physmap_mapping_media_v1.py", "gem_physmap_mapping_case_v1.py",
        "gem_physmap_mapping_check_v1.py", "gem_physmap_mapping_serial_v4.py",
        "gem_physmap_mapping_verification_profile.py", "build_gem_physmap_mapping_verification.py",
        "check_gem_physmap_mapping_verification.py", "remote_namespace_audit_v1.py",
        "qualify_gem_physmap_mapping_transport_v4.py",
        "tests/test_gem_physmap_mapping_transport_v4.py",
    )
    if __package__:
        from . import stage_gem_mapping_predicate_trial_v3 as baseline_stage
    else:
        import stage_gem_mapping_predicate_trial_v3 as baseline_stage
    _SOURCE_EXPECTATIONS = (preceding.source_pins() | baseline_stage.source_pins() |
        engine.source_pins() | {str(_parent): _PARENT_SHA} |
        {str(ROOT / "tools/rpi5" / name): sha(ROOT / "tools/rpi5" / name) for name in names} |
        {str(CONFIG): engine.TRIAL_CONFIG_SHA,
         str(GOOD["config.txt"][0]): engine.ORIGINAL_CONFIG_SHA,
         str(case.REPORT): case.REPORT_SHA,
         str(PACKAGE / "manifest.json"): MANIFEST_SHA})
    if any(sha(n) != h for n, h in _SOURCE_EXPECTATIONS.items()):
        raise ValueError("Physmap source inventory differs")
    return dict(_SOURCE_EXPECTATIONS)


def valid_report(report):
    expected = checker.inspect(PACKAGE, MANIFEST_SHA)
    if (case.FROZEN is not True or sha(case.REPORT) != case.REPORT_SHA or
            not engine.same(report, expected) or not engine.same(report, json.loads(case.REPORT.read_text()))):
        raise ValueError("Exact separately retained physmap verification report required")
    required = dict(
        profile=checker.b.PROFILE, package=str(PACKAGE), manifest_sha256=MANIFEST_SHA,
        image_sha256=IMAGE_SHA, image_bytes=case.IMAGE_BYTES, tag=TAG,
        marker=checker.b.retry.trial.marker(TAG), trial_marker=checker.b.retry.trial.marker(TAG),
        bootargs=checker.b.retry.trial.BOOTARGS, page_granular_physmap=True,
        mapping_verification_only=True, mapping_success_reason=41, alias_rows=4,
        page_table_rows=1, discard_before_route=True, allocation_bytes=32768,
        maximum_page_table_pages=257, maximum_page_table_bytes=4210688,
        packet_spans=0, bme=False, dma=False, irq=False, queues=False, packets=False,
        queue_publication=False, physical_execution_proven=False,
        automatic_watchdog_return_required=True, complete_capture_health_required=True,
    )
    if any(not engine.same(report.get(k), v) for k, v in required.items()):
        raise ValueError("Exact59-row discard-only physmap report required")
    return True


def baseline(directory, seal_sha, plan_sha):
    if (Path(directory).resolve(), seal_sha, plan_sha) != (BASELINE, BASELINE_SEAL, BASELINE_PLAN):
        raise ValueError("Exact catalog500 restoration required")
    if sha(BASELINE / "result.json") != BASELINE_RESULT:
        raise ValueError("Catalog500 result changed")
    checkpoint = json.loads((BASELINE / "checkpoint.json").read_text())
    plan = json.loads((BASELINE / "plan.json").read_text())
    result = json.loads((BASELINE / "result.json").read_text())
    if (seals.digest(checkpoint) != BASELINE_SEAL or
            seals.digest(plan) != BASELINE_PLAN or
            result.get("checkpoint_sha256") != BASELINE_SEAL or
            result.get("plan_sha256") != BASELINE_PLAN):
        raise ValueError("Catalog500 immutable operation linkage differs")
    accepted = dict(directory=str(BASELINE), checkpoint=checkpoint, plan=plan, result=result,
        evidence={str(BASELINE / name): sha(BASELINE / name)
            for name in ("checkpoint.json", "plan.json", "result.json")})
    publication = accepted["result"]["publication"]
    files = publication["protected_files_sha256"]
    if (publication["identity"]["boot_id"] != BASELINE_BOOT or
            len(accepted["result"]["next_catalog"]) != BASELINE_CATALOG or
            accepted["result"]["next_catalog_sha256"] != BASELINE_CATALOG_SHA or
            any(files.get(name) != value[1] for name, value in GOOD.items())):
        raise ValueError("Catalog500 normal config/firmware/loader restoration required")
    return accepted


def prepare_install(directory, prior_seal, prior_plan, boot):
    if boot != BASELINE_BOOT:
        raise ValueError("Exact catalog500 Linux boot witness required")
    return _mapping_prepare_install_base(directory, prior_seal, prior_plan, boot)


_scope = globals()
for _name in ("sealed_operation", "load_installation", "prepare_restore", "restoration",
              "dispatch", "launch", "replay", "main"):
    _fn = _scope[_name]
    if hasattr(_fn, "__code__"):
        _scope[_name] = types.FunctionType(_fn.__code__, _scope, argdefs=_fn.__defaults__)

if __name__ == "__main__":
    raise SystemExit(main())
