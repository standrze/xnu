#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Late state-confirmed root trial evidence; no retrospective old-run acceptance."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root42_pthread_evidence as base
import stage_root42_ready_trial as stage
import serial_root42_ready_trial as recorder
import root42_ready_command_evidence as commands

FORMAT='rpi5-root42-state-confirmed-independent-return-v1'


def source_pins(context):
    pins=recorder.bound_sources(context)
    if pins.get(str(Path(__file__).resolve()))!=stage.sha(__file__):raise ValueError('Late-root evidence source absent from seal')
    return pins


def captured(context,directory):
    core=recorder.core.bind(context['installed']['preflight'])
    facade=types.SimpleNamespace(**{**vars(recorder),'core':core,'checked_core':core})
    # Snapshot count/consistency is checked across the full transcript even
    # after the ninth executable, in addition to the complete fault guard.
    raw=(stage.local(directory)/'serial.bin').read_bytes()
    try:recorder.core.snapshots(raw,context['installed']['preflight'])
    except ValueError as error:
        # Preserve invalid-capture classification while permitting an exact
        # independently observed Linux return and explicit restoration.
        fn=stage.private(base.captured,recorder=facade,stage=stage,commands=commands)
        state,observed,pins=fn(context,directory)
        observed.update(capture_valid=False,diagnostic=None,capture_error=str(error))
        return state,observed,pins
    return stage.private(base.captured,recorder=facade,stage=stage,commands=commands)(context,directory)


scope={**vars(base),'stage':stage,'recorder':recorder,'commands':commands,'FORMAT':FORMAT,
    'source_pins':source_pins,'captured':captured,'__file__':__file__,'__doc__':__doc__}
for name in ('inspect_return','collect_return','load_return','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]


if __name__=='__main__':raise SystemExit(main())
