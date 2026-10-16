#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Derive a 180-second serial diagnostic kernel from the combined OS candidate."""
import argparse
import json
from pathlib import Path
import re

try:
    from . import root_capacity_kernel as capacity
except ImportError:
    import root_capacity_kernel as capacity

ROOT, audit = capacity.ROOT, capacity.audit
BASE = ROOT / 'build/rpi5/root-capacity-rp1-kernel-20261013-v2'
BASE_SHA = 'c1e8d2764433025114af70ac6ce51e43a84142d33b63e2c98b3cb2176d3b28d7'
PE_BASE = capacity.BASE
OLD_SOURCE = PE_BASE / 'pe_fiq.c'
OLD_OBJECT = PE_BASE / 'pe_fiq.c.o'
OLD = '#define RPI5_TERMINAL_WDOG_SECONDS 3600U'
NEW = '#define RPI5_TERMINAL_WDOG_SECONDS 180U'


def build(output):
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Combined kernel receipt changed')
    prior = json.loads(manifest.read_text())
    captured = {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA}
    captured[str(Path(__file__).resolve())] = audit.sha(Path(__file__))
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Bounded trial input changed: ' + name)
    original = OLD_SOURCE.read_text()
    if original.count(OLD) != 1 or str(OLD_SOURCE) not in captured:
        raise ValueError('Expected one pinned terminal deadline definition')
    output = output.resolve()
    if output.parent != ROOT / 'build/rpi5':
        raise ValueError('A fresh directory directly under build/rpi5 is required')
    output.mkdir(exist_ok=False)
    source, obj = output / 'pe_fiq.c', output / 'pe_fiq.c.o'
    source.write_text(original.replace(OLD, NEW))
    captured[str(source)] = audit.sha(source)
    commands = []
    def execute(args, name, cwd=ROOT, warnings=False):
        row = audit.execute(args, cwd, output / (name + '.log'))
        commands.append(row)
        if row['returncode'] or (not warnings and row['warning_count']):
            raise ValueError('Bounded kernel operation failed: ' + row['log'])
        return row
    pe = json.loads((PE_BASE / 'manifest.json').read_text())
    compiles = [r['command'] for r in pe['compiles'] if str(OLD_SOURCE) in r['command']]
    if len(compiles) != 1 or compiles[0][-2:] != ['-o', str(OLD_OBJECT)]:
        raise ValueError('Actual original PE compiler invocation ambiguous')
    args = [str(source) if a == str(OLD_SOURCE) else a for a in compiles[0][:-2]]
    cwd = audit.OBJ / 'pexpert/DEVELOPMENT'
    dep = output / 'pe_fiq.d'
    execute([a for a in args if a != '-c'] + ['-M', '-MF', str(dep)], 'deps', cwd)
    dependencies = audit.dependency_paths(dep, cwd)
    for path in dependencies:
        digest = audit.sha(path)
        if str(path) in captured and captured[str(path)] != digest:
            raise ValueError('Conflicting actual PE header')
        captured[str(path)] = digest
    actual_dep = output / 'pe_fiq.actual.d'
    execute(args + ['-MD', '-MF', actual_dep, '-o', obj], 'compile', cwd)
    if audit.dependency_paths(actual_dep, cwd) != dependencies:
        raise ValueError('Actual PE compile dependency set changed')
    assembly = output / 'pe_fiq.s'
    execute([a for a in args if a != '-c'] + ['-S', '-o', assembly], 'assembly', cwd)
    text = assembly.read_text()
    start = text.index('_pe_rpi5_watchdog_enable_terminal:')
    end = text.index('; -- End function', start)
    function = text[start:end]
    if not re.search(r'\bmov\s+w[0-9]+, #180\b', function) or re.search(r'#3600\b', function):
        raise ValueError('Actual emitted terminal function does not use the 180-second constant')
    objects = [Path(p) for p in (BASE / 'kernel.root96-rp1.filelist').read_text().splitlines()]
    if len(objects) != len(set(objects)) or objects.count(OLD_OBJECT) != 1:
        raise ValueError('Original PE replacement ambiguous')
    objects = [obj if p == OLD_OBJECT else p for p in objects]
    filelist = output / 'kernel.root96-rp1-bounded.filelist'
    filelist.write_text(''.join(str(p) + '\n' for p in objects))
    kernel, unstripped, linkmap = output / 'kernel.root96-rp1-bounded', output / 'kernel.unstripped', output / 'kernel.map'
    rows = [r for r in prior['commands'] if str(BASE / 'kernel.root96-rp1.filelist') in r['command']]
    if len(rows) != 1:
        raise ValueError('Missing original complete link invocation')
    args = rows[0]['command']
    replacements = {str(BASE / 'kernel.root96-rp1.filelist'): str(filelist),
                    str(BASE / 'kernel.unstripped'): str(unstripped),
                    '-Wl,-map,' + str(BASE / 'kernel.map'): '-Wl,-map,' + str(linkmap)}
    if any(args.count(old) != 1 for old in replacements):
        raise ValueError('Ambiguous final kernel output')
    row = execute([replacements.get(a, a) for a in args], 'link', warnings=True)
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']:
        raise ValueError('New bounded kernel linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Undefined symbols in bounded kernel')
    textmap = linkmap.read_text(errors='surrogateescape')
    if str(OLD_OBJECT) in textmap or any(str(p) not in textmap for p in objects):
        raise ValueError('Actual bounded kernel constituents differ')
    linked = capacity.previous.full.linked_audit(kernel.read_bytes(), listing, textmap)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Bounded kernel input changed during build: ' + name)
    report = dict(profile='rpi5-ramroot-96-v1', kernel_profile='root96-rp1-config-bounded-v1',
                  parent_manifest_sha256=BASE_SHA, kernel=str(kernel), kernel_sha256=audit.sha(kernel),
                  kernel_bytes=kernel.stat().st_size, node_capacity=96, inputs_sha256=captured,
                  generated_sha256={str(p): audit.sha(p) for p in output.iterdir() if p.is_file()},
                  commands=commands, link=linked, baseline_linker_warnings=warnings,
                  terminal_deadline_seconds=180, terminal_deadline_only_source_change=True,
                  original_pe_source_sha256=captured[str(OLD_SOURCE)], modified_pe_source_sha256=audit.sha(source),
                  software_deadline_disables_reload=True, hardware_reload_interval_seconds=15,
                  emitted_terminal_constant_verified=True, complete_kernel_link_proven=True,
                  installed=False, pi_executed=False, automatic_recovery_proven=False,
                  endpoint_config_writes=0, boot_caller_added=False, full_lifecycle_provider_added=False,
                  ethernet_proven=False, dma_authorized=False)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps({k: report[k] for k in ('kernel', 'kernel_sha256', 'kernel_bytes', 'terminal_deadline_seconds', 'pi_executed')}))
