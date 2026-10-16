#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original one-shot launch body bound to the separate V2 receiver."""
import hashlib
from pathlib import Path
_original = Path(__file__).with_name('arm_display_xnu_reboot.py')
_bytes = _original.read_bytes()
if hashlib.sha256(_bytes).hexdigest() != '4797df9d6bb41fe6e68e5c36ff34df226efc7b1503096e9471c808aa88735af9':
    raise ValueError('Exact frozen one-shot launcher required')
_text = _bytes.decode()
_old = 'import serial_display_xnu_trial as recorder'
if _text.count(_old) != 1:
    raise ValueError('Exact launcher binding boundary changed')
_text = _text.replace(_old, 'import serial_display_xnu_trial_v2 as recorder')
exec(compile(_text, str(Path(__file__).resolve()), 'exec'), globals())
