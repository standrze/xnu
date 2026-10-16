#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only local candidate audit. Passing does NOT authorize installation."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_pcie_access_probe as builder
from build_probe import inspect as inspect_elf

ROOT = builder.ROOT


def read_manifest(package):
    return json.loads((package/'manifest.json').read_text())


def inspect(package):
    package = package.resolve()
    if package.parent != ROOT/'build/rpi5' or not package.name.startswith('pcie-access-'):
        raise ValueError('Distinct local PCIe-access package required')
    manifest = read_manifest(package)
    binary, elf = package/'probe.bin', package/'probe.elf'
    raw = binary.read_bytes()
    loads = inspect_elf(elf.read_bytes(),raw,builder.BASE)
    objects = [package/(p.stem+'.o') for p in builder.SOURCES]
    stack_files = [package/(p.stem+'.su') for p in builder.SOURCES if p.suffix == '.c']
    expected_paths = {str(p.relative_to(ROOT)) for p in (*builder.INPUTS,elf,binary,*objects,*stack_files)}
    pins = manifest.get('sha256',{})
    # Never follow arbitrary paths supplied by a manifest. Only known sources
    # and this exact package's expected outputs are part of the evidence set.
    paths_exact = set(pins) == expected_paths
    hashes_match = paths_exact and all(builder.sha(ROOT/p) == value for p,value in pins.items())
    commands = manifest.get('commands',[])
    units = [item for cmd in commands for item in cmd if item.endswith(('.c','.S'))]
    required_flags = {'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align',
                      '-ffreestanding','-fno-builtin','-fno-stack-protector','-mgeneral-regs-only'}
    compiles = [cmd for cmd in commands if '-c' in cmd]
    static_flags = all(required_flags.issubset(cmd) for cmd in compiles)
    symbols_text = subprocess.check_output(['xcrun','llvm-nm','--defined-only','--format=posix',str(elf)],
                                           text=True,timeout=30)
    symbols = {row.split()[0]:row.split()[1:] for row in symbols_text.splitlines() if len(row.split()) >= 4}

    def words(name):
        kind,address,size = symbols[name][:3]
        if kind not in ('t','T') or int(size,16) != 16:
            raise ValueError('Unexpected MMIO leaf extent: '+name)
        offset = int(address,16)-builder.BASE
        return struct.unpack('<4I',raw[offset:offset+16])

    # Check actual emitted leaf bytes, not just source spellings/disassembly.
    leaves = (words('rpi5_access_load32') == (0xd5033f9f,0xb9400000,0xd5033f9f,0xd65f03c0) and
              words('rpi5_access_load16') == (0xd5033f9f,0x79400000,0xd5033f9f,0xd65f03c0))
    frames = []
    for path in stack_files:
        for line in path.read_text().splitlines():
            location,size,kind = line.split('\t')
            name = location.rsplit(':',1)[-1]
            if name not in symbols or symbols[name][0] not in ('t','T'):
                continue
            if kind != 'static' or int(size) < 0:
                raise ValueError('Unbounded emitted stack evidence')
            frames.append(dict(location=location,bytes=int(size),kind=kind))
    total = sum(row['bytes'] for row in frames)
    checks = dict(
        exact_diagnostic_profile=manifest.get('profile') == 'pcie2-readonly-access-v1',
        expected_entry_and_extents=loads['entry'] == manifest.get('entry') == builder.BASE and
            loads['loads'] == manifest.get('loads'),
        exact_source_output_evidence_set=paths_exact,
        every_source_object_output_hash_matches=hashes_match,
        exact_source_list=units == [str(p) for p in builder.SOURCES] and len(compiles) == len(builder.SOURCES),
        strict_freestanding_a76_compilation=static_flags,
        actual_ordered_word_halfword_leaves=leaves,
        stack_recomputed=bool(frames) and frames == manifest.get('stack_frames') and total+512 < 0x4000 and
            manifest.get('stack_budget') == dict(conservative_bytes=total,stack_bytes=0x4000,required_margin=512),
        sources_stable=manifest.get('sources_stable') is True,
        actual_access_enabled=manifest.get('pcie_mmio') is True,
        no_hardware_success_or_install_claim=all(manifest.get(k) is False for k in
            ('physical_execution','installed','hardware_recovery_proven','watchdog_destination_proven')),
        no_xnu_storage_or_endpoint_profile=all(manifest.get(k) is False for k in
            ('xnu_transfer','kernel_embedded','root_embedded','pcie_writes','config_access','irq_enable','dma',
             'reset_calibration_writes')),
        one_watchdog_reload_declared=manifest.get('watchdog_reload_once_seconds') == 15,
        raw_extent_matches=manifest.get('image') == str(binary) and manifest.get('image_bytes') == len(raw),
        access_markers_embedded=all(marker in raw for marker in (
            b'RPI5XNU:ACCESS:ENTRY',b'RPI5XNU:ACCESS:ARMED',b'RPI5XNU:ACCESS:READ_BEGIN',
            b'RPI5XNU:ACCESS:READ_END',b'RPI5XNU:ACCESS:OBSERVED',b'RPI5XNU:ACCESS:FAULT',
            b'RPI5XNU:ACCESS:STOP NO_RELOAD WAIT_FOR_RESET DESTINATION_UNPROVEN')),
    )
    if not all(checks.values()):
        raise ValueError('Access candidate refused: '+repr([k for k,v in checks.items() if not v]))
    return dict(image=str(binary),image_bytes=len(raw),image_sha256=builder.sha(binary),
                manifest_sha256=builder.sha(package/'manifest.json'),preflight_pass=True,checks=checks,
                stack_budget=manifest['stack_budget'],physical_execution=False,
                hardware_recovery_proven=False,installation_admitted=False,
                scope='Local source/output/ELF/leaf-byte/stack/profile consistency, not hardware ownership, reset destination or admission')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package',type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.package),indent=2,sort_keys=True))
