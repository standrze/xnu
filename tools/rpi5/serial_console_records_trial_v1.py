#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged five-command receiver, exact console-record namespace."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('serial_restart_late_trial.py');_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='ea6e8e6582ab9a4cebdf509ee4fed3feb51902616da00e22d0ab75e39a9a3585':raise ValueError('Frozen late receiver required')
_text=_raw.decode()
for _old,_new in (('stage_restart_late_trial','stage_console_records_trial_v1'),
    ('restart_late_serial','console_records_serial'),('CAPTURE_ARMED RESTART_LATE','CAPTURE_ARMED CONSOLE_RECORDS')):
    if _text.count(_old)!=1:raise ValueError('Exact receiver namespace boundary')
    _text=_text.replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
