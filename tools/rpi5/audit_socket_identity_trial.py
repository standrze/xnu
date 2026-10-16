#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline exact command/root/socket replay, not Ethernet or SSH acceptance."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

try:
    from . import serial_socket_identity_trial as recorder
except ImportError:
    import serial_socket_identity_trial as recorder

core,t=recorder.core,recorder.t
CHECKS=['fresh_exact_payload_allows_identity_query_only',
        'runtime_readonly_mount_all_fixed_paths_and_self_digest','fresh_recovery_nonce',
        'preserved_original_zsh_script','socket_unix_payload_and_halfclose',
        'socket_inet_payload_and_halfclose','live_recovery']


def commands(nonce):
    return [core.IDENTITY_COMMAND,'echo '+nonce,'zsh -f /etc/zsh-smoke.zsh','echo $?',
        *["zsh -f -c '"+core.HELPER+' '+mode+"; print -r -- SOCKET_STATUS:$?'" for mode in ('unix','inet')],
        'echo RECOVERED_'+nonce]


def identity_command_content(segment,command):
    """Reconstruct only the first echo, retaining the raw file unchanged.

    The pre-input shell emits a readiness frame while a paced line is still
    arriving, and the kernel can print a watchdog kick mid-echo. Permit only
    those exact bounded notifications before zsh entry, never inside identity
    results or later commands. Everything else must match the exact command
    and four startup lines; this cannot hide arbitrary UART output.
    """
    marker=b'ROOTIDENTITY:BEGIN:FIXED_CATALOG_V1\n'
    if segment.count(marker)!=1: raise ValueError('Missing/duplicate identity start')
    prefix,content=segment.split(marker,1)
    readiness=b'\nRPI5XNU:SHELL:READY\nxnu:/# '
    if prefix.count(readiness)>4: raise ValueError('Excessive first-echo readiness')
    prefix=prefix.replace(readiness,b'')
    watchdog=rb'RPI5XNU:TERMINAL:WATCHDOG_KICK RELOADS=([1-9][0-9]{0,5})\n'
    notices=list(re.finditer(watchdog,prefix))
    if len(notices)>4 or [int(row[1]) for row in notices]!=sorted({int(row[1]) for row in notices}):
        raise ValueError('Invalid first-echo watchdog sequence')
    prefix=re.sub(watchdog,b'',prefix)
    startup=b'DARWIN:ZSH:ENTRY\nDARWIN:ZSH:TSD\nDARWIN:ZSH:ENTROPY\nDARWIN:ZSH:MAIN\n'
    if prefix not in (command.encode()+b'\n'+startup,command.encode()+b'\n\n'+startup):
        raise ValueError('First identity command echo/startup differs')
    return marker+content


def replay(state,raw,report,installed,receipt):
    if (state.get('status')!='passed' or state.get('checks')!=CHECKS or state.get('baud')!=115200 or
        not t.valid_probe_device(state.get('device','')) or state.get('preflight')!=report or
        state.get('installation')!=installed or type(state.get('bytes')) is not int or state['bytes']!=len(raw) or
        state.get('serial_sha256')!=hashlib.sha256(raw).hexdigest() or
        state.get('recorder_source_sha256')!=recorder.source_pins() or
        any(key in state for key in ('error','serial_restore_error')) or
        any(state.get(key) is not False for key in ('strict_historical_mount_marker_trial_waived','nic_ready','ssh','durability'))):
        raise ValueError('Changed/incomplete trial state or unsupported claim')
    if (report.get('image_sha256')!=recorder.staging.NEW_SHA or report.get('image_bytes')!=core.IMAGE_BYTES or
        report.get('init_sha256')!=recorder.package.INIT_SHA or
        report.get('kernel_sha256')!=recorder.package.old.metadata.KERNEL_SHA or
        receipt.get('output_sha256')!=recorder.package.INIT_SHA or report.get('preflight_pass') is not True or
        not report.get('checks') or any(value is not True for value in report['checks'].values())):
        raise ValueError('Wrong package binding')
    start,end=[datetime.fromisoformat(state[key]) for key in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0<=(end-start).total_seconds()<=4200:
        raise ValueError('Invalid bounded trial timestamps')
    nonce=state.get('nonce','')
    if not re.fullmatch('S[0-9a-f]{16}',nonce): raise ValueError('Missing nonce')
    sent=commands(nonce)
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes']!=sum(len(c)+1 for c in sent):
        raise ValueError('Unexpected TX extent')
    if not core.identity_query_ready(raw): raise ValueError('No exact fresh payload boot')
    data=t.normalized(raw)
    initial=t.shell.PROMPT.search(data,data.index(t.READY))
    if initial is None: raise ValueError('Missing initial prompt')
    cursor=initial.end(); identity_result=None; sockets=[]
    expected=[[b'ROOTIDENTITY:PASS:COMPARE_SELF_AND_EXTENT_EXTERNALLY',b'ROOT_IDENTITY_STATUS:0'],
              [nonce.encode()],t.SMOKE_LINES,[b'0'],
              [b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF',b'SOCKET_STATUS:0'],
              [b'SOCKETPROBE:END:NOT_ETHERNET_OR_SSH_PROOF',b'SOCKET_STATUS:0'],
              [('RECOVERED_'+nonce).encode()]]
    for index,(command,lines) in enumerate(zip(sent,expected)):
        if index==0:
            # Ignore no arbitrary prompts: only the fixed first-query notice
            # parser below may account for readiness frames during input.
            statuses=list(re.finditer(rb'(?m)^ROOT_IDENTITY_STATUS:0\n',data[cursor:]))
            if len(statuses)!=1: raise ValueError('Missing/duplicate identity exit')
            following=t.shell.PROMPT.search(data,cursor+statuses[0].end())
        else: following=t.shell.PROMPT.search(data,cursor)
        if following is None: raise ValueError('Missing subsequent recovery prompt')
        segment=data[cursor:following.start()]
        if index==0: content=identity_command_content(segment,command)
        else:
            if not segment.startswith(command.encode()+b'\n'): raise ValueError('Changed command echo/order')
            content=segment[len(command)+1:]
        positions=[]
        for line in lines:
            # The prompt regex consumes its preceding newline.
            matches=list(re.finditer(rb'(?m)^'+re.escape(line)+rb'\n',content+b'\n'))
            if len(matches)!=1: raise ValueError('Missing/duplicate actual output '+repr(line))
            positions.append(matches[0].start())
        if positions!=sorted(positions): raise ValueError('Output order differs')
        if index==0: identity_result=recorder.identity.validate(content,receipt)
        if index in (4,5): sockets.append(core.socket_result(content,'unix' if index==4 else 'inet'))
        cursor=following.end()
    if data[cursor:].strip(): raise ValueError('Unexpected final bytes')
    if state.get('runtime_identity')!=identity_result or state.get('socket_results')!=sockets:
        raise ValueError('Reported identity/socket results differ from raw bytes')
    return dict(status='socket_identity_transcript_audited',runtime_identity=identity_result,
                socket_results=sockets,serial_sha256=hashlib.sha256(raw).hexdigest(),
                original_zsh_script_passed=True,recovery_verified=True,
                nic_ready=False,ssh=False,durability=False,
                scope='Mounted RAM-root integrity and Unix/IPv4 loopback payload/half-close only')


def audit(directory):
    state_path=directory/'state.json'; state=json.loads(state_path.read_text()); raw=(directory/'serial.bin').read_bytes()
    report=recorder.package.inspect(Path(state['preflight']['image']).parent)
    installed=recorder.installation(Path(state['installation']['directory']),report)
    receipt=json.loads(recorder.package.INIT.with_name('manifest.json').read_text())
    result=replay(state,raw,report,installed,receipt)
    result.update(state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),installation=installed)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path); parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(); result=audit(args.directory)
    with args.report.open('x') as stream: json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps(result))


if __name__=='__main__': main()
