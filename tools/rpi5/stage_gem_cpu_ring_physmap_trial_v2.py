#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Catalog524 CPU-ring transport v2 with a self-contained remote publisher."""
import hashlib
from pathlib import Path

_v1_parent = Path(__file__).with_name("stage_gem_cpu_ring_physmap_trial_v1.py")
_V1_PARENT_SHA = "cb48524f470e0cc46841e56f3a2eb9c25aa9ade64ac9efc649f631fbef937194"
_raw_v1 = _v1_parent.read_bytes()
if hashlib.sha256(_raw_v1).hexdigest() != _V1_PARENT_SHA:
    raise ValueError("Frozen CPU-ring physmap v1 controller changed")
_text = _raw_v1.decode()
for _old, _new in (
    ("stage_gem_cpu_ring_physmap_trial_v1.py", "stage_gem_cpu_ring_physmap_trial_v2.py"),
    ("serial_gem_cpu_ring_physmap_trial_v1.py", "serial_gem_cpu_ring_physmap_trial_v2.py"),
    ("gem_cpu_ring_physmap_evidence_v1.py", "gem_cpu_ring_physmap_evidence_v2.py"),
    ("arm_gem_cpu_ring_physmap_reboot_v1.py", "arm_gem_cpu_ring_physmap_reboot_v2.py"),
    ("serial_gem_cpu_ring_physmap_trial_v1", "serial_gem_cpu_ring_physmap_trial_v2"),
    ("gem_cpu_ring_physmap_evidence_v1", "gem_cpu_ring_physmap_evidence_v2"),
    ("arm_gem_cpu_ring_physmap_reboot_v1", "arm_gem_cpu_ring_physmap_reboot_v2"),
    ("gem_cpu_ring_physmap_media_v1", "gem_cpu_ring_physmap_media_v2"),
    ("gem_cpu_ring_physmap_case_v1", "gem_cpu_ring_physmap_case_v2"),
    ("check_gem_cpu_ring_physmap_transport_v1", "check_gem_cpu_ring_physmap_transport_v2"),
    ("gem_cpu_ring_physmap_serial_v1", "gem_cpu_ring_physmap_serial_v2"),
    ("gem-cpu-ring-physmap-three-target-controller-v1", "gem-cpu-ring-physmap-three-target-controller-v2"),
    ("gem-cpu-ring-physmap-three-target-v1", "gem-cpu-ring-physmap-three-target-v2"),
    ("gem-cpu-ring-physmap-independent-return-v1", "gem-cpu-ring-physmap-independent-return-v2"),
    ("rpi5-gem-cpu-ring-physmap-three-target-chain-v1", "rpi5-gem-cpu-ring-physmap-three-target-chain-v2"),
    ("gem-cpu-ring-physmap-fixed53-v1", "gem-cpu-ring-physmap-fixed53-v2"),
):
    if _old not in _text:
        raise ValueError("Exact CPU-ring physmap v2 controller boundary changed: " + _old)
    _text = _text.replace(_old, _new)
_parent_main = 'if __name__ == "__main__":\n    raise SystemExit(main())'
if _text.count(_parent_main) != 1 or not _text.rstrip().endswith(_parent_main):
    raise ValueError("Frozen CPU-ring physmap v1 main boundary changed")
_text = _text.rsplit(_parent_main, 1)[0] + 'if False:\n    raise SystemExit(main())\n'
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())

_v2_generated_source_pins = source_pins


def source_pins():
    pins = _v2_generated_source_pins()
    pins[str(_v1_parent)] = _V1_PARENT_SHA
    if any(sha(name) != digest for name, digest in pins.items()):
        raise ValueError("CPU-ring physmap v2 source inventory differs")
    return pins


if __name__ == "__main__":
    raise SystemExit(main())
