#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Wire actual RC/windows/link/post-link clock in a separate complete kernel."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_pcie_clock_kernel as previous
except ImportError:
    import build_pcie_clock_kernel as previous

audit, ROOT, full = previous.audit, previous.ROOT, previous.full
SOURCE_NAMES = previous.SOURCE_NAMES
BASE = ROOT / 'build/rpi5/pcie-clock-kernel-20261012-final'
BASE_SHA = '03edd498d0cd7cc008fbb6a6f2b3a5ec6ad54d6411b9bec6b6b08814a66a9807'
PATCH = ROOT / 'tools/rpi5/patches/pcie-controller-transport.patch'
CORES = tuple(ROOT / ('loader/rpi5/' + name + '.c') for name in ('pcie_rc', 'pcie_link'))


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted clock-policy receipt changed')
    prior = json.loads(manifest.read_text())
    captured = previous.inputs()[0]
    for name, digest in {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA}.items():
        if name in captured and captured[name] != digest:
            raise ValueError('Conflicting accepted controller input: ' + name)
        captured[name] = digest
    objects = [Path(line) for line in (BASE / 'kernel.pcie-clock.filelist').read_text().splitlines() if line]
    if len(objects) != len(set(objects)) or objects.count(BASE / 'BCM2712PCIePHYTransport.cpp.o') != 1:
        raise ValueError('Accepted actual transport replacement ambiguous')
    if any(str(path) not in captured for path in objects):
        raise ValueError('Unpinned previous complete-kernel object')
    for path in (PATCH, *CORES, *(source.with_suffix('.h') for source in CORES),
                 *(ROOT / 'iokit/Kernel' / name for name in ('BCM2712PCIeControllerPolicy.h',
                     'BCM2712PCIeController.inc', 'BCM2712PCIeControllerLifecycle.inc', 'BCM2712PCIeControllerRun.inc')),
                 Path(__file__).resolve(), *(ROOT / 'tools/rpi5/tests' / name for name in
                 ('test_pcie_controller.py', 'pcie_controller_host.cpp', 'pcie_controller_policy_host.c', 'test_pcie_controller_kernel.py'))):
        captured[str(path)] = audit.sha(path)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Controller dependency changed: ' + name)
    return captured, prior, objects


def build(output):
    captured, prior, original = inputs()
    output = output.resolve()
    if not (output.parent == ROOT / 'build/rpi5' or output.is_relative_to(Path('/private/tmp'))
            or output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('Controller kernel requires a separate fresh build/temporary directory')
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    def execute(args, name, cwd=ROOT, warning_free=False):
        row = audit.execute(args, cwd, output / (name + '.log')); commands.append(row)
        if row['returncode'] or (warning_free and row['warning_count']):
            raise ValueError('Controller build failed or warned: ' + row['log'])
        return row

    overlay = output / 'overlay'; overlay.mkdir()
    for name in SOURCE_NAMES:
        shutil.copyfile(BASE / 'overlay' / name, overlay / name)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-i', PATCH], 'patch', overlay)
    results, new = [], []
    for source in (overlay / SOURCE_NAMES[0], *CORES):
        cpp = source.suffix == '.cpp'
        template_path = audit.TEMPLATE if cpp else full.fdt.ubus.phy.watchdog.TEMPLATE
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        obj, cwd = output / (source.name + '.o'), Path(template['directory'])
        args = (full.fdt.ubus.phy.config.command if cpp else
                full.fdt.ubus.phy.watchdog.command)(template, source, obj)
        args[1:1] = ['-DRPI5_PCIE_CONTROLLER_DIAGNOSTIC=1', '-DRPI5_PCIE_CLOCK_DIAGNOSTIC=1', '-DRPI5_PCIE_PROFILE_QOS_DIAGNOSTIC=1', '-I', str(ROOT),
                     '-iquote', str(ROOT / 'iokit/Kernel')]
        if cpp:
            args[1:1] = ['-DRPI5_PCIE_PHY_DIAGNOSTIC=1', '-DRPI5_PCIE_UBUS_DIAGNOSTIC=1',
                         '-DRPI5_FIRMWARE_FDT_HANDOFF=1', '-DRPI5_PCIE_UNUSED_DIAGNOSTIC=1']
        captured[str(source)] = audit.sha(source)
        captured[str(Path(args[0]))] = audit.sha(Path(args[0]))
        dep = output / (source.name + '.d')
        execute([arg for arg in args[:-2] if arg != '-c'] + ['-M', '-MG', '-MF', str(dep)],
                source.name + '-deps', cwd, True)
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file(): raise ValueError('Missing actual controller dependency: ' + str(path))
            digest = audit.sha(path)
            if str(path) in captured and captured[str(path)] != digest:
                raise ValueError('Conflicting actual controller header: ' + str(path))
            captured[str(path)] = digest
        row = execute(args, source.name + '-compile', cwd, True)
        row['object_sha256'] = audit.sha(obj); results.append(row); new.append(obj)
    assembly = output / 'transport.s'
    args = [arg for arg in results[0]['command'][:-2] if arg != '-c'] + ['-S', '-o', str(assembly)]
    execute(args, 'assembly', audit.OBJ / 'iokit/DEVELOPMENT', True)
    for instruction in ('dmb\tosh', 'dsb\tsy', '_pe_rpi5_watchdog_check_pcie', '_rpi5_pcie_profile_decode',
                        '_rpi5_pcie_unused_inspect', '_rpi5_pcie_ubus_configure',
                        '_rpi5_pcie_qos_init', '_rpi5_pcie_qos_configure',
                        '_rpi5_pcie_clock_init', '_rpi5_pcie_clock_prepare', '_rpi5_pcie_windows_init',
                        '_rpi5_pcie_rc_init', '_rpi5_pcie_rc_configure', '_rpi5_pcie_link_init',
                        '_rpi5_pcie_link_train', '_rpi5_pcie_clock_finish'):
        if instruction not in assembly.read_text():
            raise ValueError('Actual controller composition call missing: ' + instruction)
    _, _, extras, flags, archive, _ = full.inputs()
    replaced = BASE / 'BCM2712PCIePHYTransport.cpp.o'
    objects = [new[0] if path == replaced else path for path in original] + new[1:]
    if len(objects) != len(set(objects)): raise ValueError('Duplicate new complete-kernel object')
    filelist = output / 'kernel.pcie-controller.filelist'
    filelist.write_text(''.join(str(path) + '\n' for path in objects))
    kernel, unstripped, linkmap = output / 'kernel.pcie-controller', output / 'kernel.unstripped', output / 'kernel.map'
    args = [('-Wl,-map,' + str(linkmap)) if arg.startswith('-Wl,-map,') else arg for arg in flags]
    row = execute(args + ['-filelist', str(filelist), *map(str, extras), '-o', str(unstripped), str(archive)], 'kernel-link')
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']: raise ValueError('Controller kernel introduced linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel]); (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]): raise ValueError('Controller kernel has undefined symbols')
    textmap = linkmap.read_text(errors='surrogateescape')
    linked = full.linked_audit(kernel.read_bytes(), listing, textmap)
    for path in (*full.REPLACED, full.BASE / 'BCM2712PCIePHYTransport.cpp.o', replaced):
        if str(path) in textmap: raise ValueError('Superseded implementation in controller kernel: ' + str(path))
    if any(str(path) not in textmap for path in objects): raise ValueError('Actual constituent missing from map')
    names = full.symbols(listing)
    required = ['_rpi5_pcie_windows_init', '_rpi5_pcie_windows_program', '_rpi5_pcie_rc_init',
                '_rpi5_pcie_rc_configure', '_rpi5_pcie_link_init', '_rpi5_pcie_link_train', '_rpi5_pcie_clock_finish']
    required += [name for name in names if 'BCM2712PCIePHYTransport' in name and any(part in name for part in
        ('runController', 'controllerRead16', 'controllerWrite16', 'controllerQuiescent', 'controllerLifecycle'))]
    if len(required) != 12: raise ValueError('Actual controller entry ambiguous/missing')
    for name in required:
        addresses = names.get(name, [])
        if len(addresses) != 1 or not any(s['initprot'] & 4 and s['vmaddr'] <= addresses[0] and
                addresses[0]+4 <= s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Controller implementation not executable: ' + name)
    assembly_text = assembly.read_text()
    for fragment, instruction in (('controllerRead16', 'ldrh'), ('controllerWrite16', 'strh')):
        matches = [name for name in required if fragment in name]
        if len(matches) != 1: raise ValueError('Actual halfword callback ambiguous')
        label = matches[0] + ':'
        if label not in assembly_text: raise ValueError('Actual halfword callback body missing')
        body = assembly_text.split(label, 1)[1].split('\n\t.globl', 1)[0]
        if '\t' + instruction + '\t' not in body:
            raise ValueError('Actual halfword MMIO instruction missing: ' + instruction)
    linked['controller_implementations'] = required
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest: raise ValueError('Controller input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='pcie-controller-composition-kernel-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands, compiles=results,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size, link=linked,
        replaced_transport=str(replaced), baseline_linker_warnings=warnings, new_linker_warnings=[],
        complete_kernel_link_proven=True, original_fdt_options_checked_before_mapping=True,
        actual_fifo_vdm_qos_wired=True, actual_aspm_prelink_wired=True,
        postlink_clock_core_compiled=True, postlink_clkreq_wired=True,
        independent_provider_callback_required=True, fresh_unused_rechecks_wired=True,
        actual_halfword_mmio=True, guarded_link_delay_chunks=True,
        concrete_lifecycle_provider_added=False,
        same_owned_sessions=True, single_watchdog_claim=True,
        new_mapped_pages=0, initializer_runtime_executed=False, provider_personality_added=False,
        boot_caller_added=False, inherited_power_clock_shared_ownership_proven=False,
        physical_recovery_proven=False, rc_windows_link_wired=True, clkreq_aspm_programmed=False,
        irq_dma_authorized=False, installed=False, pi_executed=False, ethernet_proven=False,
        loader_package_created=False, sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(kernel_sha256=report['kernel_sha256'], kernel_bytes=report['kernel_bytes'], pi_executed=False)))


if __name__ == '__main__': main()
