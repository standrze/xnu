# SPDX-License-Identifier: BSD-2-Clause
"""Self-contained successor publisher for the ring-only retry.

The first retry transport embedded this small derivation wrapper in its remote
program.  That wrapper then tried to reopen its parent using the Mac build path.
This successor explicitly carries the verified parent source into the remote
module before executing the wrapper; the target never needs that local path.
"""
import hashlib
from pathlib import Path

_parent=Path(__file__).with_name('gem_cpu_batch_media_v1.py')
_PARENT_SHA='51ff5b30a9ca2edc27b442dd4432569ff1d7f195e401a45623d370bfea0a551b'
_embedded_parent_source=globals().get('_embedded_parent_source')
_raw=(_parent.read_bytes() if _embedded_parent_source is None else
    _embedded_parent_source.encode())
if hashlib.sha256(_raw).hexdigest()!=_PARENT_SHA:raise ValueError('Frozen three-target publisher changed')
_text=_raw.decode()
for _old,_new in (
    ('gem_cpu_batch_case_v1','gem_cpu_ring_retry_case_v1'),
    ('gem_cpu_batch_media_v1','gem_cpu_ring_retry_media_v2'),
    ('gem-cpu-batch-triple-trial-v1','gem-cpu-ring-retry-successor-triple-trial-v2'),
    ('gem-cpu-batch-triple-restore-v1','gem-cpu-ring-retry-successor-triple-restore-v2'),
    ('rpi5-gem-cpu-batch-triple-plan-v1','rpi5-gem-cpu-ring-retry-successor-triple-plan-v2'),
    ('rpi5-gem-cpu-batch-triple-result-v1','rpi5-gem-cpu-ring-retry-successor-triple-result-v2'),
    ('gem-cpu-batch','gem-cpu-ring-retry-successor'),
    ('cpubatch','ringretry2'),
    ('CPU-batch','ring-only retry successor')):
    if _old not in _text:raise ValueError('Exact successor publisher derivation boundary changed: '+_old)
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())

_generated_source_pins=source_pins
_generated_remote_source=remote_source

def source_pins():
    pins=_generated_source_pins();pins[str(_parent)]=_PARENT_SHA
    seals.check_pins(pins);return pins

def remote_source(checkpoint,checkpoint_sha,plan,expected_plan_sha):
    """Embed the frozen parent before the derived module executes remotely."""
    code=_generated_remote_source(checkpoint,checkpoint_sha,plan,expected_plan_sha)
    wrapper=Path(__file__).read_text()
    if hashlib.sha256(wrapper.encode()).hexdigest()!=checkpoint['evidence_sha256'].get(str(Path(__file__).resolve())):
        raise ValueError('Successor wrapper differs from sealed closure')
    assignment='gem_cpu_ring_retry_media_v2._active_window_source='+repr(wrapper)+'\n'
    if code.count(assignment)!=1:raise ValueError('Successor remote module boundary changed')
    embedded=assignment+'gem_cpu_ring_retry_media_v2._embedded_parent_source='+repr(_raw.decode())+'\n'
    code=code.replace(assignment,embedded,1)
    compile(code,'<gem-cpu-ring-retry-successor-remote>','exec')
    return code
