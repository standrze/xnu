#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Correlate physical raw errno evidence with preserved linked VFS tables.

Read-only host analysis. A matching omission is not a physically verified fix.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_statprobe_trial as physical
from audit_macho import inspect as inspect_macho
from check_hfs_stats_package import FIELDS, RESERVED, linked_getter
from prepare_zsh_trial_root import SMOKE

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'build/rpi5/shell-userland-20261011/kernel.development.bcm2712'
CORRECTED = ROOT / 'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712/kernel.development.bcm2712'
PINS = {OLD: 'd133f3a21ff9d3397aed7dfdd04210fe79061d8919d5046010dfa1919980a10f',
        CORRECTED: '674e6a763a01a7e4becf0399d03641aa4e43ec1c1d995d67623546b9d64f5aad'}


def table_slot(raw, segments, symbols):
    rows = [line.split() for line in symbols.splitlines() if line.endswith(' _mockfs_vfsops')]
    if len(rows) != 1 or not re.fullmatch('[0-9a-fA-F]{16}', rows[0][0]):
        raise ValueError('Missing or duplicate linked mockfs table')
    address = int(rows[0][0], 16)
    length = 8 * (len(FIELDS) + len(RESERVED))
    owners = [s for s in segments if s['vmaddr'] <= address and
              address + length <= s['vmaddr'] + s['filesize']]
    if len(owners) != 1 or owners[0]['initprot'] & 4:
        raise ValueError('Mockfs table is not uniquely non-executable/file-backed')
    slot = FIELDS.index('vfs_getattr') * 8
    offset = owners[0]['fileoff'] + address - owners[0]['vmaddr'] + slot
    if not 0 <= offset <= len(raw) - 8:
        raise ValueError('Mockfs getter slot exceeds kernel file')
    target = struct.unpack_from('<Q', raw, offset)[0]
    return dict(table_address=hex(address), slot_offset=slot, target=hex(target))


def inspect_kernel(path):
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PINS[path]:
        raise ValueError('Preserved kernel changed: ' + str(path))
    symbols = subprocess.check_output(['xcrun', 'nm', '-nm', str(path)], text=True, timeout=30)
    segments = inspect_macho(raw)['segments']
    result = dict(kernel=str(path), kernel_sha256=digest, **table_slot(raw, segments, symbols))
    result['handler_symbol_present'] = any(line.endswith(' _mockfs_vfs_getattr') for line in symbols.splitlines())
    if result['target'] != '0x0':
        result['wiring'] = linked_getter(raw, segments, symbols, (ROOT/'bsd/sys/mount.h').read_text())
    return result


def audit(directory):
    result = physical.audit(directory)
    paths = result['observations']['paths']
    if [row['path'] for row in paths] != list(physical.trial.PATHS):
        raise ValueError('Unexpected physical diagnostic targets')
    for index, row in enumerate(paths[:3]):
        if row['access_f_ok'] != 0 or row['access_r_ok'] != 0:
            raise ValueError('Not the observed access-success/metadata-failure profile')
        for stat in (row['stat'], row['lstat'], *(opened['fstat'] for opened in row['opens'])):
            if stat['rc'] != -45 or stat['raw_hex'] != 'a5'*144 or stat['guards'] != 1:
                raise ValueError('Not the captured ENOTSUP/untouched-buffer evidence')
        for opened in row['opens']:
            if (opened['fd'] != 3 or opened['duplicate'] != 10 or opened['getfd'] != 0
                    or opened['getfl'] != 0 or opened['duplicate_read']['rc'] != 16
                    or opened['original_read']['rc'] != 16 or opened['duplicate_close'] != 0
                    or opened['original_close'] != 0):
                raise ValueError('Not the captured successful open/dup/read profile')
            expected = SMOKE if index == 0 else b'Experimental Darwin XNU on Raspberry Pi 5. Read-only RAM root.\n'
            if (bytes.fromhex(opened['duplicate_read']['hex']) != expected[:16]
                    or bytes.fromhex(opened['original_read']['hex']) != expected[16:32]):
                raise ValueError('Physical reads differ from actual preserved file contents/shared offset')
    missing = paths[3]
    if (missing['access_f_ok'], missing['access_r_ok'], missing['stat']['rc'], missing['lstat']['rc']) != (-2,)*4:
        raise ValueError('Missing-file negative control differs')
    old, corrected = inspect_kernel(OLD), inspect_kernel(CORRECTED)
    if old['target'] != '0x0' or old['handler_symbol_present'] or not corrected.get('wiring'):
        raise ValueError('Preserved kernels do not have the expected contrasting getter wiring')
    sources = ('bsd/vfs/vfs_vnops.c', 'bsd/vfs/kpi_vfs.c', 'bsd/vfs/vfs_subr.c',
               'bsd/miscfs/mockfs/mockfs_vfsops.c', 'bsd/sys/errno.h')
    return dict(status='physical_metadata_failure_correlated',
                physical_serial_sha256=result['serial_sha256'], physical_state_sha256=result['state_sha256'],
                runtime_metadata_errno=45, runtime_metadata_buffer_untouched=True,
                runtime_plain_and_noctty_open_dup_read_passed=True, old_kernel=old, corrective_kernel=corrected,
                source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
                diagnosis='Existing-file stat requires allocation metadata; mount-stat refresh reaches missing VFS_GETATTR slot',
                diagnosis_is_inference=True, corrective_kernel_pi_zsh_tested=False,
                abi_fix_physically_verified=False, original_script_acceptance=False,
                strict_mounted_root_trial_passed=result['strict_mounted_root_trial_passed'],
                networking=False, durability=False,
                next='Review storage-off corrective-kernel package, then repeat raw metadata and original zsh script acceptance')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    encoded = json.dumps(audit(args.directory), indent=2) + '\n'
    if args.report:
        with args.report.open('x') as output: output.write(encoded)
    print(encoded, end='')


if __name__ == '__main__':
    main()
