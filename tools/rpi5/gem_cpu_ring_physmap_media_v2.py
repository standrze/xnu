#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Self-contained publisher for CPU-ring physmap transport v2.

The complete retry-publisher derivation source is carried into the remote
module.  Remote initialization never reopens a Mac build path.
"""
import ast
import hashlib
from pathlib import Path
import re

_retry_parent = Path(__file__).with_name("gem_cpu_ring_retry_media_v2.py")
_RETRY_PARENT_SHA = "058a8870c22634a119e50d9ef9de7dde1d79b07d3f978f6204a9c9038e5669d7"
_batch_base = Path(__file__).with_name("gem_cpu_batch_media_v1.py")
_BATCH_BASE_SHA = "51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b"
_embedded_retry_source = globals().get("_embedded_retry_source")
_raw_retry = (_retry_parent.read_bytes() if _embedded_retry_source is None else
    _embedded_retry_source.encode())
if hashlib.sha256(_raw_retry).hexdigest() != _RETRY_PARENT_SHA:
    raise ValueError("Frozen CPU-ring retry publisher changed")
_text = _raw_retry.decode()
for _old, _new in (
    ("gem_cpu_ring_retry_case_v1", "gem_cpu_ring_physmap_case_v2"),
    ("gem_cpu_ring_retry_media_v2", "gem_cpu_ring_physmap_media_v2"),
    ("gem-cpu-ring-retry-successor-triple-trial-v2", "gem-cpu-ring-physmap-triple-trial-v2"),
    ("gem-cpu-ring-retry-successor-triple-restore-v2", "gem-cpu-ring-physmap-triple-restore-v2"),
    ("rpi5-gem-cpu-ring-retry-successor-triple-plan-v2", "rpi5-gem-cpu-ring-physmap-triple-plan-v2"),
    ("rpi5-gem-cpu-ring-retry-successor-triple-result-v2", "rpi5-gem-cpu-ring-physmap-triple-result-v2"),
    ("gem-cpu-ring-retry-successor", "gem-cpu-ring-physmap-v2"),
    ("ringretry2", "ringphysmap2"),
    ("ring-only retry successor", "physmap-enabled CPU-owned-ring trial v2"),
):
    if _old not in _text:
        raise ValueError("Exact CPU-ring physmap v2 publisher boundary changed: " + _old)
    _text = _text.replace(_old, _new)
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())

_v2_generated_source_pins = source_pins
_v2_generated_remote_source = remote_source


def source_pins():
    pins = _v2_generated_source_pins()
    if _embedded_retry_source is None:
        pins[str(_retry_parent)] = _RETRY_PARENT_SHA
        seals.check_pins(pins)
        direct = {
            str(Path(__file__).resolve()): hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            str(_retry_parent): _RETRY_PARENT_SHA,
            str(_batch_base): _BATCH_BASE_SHA,
        }
        if any(pins.get(name) != digest for name, digest in direct.items()):
            raise ValueError("V2 wrapper/retry/base direct source pins differ")
    return pins


def remote_source(checkpoint, checkpoint_sha, plan, expected_plan_sha):
    code = _v2_generated_remote_source(checkpoint, checkpoint_sha, plan, expected_plan_sha)
    # The frozen base generator records its build-host filenames as module
    # metadata.  They are useful locally but must not become target lookups:
    # each embedded module receives a synthetic filename before it executes.
    local_root = str(Path(__file__).resolve().parents[2]) + "/"
    sanitized = []
    for row in code.splitlines():
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.__file__=", row):
            name, encoded = row.split("=", 1)
            value = ast.literal_eval(encoded)
            if isinstance(value, str) and value.startswith(local_root):
                relative = Path(value).relative_to(local_root.rstrip("/"))
                row = name + "=" + repr(str(Path("/__rpi5_embedded__") / relative))
        sanitized.append(row)
    code = "\n".join(sanitized) + "\n"
    wrapper = Path(__file__).read_text()
    wrapper_path = str(Path(__file__).resolve())
    if hashlib.sha256(wrapper.encode()).hexdigest() != checkpoint["evidence_sha256"].get(wrapper_path):
        raise ValueError("V2 publisher wrapper differs from sealed closure")
    assignment = "gem_cpu_ring_physmap_media_v2._active_window_source=" + repr(wrapper) + "\n"
    if code.count(assignment) != 1:
        raise ValueError("V2 remote module boundary changed")
    embedded = assignment + "gem_cpu_ring_physmap_media_v2._embedded_retry_source=" + repr(_raw_retry.decode()) + "\n"
    code = code.replace(assignment, embedded, 1)
    immediate = "gem_cpu_ring_physmap_media_v2._embedded_retry_source="
    base = "gem_cpu_ring_physmap_media_v2._embedded_parent_source="
    rows = code.splitlines()
    if (sum(row.startswith(immediate) for row in rows) != 1 or
            sum(row.startswith(base) for row in rows) != 1):
        raise ValueError("Exactly one immediate and one base publisher source must be embedded")
    compile(code, "<gem-cpu-ring-physmap-v2-remote>", "exec")
    return code
