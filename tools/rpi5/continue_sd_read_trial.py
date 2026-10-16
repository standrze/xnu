#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One explicit SD-read continuation after the known host receive-boundary bug.

Never retries a device error or boots/stages anything. Preserve the failed run
unchanged, verify its exact complete sector prefix and completed nonce/prompt,
then append the remaining reads in a new, explicitly segmented evidence run.
The brief closed-port interval is recorded, not represented as continuous RX.
"""
import argparse
from datetime import datetime, timezone
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
from check_sd_read_package import SD_LOADER, sha256
from sd_read_results import validate_sector_capture
from serial_sd_read_trial import complete_reads, validate_preflight
from serial_shell_trial import command, receive
from serial_terminal_trial import TERMINAL_LOADER, utc_now, valid_probe_device

ABORT = (b'panic(cpu', b'KernelConfigTables syntax error', b':SD:HANDOFF RC=-',
         b':SD:INIT_FAIL RC=', b':SD:NUB_FAIL')
CHECKS = ['fresh_storage_loader_driver_capacity_and_shell_ready',
          'fresh_shell_nonce', 'real_bsd_raw_disk_node']


def validate_previous(state, raw, reference, reference_hash, preflight, preflight_hash, now):
    """No serial or filesystem mutation here; reject every other failure."""
    if (state.get('status') != 'failed' or state.get('error') != 'list index out of range'
            or state.get('checks') != CHECKS or state.get('device') != '/dev/cu.usbmodem102'
            or state.get('disk') != '/dev/rdisk0' or state.get('sd_data_write_operations') != 0
            or state.get('reference_sha256') != reference_hash
            or state.get('preflight_sha256') != preflight_hash
            or state.get('image_sha256') != preflight['image_sha256']
            or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] <= 0
            or not isinstance(raw, bytes) or len(raw) > 64 * 1024 * 1024
            or len(raw) != state.get('bytes') or hashlib.sha256(raw).hexdigest() != state.get('serial_sha256')):
        raise ValueError('Not the exact preserved host chunk-boundary failure')
    age = (now - datetime.fromisoformat(state['ended_utc'])).total_seconds()
    if not 0 <= age <= 1800:
        raise ValueError('Continuation requires a recent, explicitly known still-running boot')
    sectors = reference['identity']['bytes'] // 512
    markers = (TERMINAL_LOADER, SD_LOADER,
               f'RPI5XNU:SD:READ_ONLY_READY SECTORS={sectors} BLOCK=512 DMA=0 WRITES=0'.encode(),
               b'RPI5XNU:SHELL:READY')
    first = raw.find(b'RPI5XNU:SDREAD:SECTOR')
    if first < 0 or any(raw.find(marker) < 0 or raw.find(marker) >= first for marker in markers) \
            or any(marker in raw for marker in ABORT) or raw.count(TERMINAL_LOADER) != 1:
        raise ValueError('Missing clean prior package/readiness or observed reboot')
    count = raw.count(b'RPI5XNU:SDREAD:SECTOR')
    expected = [dict(lba=row['lba'], bytes=512, sha256=row['sha256'], **{'pass': n})
                for n in (1, 2) for row in reference['sectors']]
    if not 1 <= count <= 16 or state.get('reads') != expected[:count - 1]:
        raise ValueError('Partial report does not precede exactly one completed sector')
    validate_sector_capture(raw, expected[:count], sectors)
    # Do not consume an unfinished command, infer an exit status, or retransmit
    # an already completed read. The echoed nonce must have returned as output.
    normalized = re.sub(rb'\r{1,2}\n', b'\n', raw)
    echoed = re.findall(rb'xnu:/# sdread /dev/rdisk0 ([0-9]+) && echo (D[0-9a-f]{8})\n', normalized)
    if (len(echoed) != count or int(echoed[-1][0]) != expected[count - 1]['lba']
            or not normalized.endswith(b'RPI5XNU:SDREAD:END\n' + echoed[-1][1] + b'\nxnu:/# ')):
        raise ValueError('Last sector lacks a completed nonce and shell prompt')
    return expected[:count]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reference', required=True, type=Path)
    parser.add_argument('--preflight', required=True, type=Path)
    args = parser.parse_args()
    prior_path = args.previous / 'state.json'
    prior_bytes = prior_path.read_bytes()
    prior = json.loads(prior_bytes)
    raw = (args.previous / 'serial.bin').read_bytes()
    reference = json.loads(args.reference.read_text())
    preflight = json.loads(args.preflight.read_text())
    validate_capture(reference)
    validate_preflight(preflight)
    reads = validate_previous(prior, raw, reference, sha256(args.reference), preflight,
                              sha256(args.preflight), datetime.now(timezone.utc))
    if not valid_probe_device(prior['device']):
        raise ValueError('Invalid probe')
    args.output.mkdir(parents=True, exist_ok=False)
    state = {**prior, 'status': 'failed', 'reads': reads,
             'checks': list(CHECKS), 'continuation_started_utc': utc_now(),
             'continuation_of': str(args.previous.resolve()),
             'previous_state_sha256': hashlib.sha256(prior_bytes).hexdigest(),
             'previous_raw_sha256': hashlib.sha256(raw).hexdigest(),
             'previous_raw_bytes': len(raw),
             'capture_segments': 2, 'closed_port_interval_observed': False,
             'scope': 'One read-only XNU SD boot, two explicit capture segments; no HFS, writes or durability'}
    for key in ('error', 'ended_utc', 'serial_sha256', 'bytes'):
        state.pop(key, None)
    fd, original = None, None
    try:
        fd = os.open(prior['device'], os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        fcntl.ioctl(fd, termios.TIOCEXCL)
        original = termios.tcgetattr(fd)
        cfg = termios.tcgetattr(fd)
        cfg[0] = cfg[1] = cfg[3] = 0
        cfg[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
        cfg[4] = cfg[5] = termios.B115200
        cfg[6][termios.VMIN] = cfg[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, cfg)
        with (args.output / 'serial.bin').open('xb', buffering=0) as output:
            output.write(raw)  # Exact preserved prefix; no deletion/normalization.
            passive = b''
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                passive += receive(fd, output, deadline)
                if len(passive) > 65536 or any(marker in passive for marker in (*ABORT, TERMINAL_LOADER)):
                    raise ValueError('Unexpected boot/failure or excess chatter before continuation')
            nonce = 'D' + secrets.token_hex(4)
            command(fd, output, 'echo ' + nonce, [nonce.encode()], state)
            state['checks'].append('fresh_nonce_after_explicit_host_capture_gap')
            complete_reads(fd, output, state, reference, prior['disk'])
        captured = (args.output / 'serial.bin').read_bytes()
        validate_sector_capture(captured, state['reads'], reference['identity']['bytes'] // 512)
        state['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
    finally:
        if fd is not None:
            try:
                if original is not None:
                    termios.tcsetattr(fd, termios.TCSANOW, original)
            finally:
                os.close(fd)
        capture = args.output / 'serial.bin'
        state.update(ended_utc=utc_now(), bytes=capture.stat().st_size if capture.exists() else 0,
                     serial_sha256=sha256(capture) if capture.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
