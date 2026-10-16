#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Offline audit of a completed raw-file diagnostic; no device/network access."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_statprobe_trial as trial
import serial_statprobe_followup as followup


def audit(directory):
    state_path = directory / 'state.json'
    state = json.loads(state_path.read_text())
    raw = (directory / 'serial.bin').read_bytes()
    same_boot = state.get('status') == 'same_boot_diagnostic_completed'
    expected_checks = followup.CHECKS if same_boot else trial.CHECKS
    if (state.get('status') not in ('diagnostic_completed', 'same_boot_diagnostic_completed')
            or state.get('checks') != expected_checks
            or state.get('script_file_acceptance') is not False or state.get('baud') != 115200
            or not trial.transport.valid_probe_device(state.get('device', ''))
            or state.get('bytes') != len(raw)
            or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or 'error' in state or 'serial_restore_error' in state):
        raise ValueError('Incomplete or changed diagnostic state/transcript')
    report = state.get('preflight', {})
    if (report.get('image_sha256') != trial.IMAGE_SHA or report.get('image_bytes') != 18057920
            or report.get('root_mount_marker', '').encode() != trial.ROOT_MARKER
            or report.get('init_sha256') != trial.package_check.INIT_SHA
            or report.get('kernel_sha256') != trial.package_check.KERNEL_SHA
            or report.get('preflight_pass') is not True or not report.get('checks')
            or any(value is not True for value in report['checks'].values())):
        raise ValueError('Wrong diagnostic package/preflight binding')
    start, end = [datetime.fromisoformat(state[key]) for key in ('started_utc', 'ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end - start).total_seconds() <= 3720:
        raise ValueError('Invalid bounded diagnostic timestamps')
    source = None
    if same_boot:
        source_path = Path(state.get('source', {}).get('directory', ''))
        if not source_path.resolve().is_relative_to(followup.staging.ROOT / 'build/rpi5'):
            raise ValueError('Source capture must be a local project build artifact')
        source = followup.evidence(source_path, state['device'], report, require_recent=False)
        original = json.loads((source_path / 'state.json').read_text())
        source_end = datetime.fromisoformat(original['ended_utc'])
        if (source != state.get('source') or state.get('strict_mounted_root_trial_passed') is not False
                or not 0 <= (start - source_end).total_seconds() <= 900):
            raise ValueError('Changed/expired same-boot source or incorrect root acceptance claim')
        if (any(marker in raw for marker in trial.transport.FORBIDDEN)
                or trial.transport.ENTRY in raw or trial.transport.TERMINAL_LOADER in raw
                or b'Boot mode:' in raw):
            raise ValueError('Reboot/fault in same-boot diagnostic')
    elif not trial.transport.boot_ready(raw, report['image_bytes'], trial.ROOT_MARKER):
        raise ValueError('Missing fresh exact-extent diagnostic boot')
    nonce = state.get('nonce', '')
    if not re.fullmatch(r'F[0-9a-f]{16}', nonce):
        raise ValueError('Missing fresh diagnostic nonce')
    commands = ['echo ' + nonce, '/bin/statprobe', 'echo $?', 'echo RECOVERED_' + nonce]
    if state['transmitted_bytes'] != sum(len(command) + 1 for command in commands):
        raise ValueError('Unexpected serial input extent')
    data = trial.transport.normalized(raw)
    def line(value, after):
        matches = list(re.finditer(rb'(?:^|\n)' + re.escape(value) + rb'\n', data[after:]))
        if len(matches) != 1:
            raise ValueError('Missing/repeated actual output line: ' + repr(value))
        return after + matches[0].end()
    position = 0 if same_boot else data.index(trial.transport.READY)
    position = line(nonce.encode(), position)
    position = line(trial.BEGIN, position)
    position = line(trial.END, position)
    position = line(b'0', position)
    position = line(('RECOVERED_' + nonce).encode(), position)
    if not trial.transport.shell.PROMPT.search(data[position:]):
        raise ValueError('Missing live recovery prompt after nonce')
    observations = trial.parse_diagnostic(raw)
    if state.get('observations') != observations:
        raise ValueError('Structured observations differ from raw capture')
    return dict(status='raw_file_diagnostic_audited', image_sha256=trial.IMAGE_SHA,
                serial_sha256=hashlib.sha256(raw).hexdigest(),
                state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
                observations=observations, pi_raw_diagnostic_completed=True, source=source,
                strict_mounted_root_trial_passed=not same_boot,
                mounted_root_node_count_observed=not same_boot,
                original_zsh_script_acceptance=False, abi_root_cause_proven=False,
                full_gate6_exit=False, networking=False, durability=False,
                scope=('Separate same-boot raw diagnosis with verified loader-copy source; strict root trial remains failed'
                       if same_boot else 'Fresh exact root boot, raw observations and live recovery; not an ABI fix'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(audit(args.directory), indent=2) + '\n'
    if args.report:
        with args.report.open('x') as output:
            output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
