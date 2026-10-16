#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Replay same-boot Apple-tool diagnosis; strict mount trial remains failed."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

try:
    from . import serial_apple_network_followup as followup
    from . import audit_apple_network_trial as strict
except ImportError:
    import serial_apple_network_followup as followup
    import audit_apple_network_trial as strict

trial,t = followup.trial,followup.t


def replay(state,raw,report,installed,source,source_state):
    if (state.get('status') != 'diagnostic_completed' or
            state.get('checks') != [followup.ADMISSION]+trial.CHECKS[1:] or
            state.get('preflight') != report or state.get('installation') != installed or
            state.get('source') != source or state.get('baud') != 115200 or
            not t.valid_probe_device(state.get('device','')) or
            type(state.get('bytes')) is not int or state['bytes'] != len(raw) or
            state.get('serial_sha256') != hashlib.sha256(raw).hexdigest() or
            any(key in state for key in ('error','serial_restore_error')) or
            any(state.get(key) is not False for key in ('networking','nic_ready','ssh','durability',
                'strict_mounted_root_trial_passed','mounted_root_node_count_observed'))):
        raise ValueError('Incomplete diagnostic binding or unsupported stronger claim')
    start,end,prior_end = [datetime.fromisoformat(value) for value in
                           (state['started_utc'],state['ended_utc'],source_state['ended_utc'])]
    if any(value.tzinfo is None for value in (start,end,prior_end)) or not 0 <= (start-prior_end).total_seconds() <= 900 or not 0 <= (end-start).total_seconds() <= 300:
        raise ValueError('Diagnostic timestamps exceed bounds')
    nonce = state.get('nonce','')
    if not re.fullmatch('N[0-9a-f]{16}',nonce): raise ValueError('Missing fresh diagnostic nonce')
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != sum(len(c)+1 for c in strict.commands(nonce)):
        raise ValueError('Unexpected TX extent')
    data = t.normalized(raw)
    if (t.ENTRY in data or t.TERMINAL_LOADER in data or b'Boot mode:' in data or
            any(marker in data for marker in t.FORBIDDEN)):
        raise ValueError('Intervening reboot/fault in diagnostic capture')
    # The repeated idle readiness banner can split the first command's UART
    # echo. Require one actual nonce output and a subsequent live prompt;
    # every remaining command echo and output is replayed exactly.
    matches = list(re.finditer(rb'(?m)^'+nonce.encode()+rb'\n',data))
    if len(matches) != 1: raise ValueError('Missing/duplicate actual nonce response')
    prompt = t.shell.PROMPT.search(data,matches[0].end())
    if prompt is None: raise ValueError('No live prompt after nonce')
    names = strict.responses(data,prompt.end(),nonce,start=1)
    if names != state.get('interface_names'): raise ValueError('Interface observations differ')
    result = strict.result(raw,names)
    result.update(status='same_boot_apple_network_diagnosis_audited',source=source,
                  strict_mounted_root_trial_passed=False,mounted_root_node_count_observed=False,
                  command_echoes_verified_after_nonce=True,
                  scope='Separate captured original Apple utility diagnosis; strict fresh-mount trial remains failed')
    return result


def audit(directory):
    state_path = directory/'state.json'; state = json.loads(state_path.read_text())
    raw = (directory/'serial.bin').read_bytes()
    report = trial.package_check.inspect(Path(state['preflight']['image']).parent)
    installed = trial.installation(Path(state['installation']['directory']),report)
    source_dir = Path(state['source']['directory'])
    source = followup.evidence(source_dir,state['device'],report,installed,require_recent=False)
    source_state = json.loads((source_dir/'state.json').read_text())
    result = replay(state,raw,report,installed,source,source_state)
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
