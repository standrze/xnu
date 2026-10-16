# SPDX-License-Identifier: BSD-2-Clause
"""V2 full-tail replay with a 300s host window and unchanged kernel/TX checks."""
import hashlib
from pathlib import Path

_original = Path(__file__).with_name('display_xnu_evidence.py')
_bytes = _original.read_bytes()
if hashlib.sha256(_bytes).hexdigest() != '330895f6d3578a4b82aacdf0554959f365a32daf0f01109b12c95c0bd1a6d9e9':
    raise ValueError('Exact frozen display evidence required')
_text = _bytes.decode()
for _old, _new in (
    ('import stage_display_xnu_trial as stage', 'import stage_display_xnu_trial_v2 as stage'),
    ('import serial_display_xnu_trial as recorder', 'import serial_display_xnu_trial_v2 as recorder'),
    ("FORMAT='rpi5-display-xnu-independent-return-v1'", "FORMAT='rpi5-display-xnu-independent-return-v2'"),
    ('if not 0<delta<240 or not 0<reset_delta<220:',
     'if not 0<delta<recorder.HOST_RETURN_SECONDS or not 0<reset_delta<220:'),
    ("if __name__=='__main__':raise SystemExit(main())", ''),
):
    if _text.count(_old) != 1:
        raise ValueError('Exact evidence derivation boundary changed')
    _text = _text.replace(_old, _new)
exec(compile(_text, str(Path(__file__).resolve()), 'exec'), globals())
_inspect_capture = inspect_capture


def inspect_capture(data, rows, state, installed, sources):
    expected = recorder.initial({'installed': installed, 'evidence': state['receipt_evidence_sha256']},
                                state['device'], state['pid'], state['started_utc'])['host_return_window']
    if not stage.engine.same(state.get('host_return_window'), expected):
        raise ValueError('Exact explicit host-only return window required')
    result = _inspect_capture(data, rows, state, installed, sources)
    result['host_return_window'] = expected
    return result


# The frozen return functions use the private scope built above. Its capture
# function calls this module's global oracle, not a separately copied oracle.
if __name__ == '__main__':
    raise SystemExit(main())
