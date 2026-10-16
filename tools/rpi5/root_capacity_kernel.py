#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Relink the full Pi kernel with a separate 96-node mockfs header overlay."""
import argparse
import json
from pathlib import Path

try:
    from . import build_pcie_fw_client_kernel as previous
    from . import root_capacity_profile as profile
except ImportError:
    import build_pcie_fw_client_kernel as previous
    import root_capacity_profile as profile

ROOT, audit = previous.ROOT, previous.audit
BASE = ROOT / 'build/rpi5/pcie-fw-client-kernel-20261013-final'
BASE_SHA = '4a2c9170a0413415410cf7719310ad1bd65e207f2d62d951e2b35502304d990e'
NAMES = ('mockfs_fsnode', 'mockfs_vfsops', 'mockfs_vnops')


def build(output):
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted complete Pi kernel receipt changed')
    prior = json.loads(manifest.read_text())
    captured = {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA}
    for path, digest in captured.items():
        if audit.sha(Path(path)) != digest:
            raise ValueError('Preserved Pi kernel input changed: ' + path)
    output = output.resolve()
    if output.parent != ROOT / 'build/rpi5':
        raise ValueError('A fresh directory directly under build/rpi5 is required')
    output.mkdir(exist_ok=False)
    overlay = output / 'overlay'
    header = overlay / 'miscfs/mockfs/rpi5_ramroot_format.h'
    header.parent.mkdir(parents=True)
    header.write_bytes(profile.kernel_header())
    for path in (Path(__file__).resolve(), Path(profile.__file__).resolve(), profile.PACKER, profile.HEADER):
        captured[str(path)] = audit.sha(path)
    objects = [Path(p) for p in (BASE / 'kernel.pcie-fw-client.filelist').read_text().splitlines()]
    if len(objects) != len(set(objects)):
        raise ValueError('Duplicate original kernel constituent')
    commands, compiles, replacements = [], [], {}

    def execute(args, name, cwd=ROOT, warnings=False):
        row = audit.execute(args, cwd, output / (name + '.log'))
        commands.append(row)
        if row['returncode'] or (not warnings and row['warning_count']):
            raise ValueError('Capacity build failed: ' + row['log'])
        return row

    for name in NAMES:
        matches = [p for p in objects if p.name == name + '.o']
        if len(matches) != 1:
            raise ValueError('Missing/ambiguous mockfs object: ' + name)
        old = matches[0]
        template_path = old.with_suffix('.o.json')
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        captured[str(template_path)] = audit.sha(template_path)
        source, cwd = Path(template['file']), Path(template['directory'])
        args = list(template['arguments'])
        if args.count('-o') != 1 or args.count('-c') != 1 or args.count(str(source)) != 1:
            raise ValueError('Ambiguous accepted mockfs invocation')
        i = args.index('-o')
        del args[i:i + 2]
        obj = output / (name + '.o')
        baseline = output / (name + '.baseline.o')
        baseline_row = execute(args + ['-o', str(baseline)], name + '-baseline', cwd, warnings=True)
        baseline_warnings = Path(baseline_row['log']).read_text()
        args[1:1] = ['-I', str(overlay)]
        dep = output / (name + '.d')
        execute([a for a in args if a != '-c'] + ['-M', '-MF', str(dep)], name + '-deps', cwd)
        dependencies = audit.dependency_paths(dep, cwd)
        if header not in dependencies or profile.HEADER in dependencies:
            raise ValueError('Actual compiler did not select the isolated capacity header')
        for path in dependencies:
            digest = audit.sha(path)
            if str(path) in captured and captured[str(path)] != digest:
                raise ValueError('Conflicting capacity input: ' + str(path))
            captured[str(path)] = digest
        args += ['-o', str(obj)]
        row = execute(args, name + '-compile', cwd, warnings=True)
        if Path(row['log']).read_text() != baseline_warnings:
            raise ValueError('Capacity overlay introduced compiler diagnostics')
        row['object_sha256'] = audit.sha(obj)
        row['baseline_warning_count'] = baseline_row['warning_count']
        compiles.append(row)
        replacements[old] = obj
        execute([a for a in args[:-2] if a != '-c'] + ['-S', '-o', str(output / (name + '.s'))],
                name + '-assembly', cwd, warnings=True)
    objects = [replacements.get(p, p) for p in objects]
    filelist = output / 'kernel.root96.filelist'
    filelist.write_text(''.join(str(p) + '\n' for p in objects))
    kernel, unstripped, linkmap = output / 'kernel.root96', output / 'kernel.unstripped', output / 'kernel.map'
    rows = [row for row in prior['commands'] if Path(row['log']).name == 'kernel-link.log']
    if len(rows) != 1:
        raise ValueError('Missing accepted final link invocation')
    args = rows[0]['command']
    change = {str(BASE / 'kernel.pcie-fw-client.filelist'): str(filelist),
              str(BASE / 'kernel.unstripped'): str(unstripped),
              '-Wl,-map,' + str(BASE / 'kernel.map'): '-Wl,-map,' + str(linkmap)}
    if any(args.count(old) != 1 for old in change):
        raise ValueError('Ambiguous accepted link output')
    row = execute([change.get(a, a) for a in args], 'kernel-link', warnings=True)
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']:
        raise ValueError('New full-kernel linker warning')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Undefined symbols in expanded Pi kernel')
    map_text = linkmap.read_text(errors='surrogateescape')
    if any(str(old) in map_text for old in replacements) or any(str(p) not in map_text for p in objects):
        raise ValueError('Actual full kernel map does not select all replacement constituents')
    linked = previous.full.linked_audit(kernel.read_bytes(), listing, map_text)
    for path, digest in captured.items():
        if audit.sha(Path(path)) != digest:
            raise ValueError('Capacity input changed during build: ' + path)
    generated = {str(p): audit.sha(p) for p in output.rglob('*') if p.is_file()}
    report = dict(profile='rpi5-ramroot-96-v1', parent_manifest=str(manifest),
                  parent_manifest_sha256=BASE_SHA, kernel=str(kernel), kernel_sha256=audit.sha(kernel),
                  kernel_bytes=kernel.stat().st_size, node_capacity=profile.MAX_NODES,
                  metadata_bytes=16384, metadata_used_at_capacity=32 + 96 * 128,
                  inputs_sha256=captured, generated_sha256=generated, commands=commands,
                  compiles=compiles, link=linked, replaced_objects={str(k): str(v) for k, v in replacements.items()},
                  original_sources_unchanged=True, all_mount_structure_users_recompiled=True,
                  undefined_symbols=[], baseline_linker_warnings=warnings, complete_kernel_link_proven=True,
                  installed=False, pi_executed=False, sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps({k: report[k] for k in ('kernel', 'kernel_sha256', 'kernel_bytes', 'node_capacity', 'pi_executed')}))
