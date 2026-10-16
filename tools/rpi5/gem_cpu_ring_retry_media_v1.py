# SPDX-License-Identifier: BSD-2-Clause
"""Source-pinned three-target publisher for the ring-only retry."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('gem_cpu_batch_media_v1.py');_raw=_parent.read_bytes()
_PARENT_SHA='51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b'
if hashlib.sha256(_raw).hexdigest()!=_PARENT_SHA:raise ValueError('Frozen three-target publisher changed')
_text=_raw.decode()
for _old,_new in (('gem_cpu_batch_case_v1','gem_cpu_ring_retry_case_v1'),
    ('gem_cpu_batch_media_v1','gem_cpu_ring_retry_media_v1'),
    ('gem-cpu-batch','gem-cpu-ring-retry'),('cpubatch','ringretry'),('CPU-batch','ring-only retry')):
    if _old not in _text:raise ValueError('Exact publisher derivation boundary changed: '+_old)
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
_generated_source_pins=source_pins
def source_pins():
    pins=_generated_source_pins();pins[str(_parent)]=_PARENT_SHA
    seals.check_pins(pins);return pins
