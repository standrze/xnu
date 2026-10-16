#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Delay terminal admission telemetry until the first actual watchdog reload.

This does not serialize arbitrary console writers, extend a deadline, enable
hardware, or turn a corrupted prior trace into success. All changes are in a
fresh PE source/object and distinct complete kernel.
"""
import argparse
import json
from pathlib import Path
import re

try:
    from . import root_capacity_bounded_kernel as prior
except ImportError:
    import root_capacity_bounded_kernel as prior

ROOT, audit = prior.ROOT, prior.audit
BASE = ROOT / 'build/rpi5/root-capacity-rp1-kernel-20261013-bounded'
BASE_SHA = '30a8a72bacd9add432d631b0097bf3938f193eac586298e4cb7e072886b23a7a'
MARKER = 'RPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=%u\n'
OLD_PRINT = '\tkprintf("RPI5XNU:TERMINAL:WATCHDOG SECONDS=%u\\n", RPI5_TERMINAL_WDOG_SECONDS);\n'
DECL = 'static bool rpi5_wdog_terminal_enabled;\n'
RELOAD = '\trpi5_wdog_reloads++;\n'
ANNOUNCE = '''\tif (rpi5_wdog_terminal_enabled && !rpi5_wdog_terminal_reported) {
\t\trpi5_wdog_terminal_reported = true;
\t\tkprintf("\\nRPI5XNU:TERMINAL:WATCHDOG_READY SECONDS=%u\\n",
\t\t    RPI5_TERMINAL_WDOG_SECONDS);
\t}
'''


def transform(source):
    for needle in (OLD_PRINT, DECL, RELOAD):
        if source.count(needle) != 1:
            raise ValueError('Unexpected bounded PE telemetry source')
    return source.replace(OLD_PRINT, '').replace(DECL, DECL +
        'static bool rpi5_wdog_terminal_reported;\n').replace(RELOAD, RELOAD + ANNOUNCE)


def build(output):
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Frozen bounded parent changed')
    old = json.loads(manifest.read_text())
    pins = old['inputs_sha256'] | old['generated_sha256'] | {str(manifest): BASE_SHA,
        str(Path(__file__).resolve()): audit.sha(Path(__file__))}
    def verify():
        for name, digest in pins.items():
            if audit.sha(Path(name)) != digest:
                raise ValueError('Readiness kernel input changed: ' + name)
    verify()
    output = output.resolve()
    if output.parent != ROOT / 'build/rpi5':
        raise ValueError('Fresh local build output required')
    output.mkdir(exist_ok=False)
    source, obj = output / 'pe_fiq.c', output / 'pe_fiq.c.o'
    source.write_text(transform((BASE / 'pe_fiq.c').read_text()))
    pins[str(source)] = audit.sha(source)
    commands = []
    def execute(command, name, cwd=ROOT, warnings=False):
        row = audit.execute(list(map(str, command)), cwd, output / (name + '.log'))
        commands.append(row)
        if row['returncode'] or (row['warning_count'] and not warnings):
            raise ValueError('Ready kernel operation failed: ' + row['log'])
        return row
    command = next(r['command'] for r in old['commands'] if r['log'].endswith('/compile.log'))
    args = command[:command.index('-MD')]
    args = [str(source) if a == str(BASE / 'pe_fiq.c') else a for a in args]
    cwd = audit.OBJ / 'pexpert/DEVELOPMENT'
    dep, actual = output / 'pe_fiq.d', output / 'pe_fiq.actual.d'
    execute([a for a in args if a != '-c'] + ['-M', '-MF', dep], 'deps', cwd)
    deps = audit.dependency_paths(dep, cwd)
    for path in deps:
        digest = audit.sha(path)
        if str(path) in pins and pins[str(path)] != digest:
            raise ValueError('Conflicting consumed PE header')
        pins[str(path)] = digest
    execute(args + ['-MD', '-MF', actual, '-o', obj], 'compile', cwd)
    if audit.dependency_paths(actual, cwd) != deps:
        raise ValueError('Actual PE dependency set changed')
    assembly = output / 'pe_fiq.s'
    execute([a for a in args if a != '-c'] + ['-S', '-o', assembly], 'assembly', cwd)
    text = assembly.read_text()
    start = text.index('_pe_rpi5_watchdog_enable_terminal:')
    function = text[start:text.index('; -- End function', start)]
    if not re.search(r'\bmov\s+w[0-9]+, #180\b', function) or '#3600' in function:
        raise ValueError('Emitted terminal deadline changed')
    objects = [Path(p) for p in (BASE / 'kernel.root96-rp1-bounded.filelist').read_text().splitlines()]
    if len(objects) != len(set(objects)) or objects.count(BASE / 'pe_fiq.c.o') != 1:
        raise ValueError('Ambiguous actual PE object replacement')
    objects = [obj if p == BASE / 'pe_fiq.c.o' else p for p in objects]
    filelist = output / 'kernel.ready.filelist'
    filelist.write_text(''.join(str(p) + '\n' for p in objects))
    kernel, unstripped, linkmap = output / 'kernel.ready', output / 'kernel.unstripped', output / 'kernel.map'
    link = next(r['command'] for r in old['commands'] if r['log'].endswith('/link.log'))
    replacements = {str(BASE / 'kernel.root96-rp1-bounded.filelist'): str(filelist),
        str(BASE / 'kernel.unstripped'): str(unstripped),
        '-Wl,-map,' + str(BASE / 'kernel.map'): '-Wl,-map,' + str(linkmap)}
    if any(link.count(name) != 1 for name in replacements):
        raise ValueError('Ambiguous full kernel link')
    row = execute([replacements.get(a, a) for a in link], 'link', warnings=True)
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != old['baseline_linker_warnings']:
        raise ValueError('New kernel linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'strip')
    symbols = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(symbols + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Undefined kernel symbols')
    mapped = linkmap.read_text(errors='surrogateescape')
    if str(BASE / 'pe_fiq.c.o') in mapped or any(str(p) not in mapped for p in objects):
        raise ValueError('Actual link constituents changed')
    linked = prior.capacity.previous.full.linked_audit(kernel.read_bytes(), symbols, mapped)
    if MARKER.encode() not in kernel.read_bytes():
        raise ValueError('Missing linked readiness marker')
    verify()
    result = dict(profile='root96-terminal-ready-kernel-v1', parent_manifest_sha256=BASE_SHA,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size,
        node_capacity=96, terminal_deadline_seconds=180, hardware_reload_interval_seconds=15,
        telemetry_only_source_change=True, deadline_extended=False,
        first_successful_terminal_reload_marker=MARKER, arbitrary_console_serialization=False,
        modified_pe_source_sha256=audit.sha(source), inputs_sha256=pins, commands=commands,
        generated_sha256={str(p): audit.sha(p) for p in output.iterdir() if p.is_file()},
        link=linked, baseline_linker_warnings=warnings, installed=False, pi_executed=False,
        boot_caller_added=False, controller_initialized=False, ethernet_proven=False)
    (output / 'manifest.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps({k: report[k] for k in ('kernel', 'kernel_sha256', 'kernel_bytes')}))
