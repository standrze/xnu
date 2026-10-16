#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Self-contained three-target publisher for the physmap CPU-ring trial."""
import hashlib
from pathlib import Path

_parent = Path(__file__).with_name("gem_cpu_ring_retry_media_v2.py")
_PARENT_SHA = "058a8870c22634a119e50d9ef9de7dde1d79b07d3f978f6204a9c9038e5669d7"
_raw_parent = _parent.read_bytes()
if hashlib.sha256(_raw_parent).hexdigest() != _PARENT_SHA:
    raise ValueError("Frozen CPU-ring retry publisher changed")
_text = _raw_parent.decode()
for _old, _new in (
    ("gem_cpu_ring_retry_case_v1", "gem_cpu_ring_physmap_case_v1"),
    ("gem_cpu_ring_retry_media_v2", "gem_cpu_ring_physmap_media_v1"),
    ("gem-cpu-ring-retry-successor-triple-trial-v2", "gem-cpu-ring-physmap-triple-trial-v1"),
    ("gem-cpu-ring-retry-successor-triple-restore-v2", "gem-cpu-ring-physmap-triple-restore-v1"),
    ("rpi5-gem-cpu-ring-retry-successor-triple-plan-v2", "rpi5-gem-cpu-ring-physmap-triple-plan-v1"),
    ("rpi5-gem-cpu-ring-retry-successor-triple-result-v2", "rpi5-gem-cpu-ring-physmap-triple-result-v1"),
    ("gem-cpu-ring-retry-successor", "gem-cpu-ring-physmap"),
    ("ringretry2", "ringphysmap1"),
    ("ring-only retry successor", "physmap-enabled CPU-owned-ring trial"),
):
    if _old not in _text:
        raise ValueError("Exact CPU-ring physmap publisher boundary changed: " + _old)
    _text = _text.replace(_old, _new)
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())

_physmap_generated_source_pins = source_pins


def source_pins():
    pins = _physmap_generated_source_pins()
    pins[str(_parent)] = _PARENT_SHA
    seals.check_pins(pins)
    return pins
