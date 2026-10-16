#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original one-shot arm/boot implementation; exact CAPTURE_ARMED receiver."""
import hashlib
from pathlib import Path
_parent=Path(__file__).with_name('arm_display_xnu_reboot.py');_raw=_parent.read_bytes()
if hashlib.sha256(_raw).hexdigest()!='4797df9d6bb41fe6e68e5c36ff34df226efc7b1503096e9471c808aa88735af9':raise ValueError('Exact one-shot launcher required')
_text=_raw.decode();_old='import serial_display_xnu_trial as recorder'
if _text.count(_old)!=1:raise ValueError('Exact original recorder import')
_text=_text.replace(_old,'import serial_restart_copy_trial as recorder')
exec(compile(_text,str(Path(__file__).resolve()),'exec'),globals())
