#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline replay of original Apple networking utility results, not NIC proof."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

try:
    from . import serial_apple_network_trial as trial
except ImportError:
    import serial_apple_network_trial as trial


def commands(nonce):
    return ['echo '+nonce,'zsh -f /etc/zsh-smoke.zsh','echo $?',
            trial.IFCONFIG,trial.ROUTE,'echo RECOVERED_'+nonce]


def replay(state,raw,report,installed):
    if (state.get('status') != 'passed' or state.get('checks') != trial.CHECKS or
            state.get('baud') != 115200 or not trial.t.valid_probe_device(state.get('device','')) or
            state.get('preflight') != report or state.get('installation') != installed or
            type(state.get('bytes')) is not int or state['bytes'] != len(raw) or
            state.get('serial_sha256') != hashlib.sha256(raw).hexdigest() or
            any(key in state for key in ('error','serial_restore_error')) or
            any(state.get(key) is not False for key in ('networking','nic_ready','ssh','durability'))):
        raise ValueError('Changed/incomplete trial state or unsupported broader claim')
    if (report.get('image_sha256') != trial.staging.NEW_SHA or
            report.get('image_bytes') != trial.IMAGE_BYTES or
            report.get('init_sha256') != trial.package_check.INIT_SHA or
            report.get('kernel_sha256') != trial.package_check.metadata.KERNEL_SHA or
            report.get('root_mount_marker','').encode() != trial.ROOT_MARKER or
            report.get('preflight_pass') is not True or not report.get('checks') or
            any(value is not True for value in report['checks'].values())):
        raise ValueError('Wrong package binding')
    start,end = [datetime.fromisoformat(state[key]) for key in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end-start).total_seconds() <= 4200:
        raise ValueError('Invalid bounded trial timestamps')
    nonce = state.get('nonce','')
    if not re.fullmatch(r'N[0-9a-f]{16}',nonce): raise ValueError('Missing fresh nonce')
    sent = commands(nonce)
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != sum(len(c)+1 for c in sent):
        raise ValueError('Unexpected serial TX extent')
    if not trial.boot_ready(raw): raise ValueError('No strict fresh mounted boot')
    data = trial.t.normalized(raw)
    initial = trial.t.shell.PROMPT.search(data,data.index(trial.t.READY))
    if initial is None: raise ValueError('Missing initial recovery prompt')
    names = responses(data,initial.end(),nonce)
    if state.get('interface_names') != names:
        raise ValueError('Mismatching interface observations')
    return result(raw,names)


def responses(data,cursor,nonce,start=0):
    sent = commands(nonce)
    expected = [[nonce.encode()],trial.t.SMOKE_LINES,[b'0'],[b'NET_IFCONFIG_STATUS:0'],
                [trial.USAGE,b'NET_ROUTE_STATUS:64'],[('RECOVERED_'+nonce).encode()]]
    names = None
    for index,(command,lines) in enumerate(list(zip(sent,expected))[start:],start=start):
        following = trial.t.shell.PROMPT.search(data,cursor)
        if following is None: raise ValueError('Missing subsequent recovery prompt')
        segment = data[cursor:following.start()]
        # UART echoes the exact command before output. This also rejects a
        # capture of a different utility mode with forged result markers.
        if not segment.startswith(command.encode()+b'\n'):
            raise ValueError('Missing or changed exact command echo')
        content = segment[len(command)+1:]
        positions = []
        for line in lines:
            matches = list(re.finditer(rb'(?m)^'+re.escape(line)+rb'\n',content+b'\n'))
            if len(matches) != 1: raise ValueError('Missing/duplicate actual output: '+repr(line))
            positions.append(matches[0].start())
        if positions != sorted(positions): raise ValueError('Actual output order differs')
        if index == 3: names = trial.interfaces(content+b'\n')
        cursor = following.end()
    if data[cursor:].strip(): raise ValueError('Unexpected final bytes')
    return names


def result(raw,names):
    return dict(status='apple_network_command_transcript_audited',
                image_sha256=trial.staging.NEW_SHA,serial_sha256=hashlib.sha256(raw).hexdigest(),
                interface_names=names,original_zsh_script_passed=True,
                original_ifconfig_names_exit_zero=True,original_route_socket_usage_exit_64=True,
                recovery_verified=True,networking=False,nic_ready=False,ssh=False,durability=False,
                scope='Original command enumeration/PF_ROUTE usage path only; no address/route changes or packet traffic')


def audit(directory):
    state_path = directory/'state.json'; raw = (directory/'serial.bin').read_bytes()
    state = json.loads(state_path.read_text())
    report = trial.package_check.inspect(Path(state['preflight']['image']).parent)
    installed = trial.installation(Path(state['installation']['directory']),report)
    result = replay(state,raw,report,installed)
    result.update(state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),installation=installed)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path); parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args(); result = audit(args.directory)
    with args.report.open('x') as output:
        json.dump(result,output,indent=2,sort_keys=True); output.write('\n')
    print(json.dumps(result))


if __name__ == '__main__': main()
