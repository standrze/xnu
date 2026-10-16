#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged five-command diagnostic receiver, new exact loader namespace."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('serial_restart_diagnostic_trial.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='e8c57a6a673c06c0e664de9d138635eb5c4aa98a912d30554b1a873fadfaf03a':raise ValueError('Exact bounded diagnostic receiver required')
_text=_raw.decode()
for _old,_new in (
    ('stage_restart_diagnostic_trial','stage_restart_copy_trial'),
    ('restart_diagnostic_serial','restart_copy_serial'),
    ('RESTART_DIAGNOSTIC_ARMED','CAPTURE_ARMED RESTART_COPY'),
):
    if _text.count(_old)!=1:raise ValueError('Exact receiver binding required')
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
