#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct 41-node raw replay and independently verified NVMe return adapter."""
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_root96_trial as original
import serial_root41_trial as recorder
import root41_batch_evidence as command_evidence
core,t,stage=recorder.core,recorder.t,recorder.staging
identity_audit,return_program=original.identity_audit,original.return_program


def return_source_pins():
    return recorder.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
        (sys.modules[__name__],original,command_evidence,identity_audit,return_program)}


def replay(state,raw,report,installed,receipt):
    if (state.get('status')!='passed' or state.get('preflight')!=report or state.get('installation')!=installed or
        state.get('source_sha256')!=recorder.source_pins() or state.get('baud')!=115200 or
        not t.valid_probe_device(state.get('device','')) or any(k in state for k in ('error','serial_restore_error')) or
        any(state.get(k) is not False for k in ('independent_linux_return_verified','ssh_daemon','networking','controller_initialized','durability')) or
        any(state.get(k) is not True for k in ('command_tests_passed','normal_nvme_boot_observed')) or
        state.get('package_evidence_sha256')!=recorder.package_evidence_pins(Path(report['image']).parent)):
        raise ValueError('Incomplete/changed 41-node serial trial state')
    start,end=[datetime.fromisoformat(state[k]) for k in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0<(end-start).total_seconds()<840:
        raise ValueError('Bounded zoned trial timestamps required')
    duration=state.get('return_seconds_after_admission')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 120<duration<225:
        raise ValueError('Bounded delayed-readiness return time differs')
    files=recorder.root_profile.files_from((Path(report['root_manifest']).parent/'ramdisk.bin').read_bytes())
    result=command_evidence.replay_commands(state,raw,report,receipt,files)
    if not core.returned(raw[result['command_end_offset']:]):raise ValueError('No complete bounded normal NVMe serial return')
    return dict(result,status='root41_serial_replayed',serial_sha256=hashlib.sha256(raw).hexdigest(),
        normal_nvme_serial_boot=True,independent_linux_return_verified=False,controller_initialized=False,durability=False)


def load_capture(directory):
    result=_load_capture(directory)
    path=local_child(directory)
    state=json.loads((path/'state.json').read_text());armed=json.loads((path/'armed.json').read_text())
    if armed.get('package_evidence_sha256')!=state.get('package_evidence_sha256'):
        raise ValueError('Armed exact package closure changed')
    return result


_bindings=dict(original.__dict__,recorder=recorder,core=core,t=t,stage=stage,replay=replay,
               return_source_pins=return_source_pins,load_capture=load_capture,__doc__=__doc__)
for _name in ('local_child','inspect_return','audit','main'):
    _f=getattr(original,_name)
    globals()[_name]=types.FunctionType(_f.__code__,_bindings,argdefs=_f.__defaults__)
    _bindings[_name]=globals()[_name]
_load_capture=types.FunctionType(original.load_capture.__code__,_bindings)


if __name__=='__main__':raise SystemExit(main())
