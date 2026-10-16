#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate same-boot raw diagnosis after a zero-TX mount-marker timeout.

Does NOT pass or waive the strict mounted-root trial. Requires its preserved
recent fresh boot, exact loader/root-copy evidence, and current installed-image
receipt. No retry, reboot, media write, or speculative file-type correction.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import termios
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import serial_statprobe_trial as diagnostic
import stage_statprobe_trial as staging

t = diagnostic.transport
COPY = b'RPI5XNU:BL33:RAMDISK_MATERIALIZED PA=00000000080c8000 BYTES=0000000000160000 VERIFIED'
KERNEL = b'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=00000000010bc000 FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER'
COMMIT = b'RPI5XNU:BL33:BOOT_DATA_COMMITTED TRANSFER_NEXT'
INSTALL = staging.ROOT / 'build/rpi5/statprobe-trial-installed-20261012'
RESULT_SHA = 'c6ed4a222de1232d55eb69462b4918c8a553a328094e54f8007dee80f50c4c3b'
CHECKS = ['recent_zero_tx_exact_loader_copy_boot_receipt', 'same_boot_live_recovery_shell_nonce',
          'raw_file_diagnostic_complete', 'diagnostic_exit_zero_live_recovery_shell']


def payload_boot(raw):
    data = t.normalized(raw)
    # Retain strict rejection of explicit wrong roots/extents, duplicate boots,
    # storage trials and faults. Only the missing/torn mount line is unresolved.
    if t.boot_ready(raw, 18057920, diagnostic.ROOT_MARKER):
        raise ValueError('Strict boot was complete; use its original trial, not this follow-up')
    ordered = (b'Boot mode: SD (01)', b'Read probe.bin bytes 18057920 hnd ', t.ENTRY,
               t.TERMINAL_LOADER, COPY, KERNEL, t.package_check.TOPOLOGY_PASS,
               t.TRANSFER, COMMIT, t.READY)
    if any(data.count(marker) != 1 for marker in ordered[:-1]) or t.READY not in data:
        raise ValueError('Missing/repeated exact fresh loader and payload-copy evidence')
    positions = [data.index(marker) for marker in ordered]
    if positions != sorted(positions) or not t.shell.PROMPT.search(data[positions[-1]:]):
        raise ValueError('Loader copy/transfer/recovery evidence out of order')
    if b'FAILED_STOP' in data or b'RPI5XNU:RAMROOT:REJECT' in data:
        raise ValueError('Payload/root validation failed')
    return True


def evidence(directory, device, report, require_recent=True):
    state_path = directory / 'state.json'
    state = json.loads(state_path.read_text())
    raw = (directory / 'serial.bin').read_bytes()
    if (state.get('status') != 'failed' or state.get('checks') != [] or state.get('transmitted_bytes') != 0
            or state.get('error') != 'No fresh distinct zsh-root boot; zero input sent'
            or state.get('device') != device or state.get('baud') != 115200
            or state.get('bytes') != len(raw) or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or state.get('preflight') != report or 'serial_restore_error' in state):
        raise ValueError('Requires exact preserved zero-TX timeout and matching fresh preflight')
    start, end = [datetime.fromisoformat(state[key]) for key in ('started_utc', 'ended_utc')]
    if start.tzinfo is None or end.tzinfo is None or not 0 <= (end - start).total_seconds() <= 3720:
        raise ValueError('Invalid source capture times')
    if require_recent and not 0 <= (datetime.now(timezone.utc) - end).total_seconds() <= 900:
        raise ValueError('Same-boot source evidence expired; no input permitted')
    payload_boot(raw)
    plan = json.loads((INSTALL / 'plan.json').read_text())
    result = json.loads((INSTALL / 'result.json').read_text())
    if staging.base.terminal.sha256(INSTALL / 'result.json') != RESULT_SHA:
        raise ValueError('Exact installed-image receipt changed')
    staging.validate_result(result, plan)
    if result['image_sha256'] != report['image_sha256']:
        raise ValueError('Installed-image receipt differs from boot package')
    return dict(directory=str(directory.resolve()), state_sha256=hashlib.sha256(state_path.read_bytes()).hexdigest(),
                serial_sha256=state['serial_sha256'], install_result_sha256=RESULT_SHA,
                strict_mounted_root_trial_passed=False, mounted_root_node_count_observed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    parser.add_argument('--zero-tx-trial', type=Path, required=True)
    parser.add_argument('--package', type=Path, required=True)
    args = parser.parse_args()
    if not t.valid_probe_device(args.device): parser.error('Expected Debug Probe callout')
    report = diagnostic.package_check.inspect(args.package)
    if report['image_sha256'] != diagnostic.IMAGE_SHA or report['image_bytes'] != 18057920:
        raise ValueError('Only the exact installed diagnostic package is supported')
    source = evidence(args.zero_tx_trial, args.device, report)
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='failed', started_utc=t.utc_now(), device=args.device, baud=115200,
                 checks=[CHECKS[0]], transmitted_bytes=0, preflight=report, source=source,
                 script_file_acceptance=False, strict_mounted_root_trial_passed=False,
                 scope='Separate same-boot raw-file diagnosis; strict mount-marker trial remains failed')
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
            # Inspect queued output, do not flush away a potential reboot/fault.
            deadline, queued = time.monotonic() + 2, b''
            while time.monotonic() < deadline:
                queued += t.shell.receive(fd, output, deadline)
                if (len(queued) > 65536 or t.ENTRY in queued or t.TERMINAL_LOADER in queued
                        or b'Boot mode:' in queued or any(marker in queued for marker in t.FORBIDDEN)):
                    raise RuntimeError('Reboot/fault/oversized output before same-boot input')
            if evidence(args.zero_tx_trial, args.device, report) != source:
                raise ValueError('Source changed before first input')
            nonce = 'F' + secrets.token_hex(8)
            state['nonce'] = nonce
            t.exchange(fd, output, 'echo ' + nonce, [nonce.encode()], t.shell.PROMPT, state)
            state['checks'].append(CHECKS[1])
            raw = t.exchange(fd, output, '/bin/statprobe', [diagnostic.BEGIN, diagnostic.END], t.shell.PROMPT, state)
            state['observations'] = diagnostic.parse_diagnostic(raw)
            state['checks'].append(CHECKS[2])
            t.exchange(fd, output, 'echo $?', [b'0'], t.shell.PROMPT, state)
            t.exchange(fd, output, 'echo RECOVERED_' + nonce, [('RECOVERED_' + nonce).encode()], t.shell.PROMPT, state)
            state['checks'].append(CHECKS[3])
        state['status'] = 'same_boot_diagnostic_completed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None: termios.tcsetattr(fd, termios.TCSANOW, original)
            except OSError as error:
                state['serial_restore_error'] = str(error); state['status'] = 'failed'
            finally: os.close(fd)
        raw_path = args.output / 'serial.bin'
        state.update(ended_utc=t.utc_now(), bytes=raw_path.stat().st_size if raw_path.exists() else 0,
                     serial_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest() if raw_path.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'same_boot_diagnostic_completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
