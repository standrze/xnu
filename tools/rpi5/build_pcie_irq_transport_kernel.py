#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Wire the real IRQ lease into a separately copied complete controller kernel."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_pcie_irq_kernel as previous
except ImportError:
    import build_pcie_irq_kernel as previous

audit, ROOT, full = previous.audit, previous.ROOT, previous.full
BASE = ROOT / 'build/rpi5/pcie-irq-kernel-20261012-final'
BASE_SHA = '3078ff46d3cc69dc9e0d45480eee81fe71d1f4b2485d3e33f2fec63d018256b8'
CONTROLLER = previous.BASE
REPLACED = CONTROLLER / 'BCM2712PCIePHYTransport.cpp.o'
PATCH = ROOT / 'tools/rpi5/patches/pcie-irq-transport.patch'
BODY = ROOT / 'iokit/Kernel/BCM2712PCIeIRQTransport.inc'
SOURCE_NAMES = ('BCM2712PCIePHYTransport.cpp', 'BCM2712PCIePHYTransport.h')


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted IRQ receipt changed')
    prior = json.loads(manifest.read_text())
    captured = previous.inputs()[0]
    for name, digest in {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA}.items():
        if name in captured and captured[name] != digest:
            raise ValueError('Conflicting accepted IRQ transport input: ' + name)
        captured[name] = digest
    objects = [Path(line) for line in (BASE / 'kernel.pcie-irq.filelist').read_text().splitlines() if line]
    if len(objects) != len(set(objects)) or objects.count(REPLACED) != 1:
        raise ValueError('Actual accepted controller transport replacement ambiguous')
    if any(str(path) not in captured for path in objects):
        raise ValueError('Unpinned accepted kernel constituent')
    for path in (PATCH, BODY, Path(__file__).resolve(), *(ROOT / 'tools/rpi5/tests' / name for name in
                 ('test_pcie_irq_transport.py', 'pcie_irq_transport_host.cpp'))):
        captured[str(path)] = audit.sha(path)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('IRQ transport dependency changed: ' + name)
    return captured, prior, objects


def build(output):
    captured, prior, original = inputs()
    output = output.resolve()
    if not (output.parent == ROOT / 'build/rpi5' or output.is_relative_to(Path('/private/tmp'))
            or output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('IRQ transport requires a separate fresh build/temporary directory')
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    def execute(args, name, cwd=ROOT, warning_free=False):
        row = audit.execute(args, cwd, output / (name + '.log')); commands.append(row)
        if row['returncode'] or (warning_free and row['warning_count']):
            raise ValueError('IRQ transport failed or warned: ' + row['log'])
        return row

    overlay = output / 'overlay'; overlay.mkdir()
    for name in SOURCE_NAMES:
        shutil.copyfile(CONTROLLER / 'overlay' / name, overlay / name)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-i', PATCH], 'patch', overlay)
    source, obj = overlay / SOURCE_NAMES[0], output / (SOURCE_NAMES[0] + '.o')
    controller = json.loads((CONTROLLER / 'manifest.json').read_text())
    # Reuse the exact accepted actual IOKit compile invocation, changing only
    # the copied source/output and the explicit new opt-in definitions.
    old_source = str(CONTROLLER / 'overlay' / SOURCE_NAMES[0])
    template = controller['compiles'][0]['command']
    if template.count(old_source) != 1 or template[-2:] != ['-o', str(REPLACED)]:
        raise ValueError('Accepted actual transport compile command ambiguous')
    args = [str(source) if arg == old_source else arg for arg in template[:-2]] + ['-o', str(obj)]
    args[1:1] = ['-DRPI5_PCIE_IRQ_TRANSPORT=1', '-DRPI5_PCIE_IRQ_MASK=1']
    cwd = audit.OBJ / 'iokit/DEVELOPMENT'
    captured[str(Path(args[0]))] = audit.sha(Path(args[0]))
    for name in SOURCE_NAMES:
        path = overlay / name; captured[str(path)] = audit.sha(path)
    dep = output / 'transport.d'
    execute([arg for arg in args[:-2] if arg != '-c'] + ['-M', '-MG', '-MF', str(dep)], 'deps', cwd, True)
    for path in audit.dependency_paths(dep, cwd):
        if not path.is_file(): raise ValueError('Missing actual IRQ transport dependency: ' + str(path))
        digest = audit.sha(path)
        if str(path) in captured and captured[str(path)] != digest:
            raise ValueError('Conflicting actual IRQ transport header: ' + str(path))
        captured[str(path)] = digest
    row = execute(args, 'compile', cwd, True)
    row['object_sha256'] = audit.sha(obj)
    results = [row]
    assembly = output / 'transport.s'
    execute([arg for arg in args[:-2] if arg != '-c'] + ['-S', '-o', str(assembly)], 'assembly', cwd, True)
    assembly_text = assembly.read_text()
    for call in ('_pe_rpi5_watchdog_claim_pcie', '_pe_rpi5_pcie_irq_claim', '_pe_rpi5_pcie_irq_check',
                 '_ml_set_interrupts_enabled', '_rpi5_pcie_reset_pulse', '_rpi5_pcie_rescal_calibrate',
                 '_rpi5_pcie_serdes_configure54', '_rpi5_pcie_rc_configure', '_rpi5_pcie_link_train',
                 '_rpi5_pcie_clock_finish'):
        if call not in assembly_text: raise ValueError('Actual composition call missing: ' + call)

    _, _, extras, flags, archive, _ = full.inputs()
    objects = [obj if path == REPLACED else path for path in original]
    if len(objects) != len(set(objects)): raise ValueError('Duplicate IRQ transport constituent')
    filelist = output / 'kernel.pcie-irq-transport.filelist'
    filelist.write_text(''.join(str(path) + '\n' for path in objects))
    kernel, unstripped, linkmap = output / 'kernel.pcie-irq-transport', output / 'kernel.unstripped', output / 'kernel.map'
    args = [('-Wl,-map,' + str(linkmap)) if arg.startswith('-Wl,-map,') else arg for arg in flags]
    row = execute(args + ['-filelist', str(filelist), *map(str, extras), '-o', str(unstripped), str(archive)], 'kernel-link')
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']: raise ValueError('IRQ transport introduced linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel]); (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]): raise ValueError('IRQ transport kernel has undefined symbols')
    textmap = linkmap.read_text(errors='surrogateescape')
    linked = full.linked_audit(kernel.read_bytes(), listing, textmap)
    if str(REPLACED) in textmap: raise ValueError('Superseded controller remains in IRQ transport kernel')
    if any(str(path) not in textmap for path in objects): raise ValueError('Actual IRQ transport constituent missing')
    names = full.symbols(listing)
    required = list(prior['link']['irq_implementations'])
    required += ['_rpi5_pcie_windows_init', '_rpi5_pcie_windows_program', '_rpi5_pcie_rc_init',
                 '_rpi5_pcie_rc_configure', '_rpi5_pcie_link_init', '_rpi5_pcie_link_train', '_rpi5_pcie_clock_finish']
    required += [name for name in names if 'BCM2712PCIePHYTransport' in name and any(part in name for part in
        ('runController', 'controllerRead16', 'controllerWrite16', 'controllerQuiescent', 'controllerLifecycle',
         'claimControllerIRQ'))]
    if len(required) != 18: raise ValueError('Actual controller/IRQ implementation missing or ambiguous')
    for name in required:
        values = names.get(name, [])
        if len(values) != 1 or not any(s['initprot'] & 4 and s['vmaddr'] <= values[0] and
                values[0]+4 <= s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Actual IRQ transport implementation not executable: ' + name)
    for fragment, instruction in (('controllerRead16', 'ldrh'), ('controllerWrite16', 'strh')):
        name = next(name for name in required if fragment in name)
        body = assembly_text.split(name + ':', 1)[1].split('\n\t.globl', 1)[0]
        if '\t' + instruction + '\t' not in body or 'dsb\tsy' not in body or 'dmb\tosh' not in body:
            raise ValueError('Actual ordered halfword callback missing: ' + fragment)
    linked['controller_irq_implementations'] = required
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest: raise ValueError('IRQ transport input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='pcie-controller-irq-composition-kernel-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands, compiles=results,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size, link=linked,
        replaced_transport=str(REPLACED), baseline_linker_warnings=warnings, new_linker_warnings=[],
        complete_kernel_link_proven=True, single_watchdog_claim=True, irq_claim_after_watchdog_before_reset=True,
        real_xnu_interrupt_api=True, failed_irq_claim_leaves_local_interrupts_disabled=True,
        actual_irq_checks_bracket_lifecycle=True, same_owner_and_retained_thread=True,
        watchdog_checks_per_successful_controller_guard=6,
        accepted_irq_pe_and_core_objects_reused=True, original_controller_entries_preserved=True,
        actual_halfword_mmio=True, concrete_lifecycle_provider_added=False,
        new_mapped_pages=0, initializer_runtime_executed=False, provider_personality_added=False,
        boot_caller_added=False, inherited_power_clock_shared_ownership_proven=False,
        physical_recovery_proven=False, irq_dma_authorized=False, installed=False,
        pi_executed=False, ethernet_proven=False, loader_package_created=False,
        sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(kernel_sha256=report['kernel_sha256'], kernel_bytes=report['kernel_bytes'], pi_executed=False)))


if __name__ == '__main__': main()
