#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only audit of a watchdog-only image. Not physical-trial admission."""
import argparse
import json
from pathlib import Path
import re
import struct

import build_recovery_probe as builder
from build_probe import inspect as inspect_elf

ROOT = builder.ROOT


def leaf_words(raw, symbols, name, size):
    kind, address, extent = symbols[name]
    offset = int(address, 16)-builder.BASE
    if kind not in ('t', 'T') or int(extent, 16) != size or not 0 <= offset <= len(raw)-size:
        raise ValueError('Unexpected fixed-address leaf extent: '+name)
    return struct.unpack('<'+'I'*(size//4), raw[offset:offset+size])


def expected_leaves():
    def mmio(low, opcode):
        return (0xd2800009 | low << 5, 0xf2a00009 | 0x7d20 << 5,
            0xf2c00009 | 0x10 << 5, 0xd5033f9f, opcode, 0xd5033f9f, 0xd65f03c0)
    return {
        'rpi5_recovery_route':mmio(0x1c, 0xb9400120),
        'rpi5_recovery_countdown':mmio(0x24, 0xb9400120),
        'rpi5_recovery_write_countdown':mmio(0x24, 0xb9000120),
        'rpi5_recovery_order':(0xd5033f9f, 0xd65f03c0),
        'rpi5_recovery_counter':(0xd5033fdf, 0xd53be040, 0xd65f03c0),
        'rpi5_psci_query':(0xaa1f03e2, 0xaa1f03e3, 0xd4000003, 0xd65f03c0),
    }


def inspect(package):
    package = package.resolve()
    if package.parent != ROOT/'build/rpi5' or not package.name.startswith('pm-recovery-'):
        raise ValueError('Separate local PM recovery package required')
    manifest = json.loads((package/'manifest.json').read_text())
    tag = manifest.get('trial_tag', '')
    if not isinstance(tag, str) or not re.fullmatch('[0-9a-f]{32}', tag):
        raise ValueError('Invalid image-bound tag')
    elf, binary = package/'probe.elf', package/'probe.bin'
    raw = binary.read_bytes()
    loads = inspect_elf(elf.read_bytes(), raw, builder.BASE)
    paths = {str(p.relative_to(ROOT)) for p in (*builder.INPUTS, *builder.outputs_for(package))}
    pins = manifest.get('sha256', {})
    exact_paths = isinstance(pins, dict) and set(pins) == paths
    hashes = exact_paths and all(builder.sha(ROOT/p) == value for p, value in pins.items())
    symbols = builder.symbols_for(elf)
    leaves = {name:leaf_words(raw, symbols, name, len(words)*4) == words
        for name, words in expected_leaves().items()}
    frames, budget = builder.stack_for(package, symbols)
    checks = dict(
        exact_profile=manifest.get('profile') == builder.PROFILE,
        raw_image_extent=manifest.get('image') == str(binary) and manifest.get('image_bytes') == len(raw),
        entry_and_loads=manifest.get('entry') == loads['entry'] == builder.BASE and
            manifest.get('loads') == loads['loads'],
        exact_hash_evidence_set=exact_paths,
        every_input_object_output_hash_matches=hashes,
        exact_compile_and_link_commands=manifest.get('commands') == builder.commands_for(package, tag),
        configured_local_tools_unchanged=manifest.get('tool_identity') == builder.tool_identity(),
        actual_fixed_address_pm_barrier_counter_query_leaves=all(leaves.values()),
        actual_lease_and_main_linked=all(name in symbols for name in (
            'probe_main', 'probe_el1_main', 'probe_exception', 'rpi5_pcie_watchdog_begin',
            'rpi5_pcie_watchdog_check', 'rpi5_pcie_watchdog_init')),
        no_access_or_cpu_reset_wrappers=not any(name.startswith(('rpi5_access_', 'rpi5_pcie_access_',
            'rpi5_psci_cpu_', 'rpi5_psci_reset')) or name in ('probe_secondary_entry', 'probe_irq_entry')
            for name in symbols),
        conservative_stack_recomputed=manifest.get('stack_frames') == frames and manifest.get('stack_budget') == budget,
        source_stability_declared=manifest.get('sources_stable') is True,
        no_hardware_or_install_claim=all(manifest.get(k) is False for k in builder.FALSE_CLAIMS),
        declared_one_fifteen_second_reload=manifest.get('watchdog_reload_once_seconds') == 15,
        embedded_tag=tag.encode()+b'\0' in raw or (' TAG='+tag).encode() in raw,
        markers_and_stop_contract=all(value in raw for value in (
            b'RPI5XNU:RECOVERY:', b'ENTRY\0', b'EL1\0', b'ARMED\0', b'CHECKED\0', b'FAULT\0',
            b'RESULT\0', b'STOP\0', b'NO_RELOAD WAIT_FOR_RESET PCIE_MMIO=0 DMA=0 RESET_RETURN_PROVEN=0')),
    )
    if not all(checks.values()):
        raise ValueError('Recovery package refused: '+repr([k for k, value in checks.items() if not value]))
    return dict(preflight_pass=True, checks=checks, image=str(binary), image_bytes=len(raw),
        image_sha256=builder.sha(binary), manifest_sha256=builder.sha(package/'manifest.json'),
        trial_tag=tag, stack_budget=budget, installation_admitted=False, physical_execution=False,
        hardware_recovery_proven=False, watchdog_destination_proven=False,
        scope='Local emitted-image audit only. Reset, boot destination and working-image rollback remain board gates')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    print(json.dumps(inspect(parser.parse_args().package), indent=2, sort_keys=True))
