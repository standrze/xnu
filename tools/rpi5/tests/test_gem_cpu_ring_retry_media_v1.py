# SPDX-License-Identifier: BSD-2-Clause
"""Run the complete three-target publisher fault suite in the retry namespace."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('test_gem_cpu_batch_media_v1.py');_raw=_parent.read_bytes()
_PIN='f33ed43759b8214707edbb535aa352d9c1a589c6144cd3743268a2850bbc0285'
if hashlib.sha256(_raw).hexdigest()!=_PIN:raise ValueError('Frozen publisher fault suite changed')
_text=_raw.decode().replace('gem_cpu_batch_media_v1','gem_cpu_ring_retry_media_v1')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
