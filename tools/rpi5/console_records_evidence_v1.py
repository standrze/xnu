# SPDX-License-Identifier: BSD-2-Clause
"""Full raw capture and independent NVMe return, console-record binding."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_late_evidence.py');_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='5b61caae9447087620d69f7354d36e7fd68d11a04d9cc791b745f65c73954eae':raise ValueError('Frozen late evidence required')
_text=_raw.decode()
for _old,_new in (('stage_restart_late_trial','stage_console_records_trial_v1'),
    ('serial_restart_late_trial','serial_console_records_trial_v1'),
    ('rpi5-restart-late-independent-return-v1','rpi5-console-records-independent-return-v1')):
    if _text.count(_old)!=1:raise ValueError('Exact evidence namespace boundary')
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
