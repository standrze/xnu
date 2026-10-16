#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Strict twelve-command replay and separately observed normal-NVMe return."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root42_pthread_evidence as base
import root42_ready_evidence as previous
import stage_root45_entropy_trial as stage
import serial_root45_entropy_trial as recorder
import root45_entropy_command_evidence as commands

FORMAT='rpi5-root45-entropy-state-confirmed-independent-return-v1'


def source_pins(context):
    pins=recorder.bound_sources(context)
    if pins.get(str(Path(__file__).resolve()))!=stage.sha(__file__):raise ValueError('Root45 evidence source absent from seal')
    return pins


_captured=stage.private(previous.captured,base=base,stage=stage,recorder=recorder,commands=commands)


def captured(context,directory):
    state,observed,pins=_captured(context,directory)
    raw=(stage.local(directory)/'serial.bin').read_bytes()
    if any(marker in raw for marker in recorder.core.RUNTIME_FAULTS):
        observed.update(capture_valid=False,diagnostic=None,capture_error='Runtime fault in complete root45 capture')
    if observed['diagnostic'] is not None:observed['diagnostic']['status']='root45_entropy_serial_replayed'
    return state,observed,pins


scope={**vars(base),'stage':stage,'recorder':recorder,'commands':commands,'FORMAT':FORMAT,
    'source_pins':source_pins,'captured':captured,'__file__':__file__,'__doc__':__doc__}
for name in ('inspect_return','collect_return','load_return','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]


if __name__=='__main__':raise SystemExit(main())
