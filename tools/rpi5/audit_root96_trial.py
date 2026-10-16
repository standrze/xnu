#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Replay bounded root96 UART proof, then optionally collect one Linux witness."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_root96_trial as recorder
import audit_socket_identity_trial as identity_audit
import capture_pcie_fw_reuse_linux_return as return_program
core,t,stage=recorder.core,recorder.t,recorder.staging


def replay(state,raw,report,installed,receipt):
    if (state.get('status')!='passed' or state.get('checks')!=core.CHECKS or state.get('baud')!=115200 or
        not t.valid_probe_device(state.get('device','')) or state.get('preflight')!=report or
        state.get('installation')!=installed or type(state.get('bytes')) is not int or state['bytes']!=len(raw) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or state.get('source_sha256')!=recorder.source_pins() or
        any(k in state for k in ('error','serial_restore_error')) or
        any(state.get(k) is not False for k in ('independent_linux_return_verified','ssh_daemon','networking','controller_initialized','durability')) or
        any(state.get(k) is not True for k in ('command_tests_passed','normal_nvme_boot_observed'))):
        raise ValueError('Incomplete or changed root96 serial state')
    start,end=[datetime.fromisoformat(state[k]) for k in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0<(end-start).total_seconds()<840:
        raise ValueError('Invalid bounded trial clock')
    for key,low,high in (('commands_complete_seconds_after_admission',0,120),('return_seconds_after_admission',120,225)):
        v=state.get(key)
        if type(v) not in (int,float) or not math.isfinite(v) or not low<v<high:raise ValueError('Bounded terminal deadline differs')
    nonce=state.get('nonce','')
    if not re.fullmatch('R[0-9a-f]{16}',nonce):raise ValueError('Fresh nonce missing')
    sent=[core.IDENTITY,'echo '+nonce,core.SMOKE,core.BUFFER,'echo RECOVERED_'+nonce]
    names=['identity','nonce','zsh','buffer','recovery']
    expected=[[b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'],
              [nonce.encode()],t.SMOKE_LINES+[b'ROOT96_ZSH_STATUS:0'],
              [core.BEGIN,core.PASS,b'ROOT96_SSHBUFFER_STATUS:0'],[('RECOVERED_'+nonce).encode()]]
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=sum(len(c)+1 for c in sent):
        raise ValueError('Unexpected UART TX extent')
    exchanges=state.get('exchanges',[])
    if len(exchanges)!=5:raise ValueError('Incomplete actual exchanges')
    cursor=exchanges[0].get('pending_offset')
    if type(cursor) is not int or not 0<cursor<len(raw) or not core.boot_ready(raw[:cursor],report):
        raise ValueError('No exact bounded startup before first TX')
    runtime=None
    for i,(row,command,lines,name) in enumerate(zip(exchanges,sent,expected,names)):
        pending_length=row.get('pending_bytes')
        if row.get('pending_offset')!=cursor or type(pending_length) is not int or not 0<=pending_length<=65536:
            raise ValueError('Pending receive range differs')
        pending=raw[cursor:cursor+pending_length];cursor+=pending_length
        if row.get('pending_sha256')!=hashlib.sha256(pending).hexdigest():raise ValueError('Pending receive bytes differ')
        core.pending_safe(pending)
        length=row.get('bytes')
        if (row.get('offset')!=cursor or type(length) is not int or not 0<length<=t.MAX_BYTES or
            cursor+length>len(raw) or row.get('name')!=name or row.get('command')!=command):
            raise ValueError('Actual command ranges/order differ')
        chunk=raw[cursor:cursor+length];cursor+=length
        if row.get('response_sha256')!=hashlib.sha256(chunk).hexdigest():raise ValueError('Actual response bytes differ')
        data=t.normalized(chunk)
        # The first paced echo may contain only the accepted readiness/kick frames.
        if i==0:
            status=list(re.finditer(rb'(?m)^ROOT_IDENTITY_STATUS:0\n',data))
            if len(status)!=1:raise ValueError('Identity status differs')
            prompt=t.shell.PROMPT.search(data,status[0].end())
        else:prompt=t.shell.PROMPT.search(data)
        if prompt is None or data[prompt.end():].strip():raise ValueError('Command completion prompt differs')
        segment=data[:prompt.start()]
        if i==0:content=identity_audit.identity_command_content(segment,command)
        else:
            if not segment.startswith(command.encode()+b'\n'):raise ValueError('Command echo differs')
            content=segment[len(command)+1:]
        core.exact_lines(content,lines)
        if any(m in content for m in t.FORBIDDEN) or b'RPI5XNU:SSHBUFFER:FAIL' in content:raise ValueError('Failed command output')
        if i==0:runtime=core.identity.validate(content,receipt)
    if state.get('return_capture_offset')!=cursor or not core.returned(raw[cursor:]):
        raise ValueError('No exact automatic normal NVMe return after commands')
    if state.get('runtime_identity')!=runtime:raise ValueError('Reported root identity differs from bytes')
    return dict(status='root96_serial_replayed',serial_sha256=hashlib.sha256(raw).hexdigest(),runtime_identity=runtime,
        original_zsh_script_passed=True,ssh_buffer_roundtrip_reset_reuse_passed=True,normal_nvme_serial_boot=True,
        ssh_daemon=False,networking=False,controller_initialized=False,durability=False)


def local_child(path):
    path=path.resolve()
    if path.parent!=stage.ROOT/'build/rpi5':raise ValueError('Exact local evidence directory required')
    return path


def load_capture(directory):
    directory=local_child(directory);state=json.loads((directory/'state.json').read_text())
    report=recorder.package.inspect(Path(state['preflight']['image']).parent)
    installed=recorder.installation(Path(state['installation']['directory']),report)
    plan=json.loads((Path(installed['directory'])/'plan.json').read_text())
    armed=json.loads((directory/'armed.json').read_text())
    for key in ('device','baud','preflight','installation','source_sha256','receipt_evidence_sha256','started_utc','pid','armed_utc','armed_monotonic'):
        if armed.get(key)!=state.get(key):raise ValueError('Armed recorder binding differs')
    if armed.get('transmitted_bytes')!=0 or armed.get('checks')!=[] or armed.get('exchanges')!=[]:
        raise ValueError('Recorder was not armed at zero TX')
    if state.get('receipt_evidence_sha256')!=recorder.receipt_evidence_pins(Path(installed['directory'])):
        raise ValueError('Historical receipt byte pins changed')
    receipt=json.loads(Path(report['root_manifest']).read_text())
    observation=replay(state,(directory/'serial.bin').read_bytes(),report,installed,receipt)
    return plan,installed,observation


def return_source_pins():
    return recorder.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
        (sys.modules[__name__],identity_audit,return_program)}


def inspect_return(returned,plan,installed,observed):
    boot=returned.get('boot_id','')
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot) or boot==plan['linux_boot_id']:
        raise ValueError('Distinct post-trial Linux boot required')
    expected=dict(host=plan['host'],boot_id=boot,
        identity=dict(identity=plan['identity_binding']['expected'],boot_id=boot,hostname='kamidana'),
        root=plan['identity_binding']['expected']['root'].split(),
        bootloader={'boot-mode':6,'partition':1,'tryboot':0},sd_partitions_unmounted=True,read_only=True,
        installation=installed,serial_sha256=observed['serial_sha256'],return_source_sha256=return_source_pins())
    if any(not stage.base.reference.same(returned.get(k),v) for k,v in expected.items()):raise ValueError('Independent Linux return differs')
    timestamp=datetime.fromisoformat(returned['observed_utc'])
    if timestamp.tzinfo is None:raise ValueError('Linux observation needs UTC')
    program=return_program.remote_source(plan,installed,observed['serial_sha256'],return_source_pins())
    if 'remote_program_sha256' in returned and returned['remote_program_sha256']!=hashlib.sha256(program.encode()).hexdigest():
        raise ValueError('Read-only collector program changed')
    return boot


def audit(directory,require_linux=True):
    plan,installed,observed=load_capture(directory)
    if require_linux:
        returned=json.loads((directory/'linux-return.json').read_text())
        observed['linux_boot_id']=inspect_return(returned,plan,installed,observed)
        observed['independent_linux_return_verified']=True
    return observed


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path)
    p.add_argument('--collect-linux-return',action='store_true');p.add_argument('--serial-only',action='store_true')
    args=p.parse_args(argv);directory=local_child(args.capture)
    if args.collect_linux_return:
        target=directory/'linux-return.json'
        if target.exists() or target.is_symlink():raise ValueError('Return evidence exists; never overwrite')
        with recorder.lease.hold(stage.ROOT,'root96-independent-linux-return'):
            plan,installed,observed=load_capture(directory);pins=return_source_pins()
            program=return_program.remote_source(plan,installed,observed['serial_sha256'],pins)
            r=subprocess.run(stage.SSH+['sudo -n python3 -'],input=program,text=True,capture_output=True,timeout=60)
            r.check_returncode();returned=json.loads(r.stdout);inspect_return(returned,plan,installed,observed)
            if return_source_pins()!=pins or load_capture(directory)!=(plan,installed,observed):raise ValueError('Trial inputs changed during observation')
            returned['remote_program_sha256']=hashlib.sha256(program.encode()).hexdigest()
            with target.open('x') as f:json.dump(returned,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    print(json.dumps(audit(directory,not args.serial_only),indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
