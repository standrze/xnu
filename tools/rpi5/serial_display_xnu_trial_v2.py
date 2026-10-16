#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate host capture allowance; the frozen kernel and TX limits do not change."""
import hashlib
from pathlib import Path

HOST_RETURN_SECONDS = 60 + 180 + 15 + 45
_original = Path(__file__).with_name('serial_display_xnu_trial.py')
_bytes = _original.read_bytes()
if hashlib.sha256(_bytes).hexdigest() != 'c6fae18287d73b3356480604431b754666733879eec3f7df21332a4ebb4fe2fb':
    raise ValueError('Exact frozen display receiver required')
_text = _bytes.decode()
for _old, _new in (
    ('import stage_display_xnu_trial as stage', 'import stage_display_xnu_trial_v2 as stage'),
    ('deadline=sd_time+240 if sd_time is not None else initial_deadline',
     'deadline=sd_time+HOST_RETURN_SECONDS if sd_time is not None else initial_deadline'),
    ("if __name__=='__main__':raise SystemExit(main())", ''),
):
    if _text.count(_old) != 1:
        raise ValueError('Exact receiver derivation boundary changed')
    _text = _text.replace(_old, _new)
exec(compile(_text, str(Path(__file__).resolve()), 'exec'), globals())
_initial = initial


def initial(context, device, pid=None, started=None):
    state = _initial(context, device, pid, started)
    state['host_return_window'] = dict(
        sd_to_nvme_seconds=HOST_RETURN_SECONDS,
        loader_allowance_seconds=60, terminal_service_seconds=180,
        hardware_countdown_seconds=15, firmware_return_allowance_seconds=45,
        kernel_deadline_extended=False, tx_deadline_extended=False)
    return state


if __name__ == '__main__':
    raise SystemExit(main())
