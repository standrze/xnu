#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit same-boot read-only diagnostic of the preserved zsh script failure."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import re
import sys
import termios

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_zsh_trial as trial
from prepare_zsh_trial_root import SMOKE


def evidence(directory, device):
    state = json.loads((directory / 'state.json').read_text())
    raw = (directory / 'serial.bin').read_bytes()
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(state['ended_utc'])).total_seconds()
    if (state.get('status') != 'failed' or state.get('device') != device or not 0 <= age <= 900
            or state.get('checks') != ['fresh_exact_extent_distinct_ramroot_shell_boot', 'recovery_shell_fresh_nonce']
            or state.get('transmitted_bytes') != 49 or state.get('bytes') != len(raw)
            or hashlib.sha256(raw).hexdigest() != state.get('serial_sha256')
            or state.get('preflight', {}).get('image_sha256') != 'b3db210c0a880688bfda783e306fb6ad3473431d9a9cc68e25035d3c8fc32fd0'
            or not trial.boot_ready(raw, 18008768)
            or b"zsh: can't open input file: /etc/zsh-smoke.zsh\n" not in trial.normalized(raw)):
        raise ValueError('Requires recent exact failed zsh boot and preserved transcript')
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    parser.add_argument('--failed-trial', type=Path, required=True)
    parser.add_argument('--interactive-only', action='store_true',
                        help='Separate same-boot interactive diagnosis; never waives the script failure')
    args = parser.parse_args()
    if not trial.valid_probe_device(args.device): parser.error('Expected Debug Probe device')
    source = evidence(args.failed_trial, args.device)
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='failed', started_utc=trial.utc_now(), device=args.device, baud=115200,
                 transmitted_bytes=0, checks=[], prior_serial_sha256=source['serial_sha256'],
                 scope='Explicit same-boot file/ABI diagnostic; not a new zsh acceptance or reboot')
    fd, original = None, None
    try:
        fd = os.open(args.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        config = termios.tcgetattr(fd)
        config[0] = config[1] = config[3] = 0
        config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        config[4] = config[5] = termios.B115200
        config[6][termios.VMIN] = config[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, config)
        with (args.output / 'serial.bin').open('xb', buffering=0) as output:
            nonce = 'D' + secrets.token_hex(8)
            trial.exchange(fd, output, 'echo ' + nonce, [nonce.encode()], trial.shell.PROMPT, state)
            state['checks'].append('same_boot_live_recovery_shell_nonce')
            if args.interactive_only:
                state['scope'] = 'Separate same-boot interactive diagnosis; script-file acceptance remains failed'
                prompt = re.compile(re.escape(trial.ZPROMPT))
                launched = trial.exchange(fd, output, trial.LAUNCH, [b'DARWIN:ZSH:MAIN'], prompt, state)
                if trial.normalized(launched).count(b'DARWIN:ZSH:MAIN\n') != 2:
                    raise RuntimeError('Expected exactly two zsh startup traces')
                state['checks'].append('interactive_zsh_fixed_prompt')
                trial.exchange(fd, output, 'print -r -- "PI_ZSH:$ZSH_VERSION"', [b'PI_ZSH:5.9'], prompt, state)
                trial.exchange(fd, output, 'a=(pi xnu); print -r -- "PI_BUILTINS:${a[2]}:$((6*7))"',
                               [b'PI_BUILTINS:xnu:42'], prompt, state)
                trial.exchange(fd, output, '/bin/echo PI_EXEC_' + nonce, [('PI_EXEC_' + nonce).encode()], prompt, state)
                state['checks'].append('interactive_version_builtins_external_exec_returned_prompt')
                trial.exchange(fd, output, 'exit', [], trial.shell.PROMPT, state)
                trial.exchange(fd, output, 'echo RECOVERED_' + nonce, [('RECOVERED_' + nonce).encode()], trial.shell.PROMPT, state)
                state['checks'].append('interactive_exit_live_recovery_shell')
                state['nonce'] = nonce
                state['script_file_acceptance'] = False
                state['status'] = 'interactive_diagnostic_completed'
                return 0
            trial.exchange(fd, output, 'ls /etc', [b'zsh-smoke.zsh', b'terminfo/'], trial.shell.PROMPT, state)
            trial.exchange(fd, output, 'cat /etc/zsh-smoke.zsh', SMOKE.splitlines(), trial.shell.PROMPT, state)
            state['checks'].append('recovery_shell_lists_and_reads_exact_smoke_file')
            command = ('zsh -f -c \'print -r -- "DIAG_VERSION:$ZSH_VERSION"; '
                       '[[ -e /etc/zsh-smoke.zsh ]]; print -r -- "DIAG_EXISTS:$?"; '
                       '[[ -f /etc/zsh-smoke.zsh ]]; print -r -- "DIAG_REGULAR:$?"; '
                       '[[ -r /etc/zsh-smoke.zsh ]]; print -r -- "DIAG_READABLE:$?"; '
                       'print -r -- DIAG_DONE\'')
            trial.exchange(fd, output, command, [b'DIAG_VERSION:5.9', b'DIAG_DONE'], trial.shell.PROMPT, state)
            state['checks'].append('zsh_command_string_and_file_condition_results_captured')
        state['status'] = 'diagnostic_completed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd, termios.TCSANOW, original)
            finally: os.close(fd)
        raw = args.output / 'serial.bin'
        state.update(ended_utc=trial.utc_now(), bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] in ('diagnostic_completed', 'interactive_diagnostic_completed') else 1


if __name__ == '__main__': raise SystemExit(main())
