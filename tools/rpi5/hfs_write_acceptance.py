# SPDX-License-Identifier: BSD-2-Clause
"""Independent complete raw transcript audit of the single write batch.

Pure validation, no serial/network/device access. A passed record proves only
the same-boot batch/unmount; subsequent capture/fsck/RO readback is mandatory.
"""
import hashlib
import re

import serial_hfs_write_trial as trial
from hfs_read_results import frame_markers
from hfs_write_serial_results import parse_file
from serial_shell_trial import PROMPT


def one_line(raw, marker):
    matches = trial.exact_lines(raw, marker)
    if len(matches) != 1:
        raise ValueError('Missing, torn or repeated write proof line: ' + repr(marker))
    return matches[0]


def validate(state, raw, plan, installed, bound):
    expected = dict(status='batch_passed_not_durability', partition='/dev/disk0s2', baud=115200,
                    image_sha256=plan['new_image_sha256'], linux_boot_id_before_write=plan['linux_boot_id'],
                    write_batch_attempts=1, hfs_mounted=False, durability_verified=False)
    if (any(type(state.get(key)) is not type(value) or state[key] != value for key, value in expected.items())
            or state.get('checks') != trial.CHECKS or state.get('evidence_sha256') != bound
            or state.get('write_input_sha256') != plan['evidence_sha256']
            or installed.get('image_sha256') != plan['new_image_sha256']
            or type(state.get('bytes')) is not int or state['bytes'] != len(raw)
            or not 0 < len(raw) <= 64 * 1024 * 1024
            or state.get('serial_sha256') != hashlib.sha256(raw).hexdigest()
            or any(marker in raw for marker in trial.ABORT)):
        raise ValueError('Write batch state/raw/installation binding is incomplete')
    shell_nonces = list(re.finditer(rb'(?m)^W[0-9a-f]{16}\r{0,2}\n', raw))
    if len(shell_nonces) != 2 or shell_nonces[0][0] == shell_nonces[1][0]:
        raise ValueError('Require two distinct intact shell nonce responses')
    admission = trial.validate_boot(raw[:shell_nonces[0].start()])
    if (admission is None or state.get('admission') != admission or
            any(type(state['admission'].get(key)) is not type(value) for key, value in admission.items())):
        raise ValueError('Write admission is not independently proven before input')
    for prefix in (trial.TERMINAL_LOADER, trial.WRITE_LOADER, b'RPI5XNU:SD:WRITE_ADMITTED', b'RPI5XNU:HFS:REGISTERED'):
        if raw.count(prefix) != 1:
            raise ValueError('Repeated/torn write startup or intervening reset')
    disk = one_line(raw, b'disk0s2')
    mount, status, unmount = [one_line(raw, trial.mount_marker(op)) for op in ('MOUNTED', 'STATUS', 'UNMOUNTED')]
    batch = one_line(raw, trial.BATCH)
    if (raw.count(b'RPI5XNU:HFSRW:') != 3 or raw.count(b'RPI5XNU:HFSWRITE:') != 1 or
            not shell_nonces[0].end() <= disk.start() < disk.end() <= mount.start() < mount.end()
            <= status.start() < status.end() <= batch.start() < batch.end() <= unmount.start()):
        raise ValueError('Exact one-batch writable mount/status/unmount order is not proven')
    entries = trial.expected_entries(); reads = state.get('reads', [])
    if len(reads) != len(entries) or [row.get('path') for row in reads] != [entry['path'] for entry in entries]:
        raise ValueError('Missing/reordered/repeated full write-vector coverage')
    nonces = [row.get('nonce') for row in reads]
    if any(not isinstance(nonce, str) for nonce in nonces) or len(set(nonces)) != len(nonces):
        raise ValueError('Every full read must use a unique canonical nonce')
    position = batch.end()
    commands = ['echo ' + shell_nonces[0][0].decode().strip(), 'ls /dev', 'hfsrw mount',
                'hfsrw status', 'hfswrite exercise']
    checked = []
    for entry, row in zip(entries, reads):
        begin, end = frame_markers(row['nonce'])
        start, stop = one_line(raw, begin), one_line(raw, end)
        if not position <= start.start() < start.end() <= stop.start() < stop.end() <= unmount.start():
            raise ValueError('Full file read is outside its mounted write batch')
        actual = parse_file(raw[start.start():stop.end()], entry, row['nonce'])
        if any(type(row.get(key)) is not type(value) or row[key] != value for key, value in actual.items()):
            raise ValueError('Write-vector record differs from independently parsed raw bytes')
        checked.append(actual); position = stop.end()
        commands.append(f'echo {begin.decode()} && hexdump /mnt/hfs{entry["path"]} && echo {end.decode()}')
    restored = one_line(raw, b'hfsrw mounted identity/write guard: errno 22')
    restoration_nonces = list(re.finditer(rb'(?m)^UNMOUNTED_[0-9a-f]{16}\r{0,2}\n', raw))
    if len(restoration_nonces) != 1:
        raise ValueError('Covered-root restoration lacks its unique conditional response')
    restoration = restoration_nonces[0]
    if (not unmount.end() <= restored.start() < restored.end() <= restoration.start()
            < restoration.end() <= shell_nonces[1].start()
            or not PROMPT.search(raw[shell_nonces[1].end():])):
        raise ValueError('Nonforced unmount/restored root/final live shell sequence is incomplete')
    commands.extend(['hfsrw unmount', 'hfsrw status || echo ' + restoration[0].decode().strip(),
                     'echo ' + shell_nonces[1][0].decode().strip()])
    expected_tx = sum(len(text.encode('ascii')) + 1 for text in commands)
    if type(state.get('transmitted_bytes')) is not int or state['transmitted_bytes'] != expected_tx:
        raise ValueError('Exact one-batch transmitted byte coverage differs')
    return dict(serial_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), admission=admission,
                reads=checked, transmitted_bytes=expected_tx, write_batch_attempts=1,
                nonforced_unmount_verified=True, durability_verified=False,
                scope='Independently parsed same-boot write/unmount transcript only; not durability')
