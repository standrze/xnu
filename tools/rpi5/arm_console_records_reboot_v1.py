#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original arm-before-one-reboot launcher, console-record receiver."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('arm_restart_late_trial.py');_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='33d6e2a4973bdf4d992258d5c952055376d758580a71450fb9307e3f5533c17a':raise ValueError('Frozen one-shot late launcher required')
_text=_raw.decode();_old='import serial_restart_late_trial as recorder'
if _text.count(_old)!=1:raise ValueError('Exact launcher receiver boundary')
_text=_text.replace(_old,'import serial_console_records_trial_v1 as recorder')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
