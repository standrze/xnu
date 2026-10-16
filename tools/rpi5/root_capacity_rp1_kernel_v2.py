#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Combine independently built RP1 configuration and 96-node Pi mockfs objects."""
import argparse
import json
from pathlib import Path

try:
    from . import root_capacity_kernel as capacity
except ImportError:
    import root_capacity_kernel as capacity

ROOT, audit = capacity.ROOT, capacity.audit
CAPACITY = ROOT / 'build/rpi5/root-capacity-kernel-20261013-b'
CAPACITY_SHA = 'cfeb6b6295f7d2e5efac8c33d3b5cd1783d4460e231ba3e995467c63a942a48a'
RP1 = ROOT / 'build/rpi5/rp1-config-kernel-20261013-v2'
RP1_SHA = '0f8d791d1bf5f2a084845c485cb9d498b46275ffbe3befb9f89078fa233d0032'


def build(output):
    captured, records = {}, []
    for base, pin in ((CAPACITY, CAPACITY_SHA), (RP1, RP1_SHA)):
        path = base / 'manifest.json'
        if audit.sha(path) != pin:
            raise ValueError('Accepted composition input receipt changed')
        record = json.loads(path.read_text())
        records.append(record)
        for name, digest in {**record['inputs_sha256'], **record['generated_sha256'], str(path): pin}.items():
            if name in captured and captured[name] != digest:
                raise ValueError('Conflicting independently built kernel input: ' + name)
            captured[name] = digest
    captured[str(Path(__file__).resolve())] = audit.sha(Path(__file__))
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Combined kernel input changed: ' + name)
    expanded, rp1 = records
    replacements = {Path(old): Path(new) for old, new in expanded['replaced_objects'].items()}
    if len(replacements) != 3 or {p.stem for p in replacements} != set(capacity.NAMES):
        raise ValueError('Expected exactly three separately compiled mockfs replacements')
    objects = [Path(line) for line in (RP1 / 'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(objects) != len(set(objects)) or any(objects.count(old) != 1 for old in replacements):
        raise ValueError('RP1 parent does not contain the exact original mockfs objects')
    objects = [replacements.get(path, path) for path in objects]
    if any(str(path) not in captured for path in objects):
        raise ValueError('Unpinned combined kernel object')
    output = output.resolve()
    if output.parent != ROOT / 'build/rpi5':
        raise ValueError('A fresh directory directly under build/rpi5 is required')
    output.mkdir(exist_ok=False)
    filelist = output / 'kernel.root96-rp1.filelist'
    filelist.write_text(''.join(str(path) + '\n' for path in objects))
    kernel, unstripped, linkmap = output / 'kernel.root96-rp1', output / 'kernel.unstripped', output / 'kernel.map'
    commands = []

    def execute(args, name, warnings=False):
        row = audit.execute(args, ROOT, output / (name + '.log'))
        commands.append(row)
        if row['returncode'] or (not warnings and row['warning_count']):
            raise ValueError('Combined kernel failed: ' + row['log'])
        return row

    rows = [row for row in rp1['commands'] if str(RP1 / 'kernel.rp1-config.filelist') in row['command']]
    if len(rows) != 1:
        raise ValueError('Missing final RP1 kernel link invocation')
    args = rows[0]['command']
    changes = {str(RP1 / 'kernel.rp1-config.filelist'): str(filelist),
               str(RP1 / 'kernel.unstripped'): str(unstripped),
               '-Wl,-map,' + str(RP1 / 'kernel.map'): '-Wl,-map,' + str(linkmap)}
    if any(args.count(old) != 1 for old in changes):
        raise ValueError('Ambiguous final RP1 kernel output')
    row = execute([changes.get(a, a) for a in args], 'kernel-link', warnings=True)
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != rp1['baseline_linker_warnings']:
        raise ValueError('Composition introduced kernel linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Combined kernel has unresolved symbols')
    textmap = linkmap.read_text(errors='surrogateescape')
    if any(str(old) in textmap for old in replacements) or any(str(p) not in textmap for p in objects):
        raise ValueError('Actual link does not contain the intended combined constituents')
    linked = capacity.previous.full.linked_audit(kernel.read_bytes(), listing, textmap)
    names = capacity.previous.full.symbols(listing)
    for name in rp1['required_implementations']:
        values = names.get(name, [])
        if len(values) != 1 or not any(s['initprot'] & 4 and s['vmaddr'] <= values[0] and
                values[0] + 4 <= s['vmaddr'] + s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Combined RP1 implementation is missing or not executable: ' + name)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Combined kernel source changed during link: ' + name)
    generated = {str(p): audit.sha(p) for p in output.iterdir() if p.is_file()}
    report = dict(profile='rpi5-ramroot-96-v1', kernel_profile='root96-rp1-config-v2',
                  kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size,
                  node_capacity=96, metadata_bytes=16384, metadata_used_at_capacity=12320,
                  capacity_parent_sha256=CAPACITY_SHA, rp1_parent_sha256=RP1_SHA,
                  inputs_sha256=captured, generated_sha256=generated, commands=commands,
                  link=linked, required_rp1_implementations=rp1['required_implementations'],
                  replaced_objects={str(k): str(v) for k, v in replacements.items()},
                  all_mount_structure_users_recompiled=True, complete_kernel_link_proven=True,
                  undefined_symbols=[], baseline_linker_warnings=warnings,
                  actual_controller_then_rp1_config=rp1['actual_controller_then_rp1_config'],
                  endpoint_header_reads=rp1['endpoint_header_reads'], selector_writes=rp1['selector_writes'],
                  endpoint_config_writes=0, boot_caller_added=False, full_lifecycle_provider_added=False,
                  installed=False, pi_executed=False, ethernet_proven=False, dma_authorized=False)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps({k: report[k] for k in ('kernel', 'kernel_sha256', 'kernel_bytes', 'node_capacity', 'pi_executed')}))
