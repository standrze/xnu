#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Replay the corrective zsh capture offline; no serial, media or network I/O."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_zsh_metadata_trial as trial


def commands(nonce):
    return ['echo '+nonce,'/bin/statprobe','echo $?','zsh -f /etc/zsh-smoke.zsh','echo $?',
            trial.t.LAUNCH,'print -r -- "PI_ZSH:$ZSH_VERSION"',
            'a=(pi xnu); print -r -- "PI_BUILTINS:${a[2]}:$((6*7))"',
            '/bin/echo PI_EXEC_'+nonce,'exit','echo RECOVERED_'+nonce]


def replay(state, raw, report, installed, files):
    """Recheck raw output and semantics; status/check fields alone never suffice."""
    if (state.get('status') != 'passed' or state.get('checks') != trial.CHECKS
            or state.get('script_file_acceptance') is not True or state.get('baud') != 115200
            or not trial.t.valid_probe_device(state.get('device',''))
            or state.get('preflight') != report or state.get('installation') != installed
            or type(state.get('bytes')) is not int or state['bytes'] != len(raw)
            or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or any(key in state for key in ('error','serial_restore_error'))
            or any(state.get(key) is not False for key in ('full_gate6_exit','networking','durability'))):
        raise ValueError('Incomplete/changed corrective trial state or unsupported broader claim')
    if (report.get('image_sha256') != trial.IMAGE_SHA or report.get('image_bytes') != trial.IMAGE_BYTES
            or report.get('root_mount_marker','').encode() != trial.ROOT_MARKER
            or report.get('kernel_sha256') != trial.package_check.KERNEL_SHA
            or report.get('init_sha256') != trial.package_check.previous.INIT_SHA
            or report.get('preflight_pass') is not True or not report.get('checks')
            or any(value is not True for value in report['checks'].values())):
        raise ValueError('Wrong corrective package binding')
    start,end = [datetime.fromisoformat(state[key]) for key in ('started_utc','ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end-start).total_seconds() <= 4200:
        raise ValueError('Invalid bounded trial timestamps')
    nonce = state.get('nonce','')
    if not re.fullmatch(r'Z[0-9a-f]{16}',nonce):
        raise ValueError('Missing exact fresh nonce')
    if (type(state.get('transmitted_bytes')) is not int
            or state['transmitted_bytes'] != sum(len(command)+1 for command in commands(nonce))):
        raise ValueError('Unexpected serial input extent')
    if not trial.boot_ready(raw):
        raise ValueError('Missing exact fresh corrective copy/mounted-root boot')
    data = trial.t.normalized(raw)
    initial = trial.t.shell.PROMPT.search(data,data.index(trial.t.READY))
    if initial is None: raise ValueError('Missing initial recovery prompt')
    cursor = initial.end()
    def response(expected, prompt, counts=None):
        nonlocal cursor
        counts = counts or [1]*len(expected)
        ends = []
        for value,count in zip(expected,counts):
            matches = list(re.finditer(rb'(?m)^'+re.escape(value)+rb'\n',data[cursor:]))
            if len(matches) < count:
                raise ValueError('Missing actual output: '+repr(value))
            ends.append(cursor+matches[count-1].end())
        if ends != sorted(ends): raise ValueError('Actual output lines out of order')
        following = prompt.search(data,cursor)
        prompt_start = following.start() if following else -1
        if following and data[prompt_start:prompt_start+1] == b'\n': prompt_start += 1
        if following is None or max(ends,default=cursor) > prompt_start:
            raise ValueError('Missing correct subsequent prompt or premature prompt')
        segment = data[cursor:following.end()]
        for value,count in zip(expected,counts):
            if len(re.findall(rb'(?m)^'+re.escape(value)+rb'\n',segment)) != count:
                raise ValueError('Repeated actual output within command response')
        cursor = following.end()
        return segment
    response([nonce.encode()],trial.t.shell.PROMPT)
    diagnostic = response([trial.diagnostic.BEGIN,trial.diagnostic.END],trial.t.shell.PROMPT)
    observations = trial.diagnostic.parse_diagnostic(diagnostic)
    # Parsing the full capture also rejects extra statprobe fields outside the
    # one allowed response; returned observations must equal the actual bytes.
    if (trial.diagnostic.parse_diagnostic(raw) != observations
            or state.get('observations') != observations):
        raise ValueError('Claimed raw observations differ from captured diagnostic')
    acceptance = trial.accept_metadata(observations,files)
    if state.get('metadata_acceptance') != acceptance:
        raise ValueError('Claimed metadata acceptance differs from raw replay')
    response([b'0'],trial.t.shell.PROMPT)
    response(trial.t.SMOKE_LINES,trial.t.shell.PROMPT)
    response([b'0'],trial.t.shell.PROMPT)
    zprompt = re.compile(re.escape(trial.t.ZPROMPT))
    response([b'DARWIN:ZSH:MAIN'],zprompt,[2])
    response([b'PI_ZSH:5.9'],zprompt)
    response([b'PI_BUILTINS:xnu:42'],zprompt)
    response([('PI_EXEC_'+nonce).encode()],zprompt)
    response([],trial.t.shell.PROMPT)
    response([('RECOVERED_'+nonce).encode()],trial.t.shell.PROMPT)
    if data[cursor:].strip():
        raise ValueError('Unexpected output after final recovered prompt')
    return dict(status='corrective_zsh_transcript_audited',image_sha256=trial.IMAGE_SHA,
                serial_sha256=hashlib.sha256(raw).hexdigest(),observations=observations,
                metadata_acceptance=acceptance,original_zsh_script_acceptance=True,
                interactive_zsh_and_recovery_acceptance=True,strict_mounted_root_trial_passed=True,
                abi_root_cause_proven=False,full_gate6_exit=False,networking=False,durability=False,
                scope='Captured fixed-path metadata, original script and interactive/recovery evidence only')


def audit(directory):
    state_path = directory/'state.json'
    state = json.loads(state_path.read_text())
    raw = (directory/'serial.bin').read_bytes()
    report = trial.package_check.inspect(Path(state['preflight']['image']).parent)
    installed = trial.installation(Path(state['installation']['directory']),report)
    files = trial.files_from(trial.package_check.previous.INIT.read_bytes())
    result = replay(state,raw,report,installed,files)
    result.update(state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),installation=installed)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    encoded = json.dumps(audit(args.directory),indent=2)+'\n'
    if args.report:
        with args.report.open('x') as output: output.write(encoded)
    print(encoded,end='')


if __name__ == '__main__':
    main()
