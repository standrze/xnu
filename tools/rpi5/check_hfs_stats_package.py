#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Corrective HFS package screen: inspect the actual mockfs VFS getter slot.

Does not open devices, stage media or prove runtime statfs/mount behavior.
The original read-only package screen remains unchanged for historical trials.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from audit_macho import inspect as inspect_macho
from check_hfs_read_package import inspect as inspect_hfs

ROOT = Path(__file__).resolve().parents[2]
FIELDS = ('vfs_mount', 'vfs_start', 'vfs_unmount', 'vfs_root', 'vfs_quotactl',
          'vfs_getattr', 'vfs_sync', 'vfs_vget', 'vfs_fhtovp', 'vfs_vptofh',
          'vfs_init', 'vfs_sysctl', 'vfs_setattr', 'vfs_ioctl', 'vfs_vget_snapdir')
RESERVED = ('vfs_reserved5', 'vfs_reserved4', 'vfs_reserved3', 'vfs_reserved2', 'vfs_reserved1')


def linked_getter(raw, segments, symbols, header):
    # A commented historical vfs_statfs field is not part of this ABI.
    clean = re.sub(r'/\*.*?\*/|//[^\n]*', '', header, flags=re.S)
    matches = re.findall(r'struct vfsops\s*\{([^}]+)\}', clean, re.S)
    if len(matches) != 1:
        raise ValueError('Expected the pinned unique vfsops declaration')
    declarations = matches[0].split(';')
    if declarations[-1].strip() or len(declarations) != len(FIELDS) + len(RESERVED) + 1:
        raise ValueError('Changed vfsops member layout')
    names = []
    for declaration in declarations[:len(FIELDS)]:
        field = re.fullmatch(r'\s*int\s*\(\*(vfs_\w+)\)\s*\(.*\)\s*', declaration, re.S)
        if not field:
            raise ValueError('Unexpected non-function-pointer vfsops member')
        names.append(field[1])
    if tuple(names) != FIELDS:
        raise ValueError('Changed vfsops getter offset')
    for declaration, name in zip(declarations[len(FIELDS):-1], RESERVED):
        if not re.fullmatch(r'\s*void\s*\*\s*' + name + r'\s*', declaration):
            raise ValueError('Changed reserved vfsops pointer layout')

    def address(name):
        rows = [line.split() for line in symbols.splitlines() if line.endswith(' ' + name)]
        if len(rows) != 1 or not re.fullmatch('[0-9a-fA-F]{16}', rows[0][0]):
            raise ValueError('Missing or duplicate linked symbol: ' + name)
        return int(rows[0][0], 16)

    def location(value, size, executable):
        owners = [s for s in segments if s['vmaddr'] <= value and
                  value + size <= s['vmaddr'] + s['filesize']]
        if len(owners) != 1 or bool(owners[0]['initprot'] & 4) != executable:
            raise ValueError('Getter/table is not uniquely file-backed with expected protections')
        owner = owners[0]
        offset = owner['fileoff'] + value - owner['vmaddr']
        if offset < 0 or offset + size > len(raw):
            raise ValueError('Getter/table extends past kernel bytes')
        return offset

    table, getter = address('_mockfs_vfsops'), address('_mockfs_vfs_getattr')
    offset = location(table, (len(FIELDS) + len(RESERVED)) * 8, False)
    location(getter, 4, True)
    slot = FIELDS.index('vfs_getattr') * 8
    target = struct.unpack_from('<Q', raw, offset + slot)[0]
    if target != getter:
        raise ValueError('Actual mockfs VFS getter slot does not address the corrective handler')
    return dict(table_address=hex(table), getter_address=hex(getter), slot_offset=slot,
                slot_value=hex(target), vfsops_header_sha256=hashlib.sha256(header.encode()).hexdigest(),
                scope='Linked pointer wiring only; not runtime dispatch or HFS acceptance')


def inspect(package, kernel, init, gate3_baseline, shell_baseline, kernel_build):
    report = inspect_hfs(package, kernel, init, gate3_baseline, shell_baseline, kernel_build)
    raw = kernel.read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['kernel_sha256']:
        raise ValueError('Kernel changed after original package screen')
    wiring = linked_getter(raw, inspect_macho(raw)['segments'],
                           subprocess.check_output(['xcrun', 'nm', '-nm', str(kernel)], text=True),
                           (ROOT / 'bsd/sys/mount.h').read_text())
    report['checks']['ramroot_statfs_getter_wired'] = True
    report.update(preflight_pass=all(report['checks'].values()), hfs_ramroot_stats_trial=True,
                  linked_ramroot_statfs=wiring)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    for name in ('kernel', 'init', 'gate3-baseline', 'shell-baseline', 'kernel-build', 'output'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    report = inspect(args.package, args.kernel, args.init, args.gate3_baseline, args.shell_baseline, args.kernel_build)
    # Never overwrite a prior trial's preflight.
    with args.output.open('x') as output:
        output.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return 0 if report['preflight_pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
