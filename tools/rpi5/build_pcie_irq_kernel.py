#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build actual selective GIC masking in a distinct complete PCIe kernel."""
import argparse
import json
from pathlib import Path
import shutil

try:
    from . import build_pcie_controller_kernel as previous
except ImportError:
    import build_pcie_controller_kernel as previous

audit, ROOT, full = previous.audit, previous.ROOT, previous.full
watchdog = full.fdt.ubus.phy.watchdog
BASE = ROOT / 'build/rpi5/pcie-controller-kernel-20261012-final'
BASE_SHA = 'd35e4a56930c857a4e2c77143e5e672f12a9da46b916cf0aa8ea0511acfd4846'
OWNER = full.WATCHDOG
OLD_OBJECT = OWNER / 'bcm2712-pcie-watchdog-owner.o'
LEASE_OBJECT = OWNER / 'pcie_watchdog_lease.c.o'
PATCH = ROOT / 'tools/rpi5/patches/pcie-irq-owner.patch'
CORE = ROOT / 'loader/rpi5/pcie_irq_mask.c'


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_SHA:
        raise ValueError('Accepted controller receipt changed')
    prior = json.loads(manifest.read_text())
    captured = previous.inputs()[0]
    for name, digest in {**prior['inputs_sha256'], **prior['generated_sha256'], str(manifest): BASE_SHA}.items():
        if name in captured and captured[name] != digest:
            raise ValueError('Conflicting accepted IRQ input: ' + name)
        captured[name] = digest
    # The accepted partial-link receipt pins the constituent lease object in
    # its compile row, rather than its inputs map. Reuse that exact object,
    # never recompile/rewrite the shared watchdog core or duplicate its symbols.
    owner_manifest = OWNER / 'manifest.json'
    if str(owner_manifest) not in captured or audit.sha(owner_manifest) != captured[str(owner_manifest)]:
        raise ValueError('Accepted watchdog composition receipt changed')
    rows = [row for row in json.loads(owner_manifest.read_text())['results']
            if row['command'][-2:] == ['-o', str(LEASE_OBJECT)]]
    if len(rows) != 1 or audit.sha(LEASE_OBJECT) != rows[0]['object_sha256']:
        raise ValueError('Accepted watchdog lease constituent changed')
    captured[str(LEASE_OBJECT)] = rows[0]['object_sha256']
    objects = [Path(line) for line in (BASE / 'kernel.pcie-controller.filelist').read_text().splitlines() if line]
    if len(objects) != len(set(objects)) or objects.count(OLD_OBJECT) != 1 or LEASE_OBJECT in objects:
        raise ValueError('Actual watchdog/pexpert replacement ambiguous')
    if any(str(path) not in captured for path in (*objects, LEASE_OBJECT, OWNER / 'pe_fiq.c')):
        raise ValueError('Unpinned accepted kernel constituent/source')
    for path in (PATCH, CORE, CORE.with_suffix('.h'), ROOT / 'pexpert/arm/rpi5_pcie_irq_api.h',
                 ROOT / 'pexpert/arm/rpi5_pcie_irq_owner.inc', Path(__file__).resolve(),
                 *(ROOT / 'tools/rpi5/tests' / name for name in ('test_pcie_irq_mask.py',
                    'pcie_irq_mask_host.c', 'pcie_irq_owner_host.c', 'pcie_irq_stubs/kern/thread.h'))):
        captured[str(path)] = audit.sha(path)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('IRQ dependency changed: ' + name)
    return captured, prior, objects


def build(output):
    captured, prior, original = inputs()
    output = output.resolve()
    if not (output.parent == ROOT / 'build/rpi5' or output.is_relative_to(Path('/private/tmp'))
            or output.is_relative_to(Path('/private/var/folders'))):
        raise ValueError('IRQ kernel requires a separate fresh build/temporary directory')
    output.mkdir(parents=True, exist_ok=False)
    commands = []
    def execute(args, name, cwd=ROOT, warning_free=False):
        row = audit.execute(args, cwd, output / (name + '.log')); commands.append(row)
        if row['returncode'] or (warning_free and row['warning_count']):
            raise ValueError('IRQ build failed or warned: ' + row['log'])
        return row
    source = output / 'pe_fiq.c'
    shutil.copyfile(OWNER / 'pe_fiq.c', source)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-i', PATCH], 'patch', output)
    template = json.loads(watchdog.TEMPLATE.read_text().strip().removesuffix(','))
    cwd = Path(template['directory'])
    new, results = [], []
    for unit in (source, CORE):
        obj = output / (unit.name + '.o')
        args = watchdog.command(template, unit, obj)
        args[1:1] = ['-DRPI5_PCIE_IRQ_MASK=1']
        captured[str(unit)] = audit.sha(unit)
        captured[str(Path(args[0]))] = audit.sha(Path(args[0]))
        dep = output / (unit.name + '.d')
        execute([arg for arg in args[:-2] if arg != '-c'] + ['-M', '-MG', '-MF', str(dep)],
                unit.name + '-deps', cwd, True)
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file(): raise ValueError('Missing actual IRQ dependency: ' + str(path))
            digest = audit.sha(path)
            if str(path) in captured and captured[str(path)] != digest:
                raise ValueError('Conflicting actual IRQ header: ' + str(path))
            captured[str(path)] = digest
        row = execute(args, unit.name + '-compile', cwd, True)
        row['object_sha256'] = audit.sha(obj); results.append(row); new.append(obj)
    assembly = output / 'pexpert.s'
    execute([arg for arg in results[0]['command'][:-2] if arg != '-c'] + ['-S', '-o', str(assembly)],
            'assembly', cwd, True)
    assembly_text = assembly.read_text()
    for name in ('_pe_rpi5_pcie_irq_claim', '_pe_rpi5_pcie_irq_check'):
        if name + ':' not in assembly_text: raise ValueError('Actual IRQ entry missing: ' + name)
    for name in ('_rpi5_pcie_irq_read', '_rpi5_pcie_irq_write'):
        body = assembly_text.split(name + ':', 1)[1].split('\n\t.globl', 1)[0].split('\n\t.p2align', 1)[0]
        if 'dsb\tsy' not in body or ('\tldr\tw' if name.endswith('read') else '\tstr\tw') not in body:
            raise ValueError('Actual ordered volatile IRQ callback missing: ' + name)
    _, _, extras, flags, archive, _ = full.inputs()
    objects = []
    for path in original:
        objects.extend((new[0], LEASE_OBJECT, new[1]) if path == OLD_OBJECT else (path,))
    if len(objects) != len(set(objects)): raise ValueError('Duplicate complete-kernel IRQ constituent')
    filelist = output / 'kernel.pcie-irq.filelist'
    filelist.write_text(''.join(str(path) + '\n' for path in objects))
    kernel, unstripped, linkmap = output / 'kernel.pcie-irq', output / 'kernel.unstripped', output / 'kernel.map'
    args = [('-Wl,-map,' + str(linkmap)) if arg.startswith('-Wl,-map,') else arg for arg in flags]
    row = execute(args + ['-filelist', str(filelist), *map(str, extras), '-o', str(unstripped), str(archive)], 'kernel-link')
    warnings = [line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings != prior['baseline_linker_warnings']: raise ValueError('IRQ kernel introduced linker warnings')
    execute(['xcrun', 'strip', '-S', unstripped, '-o', kernel], 'kernel-strip')
    listing = audit.read_command(['xcrun', 'nm', '-nm', kernel]); (output / 'kernel.symbols').write_text(listing + '\n')
    if audit.read_command(['xcrun', 'nm', '-ju', kernel]): raise ValueError('IRQ kernel has undefined symbols')
    textmap = linkmap.read_text(errors='surrogateescape')
    linked = full.linked_audit(kernel.read_bytes(), listing, textmap)
    if str(OLD_OBJECT) in textmap or str(watchdog.SOURCE) in textmap:
        raise ValueError('Superseded pexpert owner remains in kernel')
    if any(str(path) not in textmap for path in objects): raise ValueError('Actual IRQ constituent missing from map')
    names = full.symbols(listing)
    required = ('_pe_rpi5_pcie_irq_claim', '_pe_rpi5_pcie_irq_check', '_rpi5_pcie_irq_init',
                '_rpi5_pcie_irq_begin', '_rpi5_pcie_irq_check')
    for name in required:
        values = names.get(name, [])
        if len(values) != 1 or not any(s['initprot'] & 4 and s['vmaddr'] <= values[0] and
                values[0]+4 <= s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Actual IRQ implementation not executable: ' + name)
    linked['irq_implementations'] = list(required)
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest: raise ValueError('IRQ input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='pcie-selective-nonsecure-gic-mask-kernel-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands, compiles=results,
        kernel=str(kernel), kernel_sha256=audit.sha(kernel), kernel_bytes=kernel.stat().st_size, link=linked,
        replaced_watchdog_owner=str(OLD_OBJECT), baseline_linker_warnings=warnings, new_linker_warnings=[],
        complete_kernel_link_proven=True, actual_existing_gic_mapping_reused=True,
        actual_existing_watchdog_lease_reused=True, claim_requires_masked_local_irq_fiq=True,
        claim_bound_to_thread=True, claimed_thread_retained_until_reset=True, claim_nonblocking=True, exact_w1c_masks=True,
        nvme_bits_written=False, maximum_gic_mask_writes=3, pending_clear_writes=0,
        active_clear_writes=0, security_group_writes=0, interrupt_enable_writes=0,
        release_restore_cleanup_implemented=False, irq_core_claim_callback_bound=106,
        irq_core_check_callback_bound=61, watchdog_checks_per_successful_irq_api=2,
        nonsecure_view_only=True, secure_firmware_ownership_proven=False,
        concrete_lifecycle_provider_added=False, provider_personality_added=False, boot_caller_added=False,
        new_mapped_pages=0, initializer_runtime_executed=False, inherited_power_clock_shared_ownership_proven=False,
        physical_recovery_proven=False, irq_dma_authorized=False, installed=False, pi_executed=False,
        ethernet_proven=False, loader_package_created=False, sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output-dir', type=Path, required=True)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(kernel_sha256=report['kernel_sha256'], kernel_bytes=report['kernel_bytes'], pi_executed=False)))


if __name__ == '__main__': main()
