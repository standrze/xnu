#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile the real unused-window continuation into a separate complete kernel."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_pcie_kernel as full
except ImportError:
    import build_pcie_kernel as full

audit, ROOT = full.audit, full.ROOT
BASE = ROOT / 'build/rpi5/pcie-kernel-20261012-final'
BASE_SHA = '39628890ad03a7d255e1a9d9e36fadf21435542c6005d73834053fbd7fe3d52c'
PATCH = ROOT / 'tools/rpi5/patches/pcie-unused-transport.patch'
CORE = ROOT / 'loader/rpi5/pcie_unused.c'
SOURCE_NAMES = ('BCM2712PCIePHYTransport.cpp', 'BCM2712PCIePHYTransport.h')


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted complete-kernel receipt changed')
    prior = json.loads(manifest.read_text())
    if not prior['complete_kernel_link_proven'] or not prior['original_kernel_replay']['all_non_uuid_bytes_identical']:
        raise ValueError('Accepted original complete-link evidence missing')
    captured, original, extras, flags, archive, constituents = full.inputs()
    for name, digest in {**prior['inputs_sha256'], **prior['generated_sha256'],
                         str(manifest): BASE_SHA}.items():
        if name in captured and captured[name] != digest:
            raise ValueError('Conflicting accepted complete-kernel input: ' + name)
        captured[name] = digest
    for path in (PATCH, CORE, CORE.with_suffix('.h'),
                 ROOT / 'iokit/Kernel/BCM2712PCIeUnusedPolicy.h',
                 ROOT / 'iokit/Kernel/BCM2712PCIeUnused.inc', Path(__file__).resolve(),
                 *(ROOT / 'tools/rpi5/tests' / name for name in
                   ('test_pcie_unused.py', 'pcie_unused_host.c', 'pcie_unused_policy_host.c',
                    'test_pcie_unused_kernel.py'))):
        captured[str(path)] = audit.sha(path)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Unused-window dependency changed: ' + name)
    return captured, prior, original, extras, flags, archive, constituents


def build(output):
    captured, prior, original, extras, flags, archive, constituents = inputs()
    output = output.resolve()
    if not (output.parent == ROOT / 'build/rpi5' or output.is_relative_to(Path('/private/tmp'))
            or output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('Unused-window kernel requires a separate fresh build/temporary directory')
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(args, name, cwd=ROOT, warning_free=False):
        row = audit.execute(args, cwd, output / (name + '.log'))
        commands.append(row)
        if row['returncode'] or (warning_free and row['warning_count']):
            raise ValueError('Unused-window build step failed or warned: ' + row['log'])
        return row

    overlay = output / 'overlay'
    overlay.mkdir()
    for name in SOURCE_NAMES:
        shutil.copyfile(full.BASE / name, overlay / name)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-i', PATCH], 'patch', overlay)
    compiled, objects = [], []
    for source in (overlay / SOURCE_NAMES[0], CORE):
        cpp = source.suffix == '.cpp'
        template_path = audit.TEMPLATE if cpp else full.fdt.ubus.phy.watchdog.TEMPLATE
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        obj, cwd = output / (source.name + '.o'), Path(template['directory'])
        args = (full.fdt.ubus.phy.config.command if cpp else
                full.fdt.ubus.phy.watchdog.command)(template, source, obj)
        args[1:1] = ['-DRPI5_PCIE_UNUSED_DIAGNOSTIC=1', '-I', str(ROOT),
                     '-iquote', str(ROOT / 'iokit/Kernel')]
        if cpp:
            args[1:1] = ['-DRPI5_PCIE_PHY_DIAGNOSTIC=1', '-DRPI5_PCIE_UBUS_DIAGNOSTIC=1',
                         '-DRPI5_FIRMWARE_FDT_HANDOFF=1']
        captured[str(source)] = audit.sha(source)
        captured[str(Path(args[0]))] = audit.sha(Path(args[0]))
        dep = output / (source.name + '.d')
        execute([arg for arg in args[:-2] if arg != '-c'] + ['-M', '-MG', '-MF', str(dep)],
                source.name + '-deps', cwd, True)
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file():
                raise ValueError('Missing actual unused-window dependency: ' + str(path))
            digest = audit.sha(path)
            if str(path) in captured and captured[str(path)] != digest:
                raise ValueError('Conflicting unused-window header: ' + str(path))
            captured[str(path)] = digest
        row = execute(args, source.name + '-compile', cwd, True)
        row['object_sha256'] = audit.sha(obj)
        compiled.append(row); objects.append(obj)
    assembly = output / 'transport.s'
    args = [arg for arg in compiled[0]['command'][:-2] if arg != '-c'] + ['-S', '-o', str(assembly)]
    execute(args, 'assembly', audit.OBJ / 'iokit/DEVELOPMENT', True)
    asm = assembly.read_text()
    for instruction in ('dmb\tosh', 'dsb\tsy', '_pe_rpi5_watchdog_check_pcie',
                        '_rpi5_pcie_ubus_configure', '_rpi5_pcie_unused_init',
                        '_rpi5_pcie_unused_inspect'):
        if instruction not in asm:
            raise ValueError('Actual guarded continuation not emitted: ' + instruction)

    replaced_transport = full.BASE / 'BCM2712PCIePHYTransport.cpp.o'
    if constituents.count(replaced_transport) != 1:
        raise ValueError('Accepted transport replacement is ambiguous')
    candidates = [path for path in original if path not in full.REPLACED]
    candidates += [objects[0] if path == replaced_transport else path for path in constituents]
    candidates.append(objects[1])
    if len(candidates) != len(set(candidates)):
        raise ValueError('Duplicate complete-kernel object')
    filelist = output / 'kernel.pcie-unused.filelist'
    filelist.write_text(''.join(str(path) + '\n' for path in candidates))
    kernel = output / 'kernel.pcie-unused'
    unstripped, linkmap = output / 'kernel.unstripped', output / 'kernel.map'
    args = [('-Wl,-map,' + str(linkmap)) if arg.startswith('-Wl,-map,') else arg for arg in flags]
    args += ['-filelist', str(filelist), *map(str, extras), '-o', str(unstripped), str(archive)]
    row = execute(args, 'kernel-link')
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']:
        raise ValueError('Unused-window complete kernel introduced linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel])
    (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]):
        raise ValueError('Unused-window complete kernel has unresolved symbols')
    textmap = linkmap.read_text(errors='surrogateescape')
    raw = kernel.read_bytes()
    linked = full.linked_audit(raw, listing, textmap)
    for path in (*full.REPLACED, replaced_transport):
        if str(path) in textmap:
            raise ValueError('Superseded implementation survived final link: ' + str(path))
    if any(str(path) not in textmap for path in candidates):
        raise ValueError('Actual complete-kernel constituent missing from map')
    names = full.symbols(listing)
    required = ['_rpi5_pcie_unused_init', '_rpi5_pcie_unused_inspect', '_memcpy']
    required += [name for name in names if 'BCM2712PCIePHYTransport' in name and
                 ('runPHYUBUSAndWindowCheck' in name or 'unusedOwner' in name)]
    if len(required) != 5:
        raise ValueError('Actual IOKit unused-window entry missing or ambiguous')
    for name in required:
        addresses = names.get(name, [])
        if len(addresses) != 1 or not any(s['initprot'] & 4 and s['vmaddr'] <= addresses[0] and
                addresses[0] + 4 <= s['vmaddr'] + s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('New implementation not executable: ' + name)
    linked['unused_window_implementations'] = required
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Unused-window input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='pcie-unused-readonly-kernel-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands, compiles=compiled,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=len(raw), link=linked,
        replaced_objects=list(map(str, (*full.REPLACED, replaced_transport))),
        baseline_linker_warnings=warnings, new_linker_warnings=[],
        complete_kernel_link_proven=True, actual_read_only_continuation_wired=True,
        same_owned_ubus_serdes_sessions=True, single_watchdog_claim=True,
        new_inspection_registers=23, new_inspection_writes=0, new_mapped_pages=0,
        unused_windows_physically_observed=False, check_quiescent_provider_implemented=False,
        rc_windows_link_wired=False, irq_dma_authorized=False,
        power_clock_shared_ownership_proven=False, physical_recovery_proven=False,
        initializer_runtime_executed=False, provider_personality_added=False, boot_caller_added=False,
        installed=False, pi_executed=False, ethernet_proven=False, loader_package_created=False,
        sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(kernel_sha256=report['kernel_sha256'], kernel_bytes=report['kernel_bytes'],
                         complete_kernel_link_proven=True, pi_executed=False)))


if __name__ == '__main__':
    main()
