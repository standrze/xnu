#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded zsh diagnostic. Never sends input without a fresh distinct boot."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import select
import sys
import termios
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_zsh_trial_package as package_check
import serial_shell_trial as shell
from serial_terminal_trial import TERMINAL_LOADER, utc_now, valid_probe_device

ENTRY = b'RPI5XNU:BL33:ENTRY EL='
TRANSFER = b'RPI5XNU:BL33:XNU_TRANSFER_PENDING WATCHDOG_15S SEED_COMMIT_NEXT'
READY = b'RPI5XNU:SHELL:READY'
ZPROMPT = b'pi-zsh# '
LAUNCH = "zsh -f -c 'export PS1=\"pi-zsh%# \"; export TERMINFO=/etc/terminfo; exec /bin/zsh -f -i'"
SMOKE_LINES = [b'RPI5XNU:ZSH:VERSION:5.9', b'RPI5XNU:ZSH:BUILTIN:42:xnu',
               b'RPI5XNU:ZSH:EXTERNAL_EXEC', b'RPI5XNU:ZSH:SMOKE_DONE']
MAX_BYTES = 2 * 1024 * 1024
FORBIDDEN = (b'panic(cpu', b'REJECTED', b'RPI5XNU:BL33:STOP', b'RPI5XNU:BL33:EXCEPTION',
             b'RPI5XNU:SD:', b'RPI5XNU:HFS:', b'RPI5XNU:HFSRW:', b'RPI5XNU:HFSWRITE:',
             b'DARWIN:ZSH:FAULT:', b'Segmentation fault', b'Illegal instruction')


def normalized(raw):
    return raw.replace(b'\r', b'')


def boot_ready(raw, image_bytes, root_marker=package_check.RAMROOT):
    data = normalized(raw)
    if len(data) > MAX_BYTES or any(marker in data for marker in FORBIDDEN):
        raise RuntimeError('Unsafe or failed boot; no zsh input permitted')
    if data.count(ENTRY) > 1 or data.count(b'Boot mode: SD (01)') > 1:
        raise RuntimeError('Duplicate boot before zsh trial')
    mounts = re.findall(rb'RPI5XNU:RAMROOT:MOUNT[^\n]*\n', data)
    if mounts and mounts != [root_marker + b'\n']:
        raise RuntimeError('Old or unexpected RAM root; no input permitted')
    reads = re.findall(rb'Read probe\.bin bytes (\d+) hnd ', data)
    if reads and reads != [str(image_bytes).encode()]:
        raise RuntimeError('Firmware loaded a different or duplicate image extent')
    ordered = (b'Boot mode: SD (01)', b'Read probe.bin bytes ' + str(image_bytes).encode() + b' hnd ',
               ENTRY, TERMINAL_LOADER, package_check.TOPOLOGY_PASS, TRANSFER,
               root_marker, READY)
    if not all(marker in data for marker in ordered):
        return False
    positions = [data.index(marker) for marker in ordered]
    if positions != sorted(positions):
        raise RuntimeError('Fresh boot markers out of order')
    return bool(shell.PROMPT.search(data[positions[-1]:]))


def wait_boot(fd, output, seconds, image_bytes, root_marker=package_check.RAMROOT):
    deadline, data = time.monotonic() + seconds, b''
    while time.monotonic() < deadline:
        data += shell.receive(fd, output, deadline)
        if len(data) > MAX_BYTES:
            raise RuntimeError('Boot capture exceeded bound')
        if boot_ready(data, image_bytes, root_marker):
            return data
    raise TimeoutError('No fresh distinct zsh-root boot; zero input sent')


def send(fd, text, progress):
    for byte in (text + '\n').encode('ascii'):
        _, ready, _ = select.select([], [fd], [], 2)
        if not ready or os.write(fd, bytes([byte])) != 1:
            raise RuntimeError('Serial transmit failed')
        progress['transmitted_bytes'] += 1
        time.sleep(0.025)


def response_complete(raw, expected, prompt):
    data = normalized(raw)
    matches = [list(re.finditer(rb'(?:^|\n)' + re.escape(line) + rb'\n', data)) for line in expected]
    if not all(matches):
        return False
    end = max((items[-1].end() for items in matches), default=0)
    return prompt.search(data[end:]) is not None


def exchange(fd, output, text, expected, prompt, progress, seconds=30):
    send(fd, text, progress)
    deadline, data = time.monotonic() + seconds, b''
    while time.monotonic() < deadline:
        data += shell.receive(fd, output, deadline)
        if len(data) > 65536:
            raise RuntimeError('zsh command output exceeded bound')
        if ENTRY in data or TERMINAL_LOADER in data or any(marker in data for marker in FORBIDDEN):
            raise RuntimeError('Reboot or execution failure during zsh trial')
        if response_complete(data, expected, prompt):
            return data
    raise TimeoutError('zsh command lacked exact output and subsequent prompt')


def trial(fd, output, seconds, report, progress):
    wait_boot(fd, output, seconds, report['image_bytes'])
    progress['checks'].append('fresh_exact_extent_distinct_ramroot_shell_boot')
    nonce = 'Z' + secrets.token_hex(8)
    exchange(fd, output, 'echo ' + nonce, [nonce.encode()], shell.PROMPT, progress)
    progress['checks'].append('recovery_shell_fresh_nonce')
    exchange(fd, output, 'zsh -f /etc/zsh-smoke.zsh', SMOKE_LINES, shell.PROMPT, progress)
    exchange(fd, output, 'echo $?', [b'0'], shell.PROMPT, progress)
    progress['checks'].append('zsh_version_array_arithmetic_external_exec_and_exit_zero')
    zprompt = re.compile(re.escape(ZPROMPT))
    # A first noninteractive zsh exports a fixed prompt and execs the interactive
    # instance. No input follows until both startup traces and its actual prompt.
    launched = exchange(fd, output, LAUNCH, [b'DARWIN:ZSH:MAIN'], zprompt, progress)
    if normalized(launched).count(b'DARWIN:ZSH:MAIN\n') != 2:
        raise RuntimeError('Expected launcher and interactive zsh startup traces')
    progress['checks'].append('interactive_zsh_fixed_prompt')
    exchange(fd, output, 'print -r -- "PI_ZSH:$ZSH_VERSION"', [b'PI_ZSH:5.9'], zprompt, progress)
    exchange(fd, output, 'a=(pi xnu); print -r -- "PI_BUILTINS:${a[2]}:$((6*7))"',
             [b'PI_BUILTINS:xnu:42'], zprompt, progress)
    exchange(fd, output, '/bin/echo PI_EXEC_' + nonce, [('PI_EXEC_' + nonce).encode()], zprompt, progress)
    progress['checks'].append('interactive_version_builtins_external_exec_returned_prompt')
    exchange(fd, output, 'exit', [], shell.PROMPT, progress)
    exchange(fd, output, 'echo RECOVERED_' + nonce, [('RECOVERED_' + nonce).encode()], shell.PROMPT, progress)
    progress['checks'].append('interactive_exit_and_live_recovery_shell')
    progress['nonce'] = nonce


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--image-sha256', required=True)
    parser.add_argument('--boot-wait-seconds', type=int, default=180)
    args = parser.parse_args()
    if not valid_probe_device(args.device) or not 30 <= args.boot_wait_seconds <= 3600:
        parser.error('Expected Debug Probe callout/stable path and bounded 30..3600 boot wait')
    report = package_check.inspect(args.package)
    if report['image_sha256'] != args.image_sha256:
        raise ValueError('Explicit trial image pin differs')
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='failed', started_utc=utc_now(), device=args.device, baud=115200,
                 checks=[], transmitted_bytes=0, preflight=report,
                 scope='One diagnostic Pi zsh boot; no networking, storage durability or full distribution proof')
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
        termios.tcflush(fd, termios.TCIFLUSH)
        with (args.output / 'serial.bin').open('xb', buffering=0) as output:
            print('ZSH_TRIAL_ARMED NO_TX_UNTIL_DISTINCT_FRESH_BOOT', flush=True)
            trial(fd, output, args.boot_wait_seconds, report, state)
        state['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            except OSError as error:
                state['serial_restore_error'] = str(error)
                state['status'] = 'failed'
            finally:
                os.close(fd)
        raw = args.output / 'serial.bin'
        state.update(ended_utc=utc_now(), bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
