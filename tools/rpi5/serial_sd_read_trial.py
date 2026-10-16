#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One bounded, marker-guarded read-only SD trial through the real BSD device."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import termios
import time

from capture_sd_reference import validate_capture
from check_sd_read_package import SD_LOADER, REQUIRED_SD_CHECKS, sha256
from sd_read_results import parse_sector
from serial_shell_trial import command, receive
from serial_terminal_trial import utc_now, valid_probe_device, wait_for_boot_markers


def validate_preflight(report):
    if (report.get('preflight_pass') is not True or report.get('sd_readonly_trial') is not True
            or not REQUIRED_SD_CHECKS <= report.get('checks', {}).keys()
            or not all(v is True for v in report['checks'].values())
            or sha256(Path(report['image'])) != report['image_sha256']):
        raise ValueError('Missing or changed SD read-only package preflight')


def trial(fd, output, wait, progress, reference, disk):
    sectors = reference['identity']['bytes'] // 512
    ready = f'RPI5XNU:SD:READ_ONLY_READY SECTORS={sectors} BLOCK=512 DMA=0 WRITES=0'.encode()
    wait_for_boot_markers(fd, output, time.monotonic()+wait,
                         extra_markers=(SD_LOADER, ready, b'RPI5XNU:SHELL:READY'), keyboard_required=False,
                         abort_markers=(b'panic(cpu', b'KernelConfigTables syntax error',
                                        b':SD:HANDOFF RC=-', b':SD:INIT_FAIL RC=', b':SD:NUB_FAIL'))
    progress['checks'].append('fresh_storage_loader_driver_capacity_and_shell_ready')
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        receive(fd, output, deadline)
    nonce = 'D' + secrets.token_hex(4)
    command(fd, output, 'echo '+nonce, [nonce.encode()], progress)
    progress['checks'].append('fresh_shell_nonce')
    command(fd, output, 'ls /dev', [disk.removeprefix('/dev/').encode()], progress)
    progress['checks'].append('real_bsd_raw_disk_node')
    complete_reads(fd, output, progress, reference, disk)


def complete_reads(fd, output, progress, reference, disk):
    """Finish exactly two ordered passes, retaining already verified records."""
    sectors = reference['identity']['bytes'] // 512
    expected_reads = [dict(lba=row['lba'], bytes=512, sha256=row['sha256'], **{'pass': n})
                      for n in (1, 2) for row in reference['sectors']]
    if progress['reads'] != expected_reads[:len(progress['reads'])] or len(progress['reads']) > 16:
        raise ValueError('Existing reads are not the exact ordered reference prefix')
    for expected in expected_reads[len(progress['reads']):]:
        nonce = 'D' + secrets.token_hex(4)
        response = command(fd, output, f"sdread {disk} {expected['lba']} && echo {nonce}",
                           [b'RPI5XNU:SDREAD:END', nonce.encode()], progress, seconds=30)
        actual = parse_sector(response, expected['lba'], sectors)
        if actual['sha256'] != expected['sha256']:
            raise ValueError(f"Linux/XNU sector mismatch: LBA {expected['lba']}")
        progress['reads'].append({**actual, 'pass': expected['pass']})
    progress['checks'].append('sixteen_sector_reads_match_independent_linux_hashes')
    command(fd, output, f'sdread {disk} {sectors} || echo BOUNDS_REJECTED', [b'BOUNDS_REJECTED'], progress)
    progress['checks'].append('userspace_bounds_rejection_not_a_driver_fault_injection')
    nonce = 'D' + secrets.token_hex(4)
    command(fd, output, 'echo '+nonce, [nonce.encode()], progress)
    progress['checks'].append('shell_live_after_storage_reads')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--preflight', required=True, type=Path)
    parser.add_argument('--disk', default='/dev/rdisk0')
    parser.add_argument('--boot-wait-seconds', type=int, default=180)
    args = parser.parse_args()
    if (not valid_probe_device(args.device) or not re.fullmatch(r'/dev/rdisk(?:[0-9]|[12][0-9]|3[01])', args.disk)
            or not 30 <= args.boot_wait_seconds <= 3600):
        parser.error('Expected Debug Probe, whole raw disk and bounded boot wait')
    reference = json.loads(args.reference.read_text())
    validate_capture(reference)
    preflight = json.loads(args.preflight.read_text())
    validate_preflight(preflight)  # Reject before opening/touching the serial port.
    args.output.mkdir(parents=True, exist_ok=False)
    state = {'status': 'failed', 'started_utc': utc_now(), 'device': args.device, 'disk': args.disk,
             'checks': [], 'reads': [], 'transmitted_bytes': 0, 'baud': 115200,
             'image_sha256': preflight['image_sha256'], 'reference_sha256': sha256(args.reference),
             'preflight_sha256': sha256(args.preflight), 'sd_data_write_operations': 0,
             'scope': 'One XNU read-only BSD-device boot; no HFS mount, writes, DMA or durability evidence'}
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
            print('SD_READ_TRIAL_ARMED 115200 8N1 NO_TX_UNTIL_SD_AND_SHELL_READY', flush=True)
            trial(fd, output, args.boot_wait_seconds, state, reference, args.disk)
        state['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
        # HANDOFF failure precedes its exact readback diagnostic. Drain only
        # incoming bytes briefly so fail-fast does not truncate the cause.
        raw = args.output / 'serial.bin'
        if fd is not None and raw.exists():
            try:
                with raw.open('ab', buffering=0) as output:
                    deadline = time.monotonic()+2
                    while time.monotonic() < deadline:
                        receive(fd, output, deadline)
            except (Exception, KeyboardInterrupt) as drain_error:
                state['diagnostic_drain_error'] = str(drain_error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            finally:
                os.close(fd)
        raw = args.output / 'serial.bin'
        state.update({'ended_utc': utc_now(), 'bytes': raw.stat().st_size if raw.exists() else 0,
                      'serial_sha256': hashlib.sha256(raw.read_bytes()).hexdigest() if raw.exists() else None})
        (args.output / 'state.json').write_text(json.dumps(state, indent=2)+'\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
