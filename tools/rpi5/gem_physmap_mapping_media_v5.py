# SPDX-License-Identifier: BSD-2-Clause
"""Self-contained publisher for the corrected catalog512 physmap v5 transport."""
import hashlib
from pathlib import Path

_v4_parent = Path(__file__).with_name("gem_physmap_mapping_media_v1.py")
_V4_PARENT_SHA = "57407b2bb7476bf566d1df5b3f0ebae97a239f949aeb1988ea23fcb8890e89ca"
_raw_v4 = _v4_parent.read_bytes()
if hashlib.sha256(_raw_v4).hexdigest() != _V4_PARENT_SHA:
    raise ValueError("Frozen physmap v4 publisher changed")
_text_v5 = _raw_v4.decode()
for _old, _new in (
    ("gem-physmap-mapping-v4-triple-trial-v1", "gem-physmap-mapping-v5-triple-trial-v1"),
    ("gem-physmap-mapping-v4-triple-restore-v1", "gem-physmap-mapping-v5-triple-restore-v1"),
    ("rpi5-gem-physmap-mapping-v4-triple-plan-v1", "rpi5-gem-physmap-mapping-v5-triple-plan-v1"),
    ("rpi5-gem-physmap-mapping-v4-triple-result-v1", "rpi5-gem-physmap-mapping-v5-triple-result-v1"),
    ("gem-physmap-mapping-v4", "gem-physmap-mapping-v5"),
    ("physmapv4", "physmapv5"),
    ("physmap mapping v4", "physmap mapping v5"),
):
    if _text_v5.count(_old) < 1:
        raise ValueError("Exact physmap v5 publisher boundary changed: " + _old)
    _text_v5 = _text_v5.replace(_old, _new)
exec(compile(_text_v5, str(Path(__file__).resolve()), "exec"), globals())

_generated_source_pins_v5 = source_pins


def source_pins():
    pins = _generated_source_pins_v5()
    pins[str(_v4_parent)] = _V4_PARENT_SHA
    seals.check_pins(pins)
    return pins
