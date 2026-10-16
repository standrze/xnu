#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline audit of same-boot interactive zsh; preserves the script failure."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_zsh_trial as trial
import stage_zsh_trial as stage

CHECKS = ['same_boot_live_recovery_shell_nonce', 'interactive_zsh_fixed_prompt',
          'interactive_version_builtins_external_exec_returned_prompt', 'interactive_exit_live_recovery_shell']


def validate(raw, state):
    if (state.get('status') != 'interactive_diagnostic_completed' or state.get('checks') != CHECKS
            or state.get('script_file_acceptance') is not False or state.get('device') != '/dev/cu.usbmodem102'
            or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != 273
            or state.get('bytes') != len(raw) or not 0 < len(raw) <= 65536
            or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or not re.fullmatch('D[0-9a-f]{16}', state.get('nonce', ''))):
        raise ValueError('Complete exact interactive diagnostic state and raw capture required')
    data = trial.normalized(raw)
    if trial.ENTRY in data or trial.TERMINAL_LOADER in data or any(x in data for x in trial.FORBIDDEN):
        raise ValueError('Failure or reboot in interactive diagnostic')
    if data.count(trial.LAUNCH.encode()) != 1 or any(data.count(x + b'\n') != 2 for x in
        (b'DARWIN:ZSH:ENTRY', b'DARWIN:ZSH:TSD', b'DARWIN:ZSH:ENTROPY', b'DARWIN:ZSH:MAIN')):
        raise ValueError('Exactly one launcher/interactive pair required')
    nonce = state['nonce'].encode()
    outputs = [nonce, b'PI_ZSH:5.9', b'PI_BUILTINS:xnu:42', b'PI_EXEC_' + nonce, b'RECOVERED_' + nonce]
    matches = []
    for value in outputs:
        found = list(re.finditer(rb'(?:^|\n)' + re.escape(value) + rb'\n', data))
        if len(found) != 1:
            raise ValueError('Missing/duplicate exact computed output, not echoed command: ' + repr(value))
        matches.append(found[0])
    if [m.start() for m in matches] != sorted(m.start() for m in matches):
        raise ValueError('Interactive outputs out of order')
    launch = data.index(trial.LAUNCH.encode())
    if not matches[0].end() < launch < matches[1].start():
        raise ValueError('Recovery handshake must precede interactive launch/version')
    for index in (1, 2, 3):
        if trial.ZPROMPT not in data[matches[index].end():matches[index + 1].start()]:
            raise ValueError('Interactive output lacks subsequent returned zsh prompt')
    if trial.ZPROMPT not in data[launch:matches[1].start()] or not trial.shell.PROMPT.search(data[matches[-1].end():]):
        raise ValueError('Initial zsh or final live recovery prompt missing')
    return dict(status='interactive_zsh_diagnostic_passed', version='5.9',
                array_and_arithmetic='xnu:42', external_exec_fresh_nonce=True,
                interactive_prompts_returned=True, exited_to_live_recovery_shell=True,
                script_file_acceptance=False, full_gate6_complete=False,
                networking_proven=False, durability_proven=False,
                scope='Actual Pi interactive zsh subset; original script-file failure remains unresolved')


def audit(capture, failed, installed, package):
    state = json.loads((capture / 'state.json').read_text())
    raw = (capture / 'serial.bin').read_bytes()
    report = validate(raw, state)
    prior = json.loads((failed / 'state.json').read_text())
    prior_raw = (failed / 'serial.bin').read_bytes()
    prior_sha = hashlib.sha256(prior_raw).hexdigest()
    if (prior.get('status') != 'failed' or prior.get('serial_sha256') != prior_sha
            or state.get('prior_serial_sha256') != prior_sha or prior.get('bytes') != len(prior_raw)
            or prior.get('transmitted_bytes') != 49 or not trial.boot_ready(prior_raw, 18008768)
            or b"zsh: can't open input file: /etc/zsh-smoke.zsh\n" not in trial.normalized(prior_raw)):
        raise ValueError('Original failed boot must remain intact and explicitly linked')
    plan = json.loads((installed / 'plan.json').read_text())
    result = json.loads((installed / 'result.json').read_text())
    stage.validate_result(result, plan)
    package_report = trial.package_check.inspect(package)
    if package_report['image_sha256'] != result['image_sha256'] or prior['preflight'] != package_report:
        raise ValueError('Boot/package/install identity differs')
    times = [datetime.fromisoformat(x) for x in
             (prior['started_utc'], (installed / 'reboot.log').read_text().splitlines()[0].replace('Z','+00:00'),
              prior['ended_utc'], state['started_utc'], state['ended_utc'])]
    if times != sorted(times) or not 0 <= (times[3] - times[2]).total_seconds() <= 900:
        raise ValueError('Recorder/reboot/same-boot diagnostic chronology differs')
    report.update(image_sha256=result['image_sha256'], serial_sha256=hashlib.sha256(raw).hexdigest(),
                  prior_failed_serial_sha256=prior_sha, installer_result_sha256=trial.package_check.terminal.sha256(installed / 'result.json'),
                  nonce=state['nonce'], started_utc=state['started_utc'], ended_utc=state['ended_utc'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'failed-trial', 'installed', 'package'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True, help='New report, never overwrite')
    args = parser.parse_args()
    report = audit(args.capture, args.failed_trial, args.installed, args.package)
    encoded = json.dumps(report, indent=2, sort_keys=True) + '\n'
    with args.report.open('x') as output: output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__': main()
