#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One fresh-boot raw-file diagnosis; never a script-acceptance or soak trial."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import termios

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_statprobe_package as package_check
import serial_zsh_trial as transport

IMAGE_SHA = '822e52de88303be9edfe20dec51d14fe1476a0604c77040b56d6254f1a953e99'
ROOT_MARKER = b'RPI5XNU:RAMROOT:MOUNT NODES=25 BYTES=1441792 READONLY'
PATHS = ('/etc/zsh-smoke.zsh', '/etc/motd', '/etc', '/etc/statprobe-missing')
BEGIN = b'STATPROBE:BEGIN:RAW_DARWIN_STAT64_V1'
END = b'STATPROBE:END:DIAGNOSTIC_ONLY'
CHECKS = ['fresh_exact_extent_statprobe_recovery_boot', 'recovery_shell_fresh_nonce',
          'raw_file_diagnostic_complete', 'diagnostic_exit_zero_live_recovery_shell']


def parse_diagnostic(raw):
    """Validate framing/grammar without interpreting errno or type as success.

    No guessed type replacement, zero filling, or requirement that metadata/open
    succeed. Failed calls and inconsistent type remain the returned evidence.
    """
    lines = [line for line in transport.normalized(raw).splitlines() if line.startswith(b'STATPROBE:')]
    cursor = 0
    def take(prefix):
        nonlocal cursor
        if cursor >= len(lines) or not lines[cursor].startswith(prefix):
            raise ValueError('Incomplete/out-of-order statprobe field: ' + repr(prefix))
        value = lines[cursor][len(prefix):]
        cursor += 1
        return value
    def literal(value):
        if take(value) != b'':
            raise ValueError('Unexpected diagnostic marker suffix')
    def number(key):
        value = take(b'STATPROBE:' + key.encode() + b'=')
        if not transport.re.fullmatch(rb'-?(?:0|[1-9][0-9]*)', value):
            raise ValueError('Not an exact signed diagnostic integer')
        result = int(value)
        if not -(1 << 63) <= result < (1 << 63):
            raise ValueError('Diagnostic integer outside Darwin register extent')
        return result
    def hexdata(key, size):
        value = take(b'STATPROBE:' + key.encode() + b'=')
        if not transport.re.fullmatch(rb'[0-9a-f]*', value) or len(value) != 2 * size:
            raise ValueError('Incorrect raw diagnostic byte extent')
        return value.decode('ascii')
    def metadata(key):
        rc = number(key)
        result = dict(rc=rc, raw_hex=hexdata('RAW', 144), guards=number('GUARDS'))
        if result['guards'] != 1:
            raise ValueError('Diagnostic buffer damage; preserve incomplete capture')
        if rc == 0:
            mode = number('MODE')
            regular, directory = number('ISREG'), number('ISDIR')
            actual = int.from_bytes(bytes.fromhex(result['raw_hex'])[4:6], 'little')
            if (mode != actual or regular != int((mode & 0xf000) == 0x8000)
                    or directory != int((mode & 0xf000) == 0x4000)):
                raise ValueError('Reported metadata differs from actual raw bytes')
            result.update(mode=mode, is_regular=bool(regular), is_directory=bool(directory))
        return result
    def read(key, data_key):
        rc = number(key)
        result = dict(rc=rc)
        if rc >= 0:
            if rc > 16:
                raise ValueError('Unbounded diagnostic read')
            result['hex'] = hexdata(data_key, rc)
        return result
    literal(BEGIN)
    paths = []
    for path in PATHS:
        if take(b'STATPROBE:PATH=') != path.encode():
            raise ValueError('Unexpected or duplicate diagnostic path')
        row = dict(path=path, access_f_ok=number('ACCESS_F_OK'), access_r_ok=number('ACCESS_R_OK'),
                   stat=metadata('STAT64'), lstat=metadata('LSTAT64'), opens=[])
        if len(paths) < 2:
            for flags in (0, 0x20000):
                if number('OPEN_FLAGS') != flags:
                    raise ValueError('Unexpected or duplicate open profile')
                opened = dict(flags=flags, fd=number('OPEN'))
                if opened['fd'] >= 0:
                    if opened['fd'] > 0x7fffffff:
                        raise ValueError('Invalid descriptor extent')
                    opened.update(fstat=metadata('FSTAT64'), getfd=number('F_GETFD'), getfl=number('F_GETFL'),
                                  duplicate=number('F_DUPFD_10'))
                    duplicate = opened['duplicate']
                    if duplicate >= 0:
                        if not 10 <= duplicate <= 0x7fffffff or duplicate == opened['fd']:
                            raise ValueError('Invalid/aliased duplicate; preserve failed capture')
                        opened.update(duplicate_read=read('DUP_READ', 'DUP_DATA'), duplicate_close=number('DUP_CLOSE'))
                    opened.update(original_read=read('ORIGINAL_READ', 'ORIGINAL_DATA'), original_close=number('ORIGINAL_CLOSE'))
                row['opens'].append(opened)
        paths.append(row)
    if number('BUFFER_DAMAGE') != 0:
        raise ValueError('Diagnostic reported damage')
    literal(END)
    if cursor != len(lines):
        raise ValueError('Repeated or extra statprobe fields')
    return dict(paths=paths, bounded_diagnostic_completed=True,
                script_file_acceptance=False, abi_root_cause_proven=False)


def trial(fd, output, seconds, report, state):
    transport.wait_boot(fd, output, seconds, report['image_bytes'], ROOT_MARKER)
    state['checks'].append(CHECKS[0])
    nonce = 'F' + secrets.token_hex(8)
    state['nonce'] = nonce
    transport.exchange(fd, output, 'echo ' + nonce, [nonce.encode()], transport.shell.PROMPT, state)
    state['checks'].append(CHECKS[1])
    raw = transport.exchange(fd, output, '/bin/statprobe', [BEGIN, END], transport.shell.PROMPT, state)
    state['observations'] = parse_diagnostic(raw)
    state['checks'].append(CHECKS[2])
    transport.exchange(fd, output, 'echo $?', [b'0'], transport.shell.PROMPT, state)
    transport.exchange(fd, output, 'echo RECOVERED_' + nonce, [('RECOVERED_' + nonce).encode()], transport.shell.PROMPT, state)
    state['checks'].append(CHECKS[3])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--image-sha256', required=True)
    parser.add_argument('--boot-wait-seconds', type=int, default=180)
    args = parser.parse_args()
    if not transport.valid_probe_device(args.device) or not 30 <= args.boot_wait_seconds <= 3600:
        parser.error('Expected Debug Probe callout and bounded boot wait')
    report = package_check.inspect(args.package)
    if report['image_sha256'] != args.image_sha256 or args.image_sha256 != IMAGE_SHA:
        raise ValueError('Requires the exact distinct prepared diagnostic image')
    if report.get('root_mount_marker', '').encode() != ROOT_MARKER or report['image_bytes'] != 18057920:
        raise ValueError('Requires exact additive root/image extents')
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='failed', started_utc=transport.utc_now(), device=args.device, baud=115200,
                 checks=[], transmitted_bytes=0, preflight=report, script_file_acceptance=False,
                 scope='One raw stat/open/dup diagnostic; not a script fix, network or durability acceptance')
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
            print('STATPROBE_TRIAL_ARMED ZERO_TX_UNTIL_DISTINCT_FRESH_BOOT', flush=True)
            trial(fd, output, args.boot_wait_seconds, report, state)
        state['status'] = 'diagnostic_completed'
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
        state.update(ended_utc=transport.utc_now(), bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'diagnostic_completed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
