# SPDX-License-Identifier: BSD-2-Clause
"""Strict late restart grammar rebound to the sealed console-record image."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_late_serial.py');_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='181556b857aea437efe9983941e33f7e043797b1d4f665b0f982c7fc1acb506b':raise ValueError('Frozen strict late protocol required')
_text=_raw.decode()
_old="exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())"
_new=_old+"\nINIT_READY=b'RPI5XNU:INIT:SHUTDOWN_READY MASKED POLLED STOP_LATCH'"
if _text.count(_old)!=1 or _text.count('RPI5XNU:DISPLAYRESTART_LATE:ENTRY TAG=')!=1:raise ValueError('Exact protocol derivation boundary')
_text=_text.replace('RPI5XNU:DISPLAYRESTART_LATE:ENTRY TAG=','RPI5XNU:DISPLAY_CONSOLE_RECORDS:ENTRY TAG=').replace(_old,_new)
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
