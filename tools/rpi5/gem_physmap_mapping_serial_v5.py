# SPDX-License-Identifier: BSD-2-Clause
"""Strict zero-TX parser for the corrected page-granular physmap image."""
import hashlib
from pathlib import Path

_parent = Path(__file__).with_name("gem_physmap_mapping_serial_v4.py")
_PARENT_SHA = "b6a8583a8717391c00904531028c0c02109ade2b8583109443c0d334ef09ce6b"
_raw = _parent.read_bytes()
if hashlib.sha256(_raw).hexdigest() != _PARENT_SHA:
    raise ValueError("Frozen physmap v4 parser changed")
_text = _raw.decode()
for _old, _new in (
    ("page-granular physmap verification image", "corrected page-granular physmap verification image"),
    ("START END BYTES PAGES MAX PAGE_BYTES MAPPED RESERVATION_CLEAR",
     "START END BYTES PAGES MAX EDGE UPPER PAGE_BYTES MAPPED RESERVATION_CLEAR"),
    ('1 <= pgtable["pages"] <= pgtable["max"] <= 257 and',
     '1 <= pgtable["pages"] <= pgtable["max"] <= 259 and\n            0 <= pgtable["edge"] <= 2 and pgtable["upper"] == 1 and'),
    ('pgtable["bytes"] <= 4210688 and pgtable["mapped"] > 0 and',
     'pgtable["bytes"] <= 4243456 and pgtable["mapped"] > 0 and'),
    ('marker = report.get("marker", "")\n    expected = checker.b.retry.trial.marker(tag)',
     'marker = report.get("trial_marker", "")\n    if report.get("marker") != marker:\n        raise ValueError("Package marker aliases differ")\n    expected = checker.b.retry.trial.marker(tag)'),
):
    if _text.count(_old) != 1:
        raise ValueError("Exact physmap v5 parser boundary changed: " + _old)
    _text = _text.replace(_old, _new, 1)
exec(compile(_text, str(Path(__file__).resolve()), "exec"), globals())
