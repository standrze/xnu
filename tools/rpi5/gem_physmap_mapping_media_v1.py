# SPDX-License-Identifier: BSD-2-Clause
"""Self-contained publisher for the page-granular physmap v4 transport."""
import hashlib
from pathlib import Path

_parent = Path(__file__).with_name("gem_cpu_batch_media_v1.py")
_PARENT_SHA = "51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b"
_embedded_parent_source = globals().get("_embedded_parent_source")
_raw = _parent.read_bytes() if _embedded_parent_source is None else _embedded_parent_source.encode()
if hashlib.sha256(_raw).hexdigest() != _PARENT_SHA:
    raise ValueError("Frozen mapping-predicate publisher changed")
_text = _raw.decode()
for _old, _new in (
    ("gem_cpu_batch_case_v1", "gem_physmap_mapping_case_v1"),
    ("gem_cpu_batch_media_v1", "gem_physmap_mapping_media_v1"),
    ("gem-cpu-batch-triple-trial-v1", "gem-physmap-mapping-v4-triple-trial-v1"),
    ("gem-cpu-batch-triple-restore-v1", "gem-physmap-mapping-v4-triple-restore-v1"),
    ("rpi5-gem-cpu-batch-triple-plan-v1", "rpi5-gem-physmap-mapping-v4-triple-plan-v1"),
    ("rpi5-gem-cpu-batch-triple-result-v1", "rpi5-gem-physmap-mapping-v4-triple-result-v1"),
    ("gem-cpu-batch", "gem-physmap-mapping-v4"),
    ("cpubatch", "physmapv4"),
    ("CPU-batch", "physmap mapping v4"),
):
    if _old not in _text:
        raise ValueError("Exact physmap publisher derivation boundary changed: " + _old)
    _text = _text.replace(_old, _new)
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())

_generated_source_pins = source_pins
_generated_remote_source = remote_source


def source_pins():
    pins = _generated_source_pins()
    pins[str(_parent)] = _PARENT_SHA
    seals.check_pins(pins)
    return pins


def remote_source(checkpoint, checkpoint_sha, plan, expected_plan_sha):
    code = _generated_remote_source(checkpoint, checkpoint_sha, plan, expected_plan_sha)
    wrapper = Path(__file__).read_text()
    if hashlib.sha256(wrapper.encode()).hexdigest() != checkpoint["evidence_sha256"].get(str(Path(__file__).resolve())):
        raise ValueError("Physmap publisher differs from sealed closure")
    assignment = "gem_physmap_mapping_media_v1._active_window_source=" + repr(wrapper) + "\n"
    if code.count(assignment) != 1:
        raise ValueError("Physmap remote module boundary changed")
    flattened = _text
    anchor = "SOURCE=Path(original.__file__).resolve()"
    if flattened.count(anchor) != 1:
        raise ValueError("Physmap remote SOURCE boundary changed")
    flattened = flattened.replace(anchor, "SOURCE=Path(original.__file__)", 1)
    compile(flattened, "<gem-physmap-mapping-v4-flattened>", "exec")
    code = code.replace(assignment,
        "gem_physmap_mapping_media_v1._active_window_source=" + repr(flattened) + "\n", 1)
    invocation = "exec(" + repr(wrapper) + ",gem_physmap_mapping_media_v1.__dict__)\n"
    if code.count(invocation) != 1:
        raise ValueError("Physmap remote exec boundary changed")
    code = code.replace(invocation,
        "exec(" + repr(flattened) + ",gem_physmap_mapping_media_v1.__dict__)\n", 1)
    compile(code, "<gem-physmap-mapping-v4-remote>", "exec")
    return code

