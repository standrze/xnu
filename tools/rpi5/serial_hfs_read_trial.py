#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Guarded HFS read-only acceptance: two mount/read/unmount cycles, no soak.

Requires a prior successful physical SD read capture, independently verified
Linux clone of the Mac fixture, and a distinct HFS package before opening the
port. Never stages, partitions, writes media or reboots the Pi.
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

import capture_hfs_reference as hfs_reference
from check_hfs_read_package import HFS_LOADER, REQUIRED_HFS_CHECKS, REQUIRED_HFS_CONFIG
from check_sd_read_package import SD_LOADER, sha256
from hfs_read_results import normalize_output, read_file
from prepare_hfs_fixture import PROOF
from serial_sd_read_trial import validate_preflight as validate_sd_preflight
from serial_shell_trial import command, receive
from serial_terminal_trial import TERMINAL_LOADER, utc_now, valid_probe_device, wait_for_boot_markers
from sd_read_results import validate_sector_capture

ABORT_MARKERS = (b'panic(cpu', b'KernelConfigTables syntax error',
                 b':SD:HANDOFF RC=-', b':SD:INIT_FAIL RC=', b':SD:NUB_FAIL')


def validate_preflight(report):
    validate_sd_preflight(report)
    if (report.get('hfs_readonly_trial') is not True or
            not REQUIRED_HFS_CHECKS <= report['checks'].keys() or
            any(report['checks'][name] is not True for name in REQUIRED_HFS_CHECKS)):
        raise ValueError('Distinct complete HFS read-only package preflight required')
    image = Path(report['image']).read_bytes()
    if HFS_LOADER not in image or b' bcm2712_hfs=1 bcm2712_sd_readonly=1\0' not in image:
        raise ValueError('Actual image is not the distinct HFS read-only trial')
    config = report.get('linked_hfs_configuration', {})
    fragments = config.get('required_fragments_present', {})
    if (config.get('syntax_pass') is not True or set(fragments) != set(REQUIRED_HFS_CONFIG)
            or any(value is not True for value in fragments.values())):
        raise ValueError('Actual linked all-of HFS encoding dependency required')


def load_zero_tx_resume(path, reports, hashes, device, partition, now=None):
    """Only the recent interrupted zero-input boot with a torn encoding banner.

    A complete REGISTERED line follows IOKit's linked all-of encoding resource
    match. We do not reconstruct the torn banner or claim it was observed.
    Full mount/file/exec/unmount acceptance still runs twice, unchanged.
    """
    saved = path.read_bytes()
    state = json.loads(saved)
    raw_path = path.parent / 'serial.bin'
    if raw_path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('Oversized prior HFS capture')
    raw = raw_path.read_bytes()
    if (state.get('status') != 'failed' or state.get('error') != 'interrupted'
            or state.get('device') != device or state.get('partition') != partition
            or state.get('checks') != [] or state.get('reads') != []
            or type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != 0
            or type(state.get('mount_cycles_completed')) is not int or state['mount_cycles_completed'] != 0
            or state.get('sd_data_write_commands') != 0 or state.get('baud') != 115200
            or state.get('image_sha256') != reports['preflight']['image_sha256']
            or state.get('evidence_sha256') != hashes or len(raw) != state.get('bytes')
            or hashlib.sha256(raw).hexdigest() != state.get('serial_sha256')):
        raise ValueError('Not the preserved zero-transmit HFS startup interruption')
    start = datetime.fromisoformat(state['started_utc'])
    end = datetime.fromisoformat(state['ended_utc'])
    captured = datetime.fromisoformat(reports['reference']['captured_at'])
    now = now or datetime.now(timezone.utc)
    if (any(value.utcoffset() is None for value in (start, end, captured, now))
            or not captured <= start <= end <= now or not 0 <= (now-end).total_seconds() <= 900
            or (now-start).total_seconds() > 1800):
        raise ValueError('Recent explicitly known boot required for HFS continuation')
    capacity = reports['reference']['identity']['bytes'] // 512
    markers = (TERMINAL_LOADER, SD_LOADER, HFS_LOADER,
               f'RPI5XNU:SD:READ_ONLY_READY SECTORS={capacity} BLOCK=512 DMA=0 WRITES=0'.encode(),
               b'RPI5XNU:HFS:REGISTERED')
    if (any(raw.count(marker) != 1 for marker in markers)
            or b'RPI5XNU:SHELL:READY' not in raw
            or b'RPI5XNU:HFS:ENCODINGS_READY' in raw
            or any(marker in raw for marker in (*ABORT_MARKERS, b'RPI5XNU:HFSRO:'))
            or any(raw.index(marker) >= raw.index(markers[-1]) for marker in markers[:3])
            or raw.rfind(b'RPI5XNU:SHELL:READY') < max(raw.index(marker) for marker in markers)):
        raise ValueError('Missing intact HFS registration/readiness, unexpected boot or prior mount')
    if path.read_bytes() != saved or raw_path.read_bytes() != raw:
        raise ValueError('Prior HFS capture changed during validation')
    return raw, dict(continuation_of=str(path.resolve()),
                     previous_state_sha256=hashlib.sha256(saved).hexdigest(),
                     previous_raw_sha256=hashlib.sha256(raw).hexdigest(), previous_raw_bytes=len(raw),
                     capture_segments=2, closed_port_interval_observed=False,
                     encoding_ready_banner_observed=False)


def validate_sd_trial(state, raw, baseline, baseline_sha256):
    expected = [dict(lba=row['lba'], bytes=512, sha256=row['sha256'], **{'pass': n})
                for n in (1, 2) for row in baseline['sectors']]
    if (state.get('status') != 'passed' or state.get('reads') != expected or
            state.get('reference_sha256') != baseline_sha256 or
            type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] <= 0 or
            'sixteen_sector_reads_match_independent_linux_hashes' not in state.get('checks', []) or
            not raw.is_file() or raw.stat().st_size > 64 * 1024 * 1024 or
            raw.stat().st_size != state.get('bytes') or sha256(raw) != state.get('serial_sha256')):
        raise ValueError('Prior complete physical SD read capture required before HFS trial')
    if any(type(row['pass']) is not int or type(row['bytes']) is not int or
           type(row['lba']) is not int for row in state['reads']):
        raise ValueError('Prior SD read coverage must use integer passes, lengths and LBAs')
    captured = raw.read_bytes()
    if (len(captured) != state['bytes'] or
            hashlib.sha256(captured).hexdigest() != state['serial_sha256']):
        raise ValueError('Prior SD capture changed while being read')
    ready = (f"RPI5XNU:SD:READ_ONLY_READY SECTORS={baseline['identity']['bytes'] // 512} "
             'BLOCK=512 DMA=0 WRITES=0').encode()
    if (any(marker not in captured for marker in (TERMINAL_LOADER, SD_LOADER, ready,
                                                 b'RPI5XNU:SHELL:READY')) or
            any(marker in captured for marker in ABORT_MARKERS)):
        raise ValueError('Prior physical SD capture lacks clean fresh readiness')
    validate_sector_capture(captured, expected, baseline['identity']['bytes'] // 512)
    first_read = captured.index(b'RPI5XNU:SDREAD:SECTOR')
    if any(captured.index(marker) >= first_read for marker in
           (TERMINAL_LOADER, SD_LOADER, ready, b'RPI5XNU:SHELL:READY')):
        raise ValueError('Prior SD readiness did not precede the physical reads')


def load_inputs(paths, now=None):
    """Validate immutable evidence before mkdir/open/ioctl/serial transmission."""
    snapshots = {name: path.read_bytes() for name, path in paths.items()}
    reports = {name: json.loads(raw) for name, raw in snapshots.items()}
    hashes = {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshots.items()}
    fixture, baseline, reference = (reports[name] for name in ('fixture', 'baseline', 'reference'))
    hfs_reference.validate_fixture(fixture)
    hfs_reference.validate_capture(reference, baseline, fixture)
    validate_preflight(reports['preflight'])
    validate_sd_trial(reports['sd_trial'], paths['sd_trial'].parent / 'serial.bin', baseline, hashes['baseline'])
    expected_source = hfs_reference.remote_source(hfs_reference.expected_identity(baseline), fixture['image_sha256'])
    if (reference.get('fixture_reference_sha256') != hashes['fixture'] or
            reference.get('sd_baseline_reference_sha256') != hashes['baseline'] or
            reference.get('capture_source_sha256') != sha256(Path(hfs_reference.__file__)) or
            reference.get('remote_source_sha256') != hashlib.sha256(expected_source.encode()).hexdigest() or
            reference.get('host') != 'sandrzej@192.168.4.23'):
        raise ValueError('Linux physical reference provenance or fixture binding changed')
    captured_at = datetime.fromisoformat(reference['captured_at'])
    if captured_at.utcoffset() is None:
        raise ValueError('Linux physical reference timestamp lacks timezone')
    age = ((now or datetime.now(timezone.utc)) - captured_at).total_seconds()
    if not -30 <= age <= 1800:
        raise ValueError('Linux physical reference is stale; recapture before arming')
    if any(sha256(path) != hashes[name] for name, path in paths.items()):
        raise ValueError('Evidence changed during HFS trial preflight')
    return reports, hashes


def mount_marker(action, partition):
    return f'RPI5XNU:HFSRO:{action} DEVICE={partition} PATH=/mnt/hfs READONLY=1'.encode()


def trial(fd, output, wait, progress, reference, fixture, partition, resume=False):
    sectors = reference['identity']['bytes'] // 512
    ready = f'RPI5XNU:SD:READ_ONLY_READY SECTORS={sectors} BLOCK=512 DMA=0 WRITES=0'.encode()
    if resume:
        passive = b''
        deadline = time.monotonic() + 15
        while b'RPI5XNU:SHELL:READY' not in passive:
            if time.monotonic() >= deadline:
                raise TimeoutError('No fresh repeated shell readiness after explicit capture gap')
            passive += receive(fd, output, deadline)
            if len(passive) > 65536 or any(marker in passive for marker in (*ABORT_MARKERS, TERMINAL_LOADER)):
                raise ValueError('Unexpected boot/failure before HFS continuation')
        progress['checks'].append('fresh_repeated_shell_readiness_after_explicit_capture_gap')
    else:
        # REGISTERED is printed only after the actual linked all-of dependency
        # on IOBSD and RPI5HFSEncodingsReady matched. The one-time encoder printf
        # can be torn by SMP chatter; it is diagnostic, not independent proof.
        wait_for_boot_markers(fd, output, time.monotonic() + wait, keyboard_required=False,
                             extra_markers=(SD_LOADER, HFS_LOADER, ready, b'RPI5XNU:HFS:REGISTERED',
                                            b'RPI5XNU:SHELL:READY'), abort_markers=ABORT_MARKERS)
    progress['encoding_readiness_evidence'] = 'intact_registered_service_after_verified_linked_all_of_encoding_dependency'
    progress['checks'].append('fresh_distinct_hfs_loader_sd_capacity_hfs_services_and_shell_ready')
    quiet = b''
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        quiet += receive(fd, output, deadline)
        if len(quiet) > 65536 or any(marker in quiet for marker in (*ABORT_MARKERS, TERMINAL_LOADER)):
            raise ValueError('Unexpected boot/failure while settling HFS shell')
    nonce = 'H' + secrets.token_hex(8)
    command(fd, output, 'echo ' + nonce, [nonce.encode()], progress)
    progress['checks'].append('fresh_shell_nonce')
    command(fd, output, 'ls /dev', [partition.removeprefix('/dev/').encode()], progress)
    progress['checks'].append('real_bsd_second_partition_node')
    for cycle in (1, 2):
        command(fd, output, 'hfsro mount ' + partition, [mount_marker('MOUNTED', partition)], progress, seconds=120)
        command(fd, output, 'hfsro status ' + partition, [mount_marker('STATUS', partition)], progress)
        command(fd, output, 'ls /mnt/hfs', [b'bin/', b'etc/'], progress)
        command(fd, output, 'ls /mnt/hfs/etc', [b'proof.txt', b'empty', b'cross-page.bin', b'recovery.sh'], progress)
        for entry in fixture['files']:
            result = read_file(fd, output, entry, progress)
            progress['reads'].append({**result, 'mount_cycle': cycle})
        nonce = 'H' + secrets.token_hex(8)
        response = command(fd, output, 'sh /mnt/hfs/etc/recovery.sh && echo ' + nonce,
                           [b'HFS_SCRIPT_BEGIN', PROOF.rstrip(b'\n'), b'HFS_SCRIPT_END', nonce.encode()], progress)
        script = b'HFS_SCRIPT_BEGIN\n' + PROOF + b'HFS_SCRIPT_END\n' + nonce.encode() + b'\n'
        if script not in normalize_output(response):
            raise ValueError('HFS script output is torn or out of order')
        nonce = 'H' + secrets.token_hex(8)
        command(fd, output, '/mnt/hfs/bin/echo ' + nonce, [nonce.encode()], progress)
        progress['checks'].append(f'cycle_{cycle}_directory_full_hashes_script_and_hfs_exec')
        nonce = 'MISSING_' + secrets.token_hex(8)
        command(fd, output, 'cat /mnt/hfs/etc/no_such_fixture || echo ' + nonce, [nonce.encode()], progress)
        command(fd, output, 'hfsro unmount ' + partition, [mount_marker('UNMOUNTED', partition)], progress, seconds=120)
        nonce = 'UNMOUNTED_' + secrets.token_hex(8)
        command(fd, output, 'hfsro status ' + partition + ' || echo ' + nonce, [nonce.encode()], progress)
        progress['mount_cycles_completed'] = cycle
        progress['checks'].append(f'cycle_{cycle}_missing_read_recovery_nonforce_unmount_and_mount_gone')
    nonce = 'H' + secrets.token_hex(8)
    command(fd, output, 'echo ' + nonce, [nonce.encode()], progress)
    progress['checks'].append('shell_live_after_two_complete_hfs_mount_cycles')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device')
    parser.add_argument('output', type=Path)
    for name in ('reference', 'fixture', 'sd-baseline-reference', 'preflight', 'sd-trial'):
        parser.add_argument('--' + name, required=True, type=Path)
    parser.add_argument('--partition', default='/dev/disk0s2')
    parser.add_argument('--boot-wait-seconds', type=int, default=180)
    parser.add_argument('--resume-zero-tx-state', type=Path,
                        help='Explicit same-boot recovery only for a recent interrupted zero-TX HFS startup capture')
    args = parser.parse_args()
    if (not valid_probe_device(args.device) or not re.fullmatch(r'/dev/disk(?:[0-9]|[12][0-9]|3[01])s2', args.partition)
            or not 30 <= args.boot_wait_seconds <= 3600):
        parser.error('Expected Debug Probe, canonical second BSD partition and bounded boot wait')
    reports, hashes = load_inputs(dict(reference=args.reference, fixture=args.fixture,
                                      baseline=args.sd_baseline_reference, preflight=args.preflight,
                                      sd_trial=args.sd_trial))
    prefix, continuation = b'', {}
    if args.resume_zero_tx_state:
        prefix, continuation = load_zero_tx_resume(args.resume_zero_tx_state, reports, hashes,
                                                   args.device, args.partition)
    args.output.mkdir(parents=True, exist_ok=False)
    state = dict(status='failed', started_utc=utc_now(), device=args.device, partition=args.partition,
                 checks=[], reads=[], mount_cycles_completed=0, transmitted_bytes=0, baud=115200,
                 image_sha256=reports['preflight']['image_sha256'], evidence_sha256=hashes,
                 sd_data_write_commands=0,
                 scope='Two read-only HFS mount/read/unmount cycles in one boot; not write durability, cold boots, DMA or full Gate 4')
    state.update(continuation)
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
        if not continuation:
            termios.tcflush(fd, termios.TCIFLUSH)
        with (args.output / 'serial.bin').open('xb', buffering=0) as output:
            output.write(prefix) # Exact unmodified prefix; the closed-port gap is explicitly unobserved.
            print('HFS_READ_TRIAL_ARMED 115200 8N1 NO_TX_UNTIL_HFS_SD_AND_SHELL_BOOT', flush=True)
            trial(fd, output, args.boot_wait_seconds, state, reports['reference'], reports['fixture'],
                  args.partition, resume=bool(continuation))
        state['status'] = 'passed'
    except (Exception, KeyboardInterrupt) as error:
        state['error'] = str(error) or 'interrupted'
        # No cleanup commands are sent into a failed/unknown kernel. Preserve
        # incoming diagnostics only, including first-failed-register details.
        raw = args.output / 'serial.bin'
        if raw.exists():
            state['encoding_ready_banner_observed'] = b'RPI5XNU:HFS:ENCODINGS_READY' in raw.read_bytes()
        if fd is not None and raw.exists():
            try:
                with raw.open('ab', buffering=0) as output:
                    deadline = time.monotonic() + 2
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
        state.update(ended_utc=utc_now(), bytes=raw.stat().st_size if raw.exists() else 0,
                     serial_sha256=sha256(raw) if raw.exists() else None)
        (args.output / 'state.json').write_text(json.dumps(state, indent=2) + '\n')
        print(json.dumps(state), flush=True)
    return 0 if state['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
