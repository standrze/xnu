# SPDX-License-Identifier: BSD-2-Clause
"""Exact diagnostic grammar, bound to the distinct copy-phase loader tag."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('restart_diagnostic_serial.py')
_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='2041a4dffacf4210ef0a25e59877d00e2bbff75c2bcc7e3b94d1e04271b0ca20':raise ValueError('Frozen diagnostic grammar required')
_text=_raw.decode().replace('RPI5XNU:DISPLAYRESTART_DIAG:ENTRY TAG=','RPI5XNU:DISPLAYRESTART_COPY:ENTRY TAG=')
if _text==_raw.decode():raise ValueError('Exact diagnostic tag derivation required')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
