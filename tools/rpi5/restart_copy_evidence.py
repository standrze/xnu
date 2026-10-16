# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged full diagnostic capture/independent return semantics, new binding."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_diagnostic_evidence.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='79a8e2e9dc885abd10c004a0c8c913b6e63e57253ccd1e58a1c979d46d031dd8':raise ValueError('Frozen diagnostic evidence required')
_text=_raw.decode()
for _old,_new in (
    ('stage_restart_diagnostic_trial','stage_restart_copy_trial'),
    ('serial_restart_diagnostic_trial','serial_restart_copy_trial'),
    ('rpi5-restart-diagnostic-independent-return-v1','rpi5-restart-copy-independent-return-v1'),
):
    if _text.count(_old)!=1:raise ValueError('Exact evidence binding required')
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
