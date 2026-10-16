#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Catalog512 to the corrected discard-only physmap verifier and restoration."""
import hashlib
from pathlib import Path

_v4_parent = Path(__file__).with_name("stage_gem_physmap_mapping_trial_v4.py")
_V4_PARENT_SHA = "8f4be24b9c9ff585a07b322c0d0183948da87f48e872cb6bb7bb41bbf03bfc1c"
_raw_v4 = _v4_parent.read_bytes()
if hashlib.sha256(_raw_v4).hexdigest() != _V4_PARENT_SHA:
    raise ValueError("Frozen physmap v4 controller changed")
_text_v5 = _raw_v4.decode()
for _old, _new in (
    ("stage_gem_physmap_mapping_trial_v4.py", "stage_gem_physmap_mapping_trial_v5.py"),
    ("serial_gem_physmap_mapping_trial_v4.py", "serial_gem_physmap_mapping_trial_v5.py"),
    ("gem_physmap_mapping_evidence_v4.py", "gem_physmap_mapping_evidence_v5.py"),
    ("arm_gem_physmap_mapping_reboot_v4.py", "arm_gem_physmap_mapping_reboot_v5.py"),
    ("serial_gem_physmap_mapping_trial_v4", "serial_gem_physmap_mapping_trial_v5"),
    ("gem_physmap_mapping_evidence_v4", "gem_physmap_mapping_evidence_v5"),
    ("arm_gem_physmap_mapping_reboot_v4", "arm_gem_physmap_mapping_reboot_v5"),
    ("gem_physmap_mapping_media_v1", "gem_physmap_mapping_media_v5"),
    ("gem_physmap_mapping_serial_v4", "gem_physmap_mapping_serial_v5"),
    ("qualify_gem_physmap_mapping_transport_v4.py", "qualify_gem_physmap_mapping_transport_v5.py"),
    ("test_gem_physmap_mapping_transport_v4.py", "test_gem_physmap_mapping_transport_v5.py"),
    ("gem-physmap-mapping-three-target-controller-v4", "gem-physmap-mapping-three-target-controller-v5"),
    ("gem-physmap-mapping-three-target-v4", "gem-physmap-mapping-three-target-v5"),
    ("gem-physmap-mapping-independent-return-v4", "gem-physmap-mapping-independent-return-v5"),
    ("rpi5-gem-physmap-mapping-three-target-chain-v4", "rpi5-gem-physmap-mapping-three-target-chain-v5"),
    ("gem-physmap-mapping-fixed59", "gem-physmap-mapping-fixed59-v5"),
    ("Catalog500", "Catalog512"),
    ("catalog500", "catalog512"),
    ("v9 package", "v10 package"),
    ("V9 is", "V10 is"),
    ("Noncanonical v9", "Noncanonical v10"),
    ('BASELINE = ROOT / "build/rpi5/gem-mapping-predicate-restored-20261014"',
     'BASELINE = ROOT / "build/rpi5/gem-physmap-mapping-v4-restored"'),
    ('BASELINE_SEAL = "beb6c83c7a719a7bf140b5b48b32c9c4500b73ea4fbcffe7e84006cb0a204cc9"',
     'BASELINE_SEAL = "6b55bf9cf939bb70a58e3781cf1f54eb0633167a95bde75db6bc663df6bdb2b3"'),
    ('BASELINE_PLAN = "da1df6b95c5251a23f18dc3e586a97cefc2b2448db40ce8f872ecbd4eabdbd63"',
     'BASELINE_PLAN = "f77a4e94248d6df7b215086ff32aa18acf94ad570509e48a3d384b7cd9a0ce37"'),
    ('BASELINE_RESULT = "539aa40fa080cca5973c99782a04f2d0129d181e9c8d38be630807f60cfa492b"',
     'BASELINE_RESULT = "20345faa425243b43f1578aa30f1c0c3983192cd21fde92a9906ee2555f38298"'),
    ('BASELINE_BOOT = "a6c96368-1ef6-4c34-be8e-7efdd97a9395"',
     'BASELINE_BOOT = "5a1f5c04-c3d6-463a-8785-d737a3d59935"'),
    ("BASELINE_CATALOG = 500", "BASELINE_CATALOG = 512"),
    ('BASELINE_CATALOG_SHA = "3fb9b00235759812efa3627104c9dd5158551c3ea981d47b540d333fe0e02186"',
     'BASELINE_CATALOG_SHA = "8f7be2df370eb5a6951e645fca95d0609db141cf07ac53da020e7bcd26964566"'),
    ("maximum_page_table_pages=257, maximum_page_table_bytes=4210688,",
     "maximum_page_table_pages=259, maximum_page_table_bytes=4243456, preallocated_upper_pages=1,"),
):
    if _text_v5.count(_old) < 1:
        raise ValueError("Exact physmap v5 derivation boundary changed: " + _old)
    _text_v5 = _text_v5.replace(_old, _new)
_main_v4 = 'if __name__ == "__main__":\n    raise SystemExit(main())'
if _text_v5.count(_main_v4) != 1 or not _text_v5.rstrip().endswith(_main_v4):
    raise ValueError("Physmap v5 controller main boundary changed")
_text_v5 = _text_v5.rsplit(_main_v4, 1)[0] + "if False:\n    raise SystemExit(main())\n"
exec(compile(_text_v5, str(Path(__file__).resolve()), "exec"), globals())

_generated_source_pins_v5 = source_pins


def source_pins():
    pins = _generated_source_pins_v5()
    pins[str(_v4_parent)] = _V4_PARENT_SHA
    if any(sha(name) != digest for name, digest in pins.items()):
        raise ValueError("Physmap v5 source inventory differs")
    return pins


if __name__ == "__main__":
    raise SystemExit(main())
