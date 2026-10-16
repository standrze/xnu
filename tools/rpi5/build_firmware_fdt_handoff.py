#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build distinct retained-FDT loader/kernel components; no install or hardware I/O."""
import argparse
import json
from pathlib import Path
import re
import shutil

try:
    from . import build_pcie_device_handoff as device
    from . import build_pcie_ubus_transport as ubus
except ImportError:
    import build_pcie_device_handoff as device
    import build_pcie_ubus_transport as ubus

ROOT, audit = device.ROOT, device.audit
LOADER = ROOT / 'build/rpi5/pcie-device-handoff-20261012-final'
LOADER_SHA = '0066df558ec54cd3932178dd2e1b127cdb6c0dcc5b27ba689e5def09d587bdf7'
KERNEL = ROOT / 'build/rpi5/pcie-ubus-transport-20261012-final'
KERNEL_SHA = 'cec6fb504b3b7b903bee2622c271c5e08bc3557a6bdf22033648b6559db4098b'
PATCH = ROOT / 'tools/rpi5/patches/firmware-fdt-loader.patch'
TRANSPORT_PATCH = ROOT / 'tools/rpi5/patches/firmware-fdt-transport.patch'
ARM = ROOT / 'osfmk/arm/arm_init.c'
ARM_TEMPLATE = audit.OBJ / 'osfmk/DEVELOPMENT/arm_init.o.json'
TREE = ROOT / 'loader/rpi5/firmware_fdt_tree.c'
SANITIZE = ROOT / 'loader/rpi5/fdt_sanitize.c'
COPY = ROOT / 'iokit/Kernel/BCM2712FirmwareFDT.cpp'
MARKER = b'RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0'


def inputs():
    captured, reports = {}, []
    for directory, pin in ((LOADER, LOADER_SHA), (KERNEL, KERNEL_SHA)):
        manifest = directory / 'manifest.json'
        if audit.sha(manifest) != pin:
            raise ValueError('Accepted FDT dependency receipt changed: ' + str(manifest))
        report = json.loads(manifest.read_text())
        for name, digest in {**report['inputs_sha256'], **report['generated_sha256'], str(manifest): pin}.items():
            if name in captured and captured[name] != digest:
                raise ValueError('Conflicting FDT dependency: ' + name)
            captured[name] = digest
        reports.append(report)
    # These are source/template pins, not inferred physical acceptance.
    for path in (PATCH, TRANSPORT_PATCH, ARM, ARM_TEMPLATE, ROOT / 'osfmk/arm64/arm_vm_init.c',
                 TREE, TREE.with_suffix('.h'), SANITIZE,
                 SANITIZE.with_suffix('.h'), COPY, COPY.with_suffix('.h'),
                 ROOT / 'loader/rpi5/firmware_fdt_record.h',
                 ROOT / 'osfmk/arm64/rpi5_firmware_fdt.inc',
                 ROOT / 'iokit/Kernel/BCM2712FirmwareFDTTransport.inc',
                 ROOT / 'osfmk/arm64/rpi5_firmware_fdt_api.h', Path(__file__).resolve()):
        digest = audit.sha(path)
        if str(path) in captured and captured[str(path)] != digest:
            raise ValueError('Accepted FDT source pin conflict: ' + str(path))
        captured[str(path)] = digest
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('FDT dependency changed: ' + name)
    return captured, reports[0], reports[1]


def build(output):
    captured, old_loader, old_kernel = inputs()
    output = output.resolve()
    prohibited = (ROOT / 'loader', ROOT / 'iokit', ROOT / 'osfmk', ROOT / 'pexpert',
        ROOT / 'tools', ROOT / 'docs', audit.APPLE, audit.SDK, audit.OBJ,
        LOADER, KERNEL, device.BASE, ubus.BASE, ubus.phy.config.BASE,
        *(directory for directory, _, _ in ubus.phy.BASELINES))
    if any(output.is_relative_to(path.resolve()) for path in prohibited):
        raise ValueError('FDT output must not be inside sources or accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(args, name, cwd=ROOT, legacy_arm_warning=False):
        row = audit.execute(args, cwd, output / (name + '.log'))
        commands.append(row)
        legacy = (legacy_arm_warning and row['warning_count'] == 1 and
                  "dyld_kernel_fixups.h:367:12: warning: variable 'cnt' set but not used [-Wunused-but-set-variable]"
                  in Path(row['log']).read_text())
        if row['returncode'] or (row['warning_count'] and not legacy):
            raise ValueError('FDT build step failed or warned: ' + row['log'])
        return row

    main, seed, arm = (output / name for name in ('probe_main.c', 'firmware_seed_tree.c', 'arm_init.c'))
    for source, dest in ((LOADER / 'probe_main.c', main),
                         (ROOT / 'loader/rpi5/firmware_seed_tree.c', seed), (ARM, arm)):
        shutil.copyfile(source, dest)
    transport = output / 'BCM2712PCIePHYTransport.cpp'
    for name in ('BCM2712PCIePHYTransport.cpp', 'BCM2712PCIePHYTransport.h'):
        shutil.copyfile(KERNEL / 'overlay' / name, output / name)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', output, '-i', PATCH], 'patch')
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', output, '-i', TRANSPORT_PATCH], 'transport-patch')
    for path in (main, seed, arm, transport): captured[str(path)] = audit.sha(path)
    base = json.loads((device.BASE / 'manifest.json').read_text())
    main_record = next(row['command'] for row in old_loader['commands'] if row['log'].endswith('/main.log'))
    seed_record = next(command for command in base['commands'] if '-c' in command and
                       command[command.index('-c') + 1].endswith('/firmware_seed_tree.c'))

    def loader_compile(record, source, dest, enabled):
        args = list(record)
        args[args.index('-c') + 1] = str(source)
        args[args.index('-o') + 1] = str(dest)
        args[2:2] = ['-I' + str(ROOT / 'loader/rpi5'), '-DRPI5_FIRMWARE_FDT_HANDOFF=' + str(int(enabled))]
        return args

    link = next(row['command'] for row in old_loader['commands'] if row['log'].endswith('/handoff-link.log'))

    def replay(main_obj, seed_obj, stem, extra=()):
        elf, binary = output / (stem + '.elf'), output / (stem + '.bin')
        replacements = {str(LOADER / 'probe_main.o'): str(main_obj),
                        str(device.BASE / 'firmware_seed_tree.o'): str(seed_obj)}
        args = [replacements.get(arg, arg) for arg in link]
        if not all(name in link for name in replacements):
            raise ValueError('Accepted loader object layout changed')
        args[args.index('-o') + 1] = str(elf)
        args[args.index('-o'):args.index('-o')] = list(map(str, extra))
        execute(args, stem + '-link')
        execute([ROOT / 'tools/rpi5/tfa-objcopy', '-O', 'binary', elf, binary], stem + '-objcopy')
        device.accepted.old.inspect_elf(elf.read_bytes(), binary.read_bytes(), 0x9000000)
        return elf, binary

    # New patch disabled: recompile BOTH changed units and require exact bytes.
    off_main, off_seed = output / 'off-main.o', output / 'off-seed.o'
    execute(loader_compile(main_record, main, off_main, False), 'off-main')
    execute(loader_compile(seed_record, seed, off_seed, False), 'off-seed')
    _, off_binary = replay(off_main, off_seed, 'off-replay')
    if audit.sha(off_binary) != old_loader['image_sha256']:
        raise ValueError('Disabled FDT patches change the exact Device-handoff image')
    main_obj, seed_obj, tree_obj = (output / name for name in ('probe_main.o', 'firmware_seed_tree.o', 'firmware_fdt_tree.o'))
    execute(loader_compile(main_record, main, main_obj, True), 'loader-main')
    execute(loader_compile(seed_record, seed, seed_obj, True), 'loader-seed')
    execute(loader_compile(main_record, TREE, tree_obj, True), 'loader-tree')
    elf, binary = replay(main_obj, seed_obj, 'firmware-fdt', (tree_obj,))
    raw, payload = binary.read_bytes(), (device.BASE / 'payload.bin').read_bytes()
    offset = raw.find(payload)
    if raw.count(MARKER) != 1 or offset < 0 or offset & 63 or raw.find(payload, offset + 1) >= 0:
        raise ValueError('Distinct FDT loader marker or exact aligned payload missing')
    replaced = {'loader/rpi5/probe_main.c', 'loader/rpi5/firmware_seed_tree.c'}
    frames = [row for row in old_loader['stack_frames'] if row['location'].split(':')[0] not in replaced]
    for obj, unit in ((main_obj, 'probe_main'), (seed_obj, 'firmware_seed_tree'), (tree_obj, 'firmware_fdt_tree')):
        frames += device.stack_frames(obj.with_suffix('.su'), 'loader/rpi5/' + unit + '.c')
    budgets = dict(device_handoff=device.device_stack(frames))
    added = [row for row in frames if row['location'].startswith('loader/rpi5/firmware_fdt_tree.c:')]
    if not added: raise ValueError('Missing actual FDT attachment stack evidence')
    conservative = budgets['device_handoff']['conservative_bytes'] + sum(row['bytes'] for row in added)
    if conservative + 512 >= 0x4000: raise ValueError('FDT attachment exhausts loader stack headroom')
    budgets['firmware_fdt'] = dict(conservative_bytes=conservative, minimum_remaining_bytes=0x4000-conservative)
    # Use the actual encoder's fixed bound, never an invented enlarged stack.
    depth = int(re.search(r'^#define RPI5_ADT_MAX_DEPTH ([0-9]+)$',
                         (ROOT / 'loader/rpi5/apple_dt.h').read_text(), re.M)[1])
    budgets['tree'] = device.tree_stack.check(frames, depth)
    budgets['runtime_plan'] = device.tree_stack.check_runtime_plan(frames, depth)

    objects, kernel_results = [], []
    for source, template_path, cpp in ((arm, ARM_TEMPLATE, False), (COPY, audit.TEMPLATE, True),
                                        (transport, audit.TEMPLATE, True),
                                        (SANITIZE, ubus.phy.watchdog.TEMPLATE, False)):
        template = json.loads(template_path.read_text().strip().removesuffix(','))
        obj, cwd = output / (source.name + '.o'), Path(template['directory'])
        if cpp:
            args = ubus.phy.config.command(template, source, obj)
        elif source == arm:
            args = audit.compile_command(template, source, ROOT, obj)
            args = ['-Werror' if arg == '-Wno-error' else arg for arg in args]
        else:
            args = ubus.phy.watchdog.command(template, source, obj)
        args[1:1] = ['-DRPI5_FIRMWARE_FDT_HANDOFF=1', '-I', str(ROOT), '-iquote', str(ARM.parent),
                     '-iquote', str(ROOT / 'iokit/Kernel')]
        if source == transport:
            args[1:1] = ['-DRPI5_PCIE_PHY_DIAGNOSTIC=1', '-DRPI5_PCIE_UBUS_DIAGNOSTIC=1']
        compiler = Path(args[0]); captured[str(compiler)] = audit.sha(compiler)
        if source == arm:
            baseline_args = list(args)
            baseline_args[baseline_args.index(str(arm))] = str(ARM)
            baseline_args[baseline_args.index('-o') + 1] = str(output / 'baseline-arm.o')
            baseline_args[baseline_args.index('-DRPI5_FIRMWARE_FDT_HANDOFF=1')] = '-DRPI5_FIRMWARE_FDT_HANDOFF=0'
            baseline_arm = execute(baseline_args, 'baseline-arm-compile', cwd, legacy_arm_warning=True)
            if baseline_arm['warning_count'] != 1:
                raise ValueError('Original arm_init warning baseline changed')
        dep = output / (source.name + '.d')
        execute([arg for arg in args[:-2] if arg != '-c'] + ['-M', '-MG', '-MF', str(dep)],
                source.name + '-deps', cwd)
        for path in audit.dependency_paths(dep, cwd):
            if not path.is_file(): raise ValueError('Missing real kernel FDT dependency: ' + str(path))
            captured.setdefault(str(path), audit.sha(path))
        row = execute(args, source.name + '-compile', cwd, legacy_arm_warning=source == arm)
        row['object_sha256'] = audit.sha(obj)
        kernel_results.append(row); objects.append(obj)
    composed = output / 'apple-bcm2712-firmware-fdt.o'
    kernel_link = execute(['xcrun', 'ld', '-r', '-arch', 'arm64', '-o', composed,
        *(directory / name for directory, _, name in ubus.phy.BASELINES),
        *(ubus.BASE / (source.name + '.o') for source in ubus.phy.CORES),
        KERNEL / 'pcie_ubus.c.o', *objects], 'kernel-link')
    kernel_link['object_sha256'] = audit.sha(composed)
    defined = set(audit.read_command(['xcrun', 'nm', '-jU', composed]).splitlines())
    undefined = set(audit.read_command(['xcrun', 'nm', '-ju', composed]).splitlines())
    reference = set(audit.read_command(['xcrun', 'nm', '-jU', audit.KERNEL]).splitlines())
    kernel_link['undefined_symbols'] = sorted(undefined)
    kernel_link['not_defined_in_reference_kernel'] = sorted(undefined - reference)
    boundaries = {'section$end$__TEXT$__thread_starts', 'section$start$__TEXT$__thread_starts'}
    original_undefined = set(audit.read_command(['xcrun', 'nm', '-ju', output / 'baseline-arm.o']).splitlines())
    if not boundaries.issubset(original_undefined):
        raise ValueError('Original arm_init linker-section baseline changed')
    kernel_link['original_arm_linker_section_boundaries'] = sorted(boundaries)
    if kernel_link['not_defined_in_reference_kernel'] != sorted({'___dso_handle'} | boundaries):
        raise ValueError('New unresolved firmware-FDT kernel dependency')
    for name in ('_rpi5_firmware_fdt_view', '_rpi5_fdt_sanitize_boot_seeds',
                 '__Z27rpi5_copy_boot_firmware_fdtv'):
        if name not in defined: raise ValueError('Actual firmware-FDT implementation missing: ' + name)
    if not any('BCM2712PCIePHYTransport' in name and 'prepareBoot' in name for name in defined):
        raise ValueError('Actual retained-FDT transport preparation missing')
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest: raise ValueError('FDT input changed during build: ' + name)
    generated = {str(path): audit.sha(path) for path in output.rglob('*') if path.is_file()}
    report = dict(schema_version=1, profile='retained-firmware-fdt-v1',
        inputs_sha256=captured, generated_sha256=generated, commands=commands,
        image=str(binary), image_sha256=audit.sha(binary), image_bytes=len(raw), payload_offset=offset,
        elf_audit=device.accepted.old.inspect_elf(elf.read_bytes(), raw, 0x9000000),
        disabled_patch_boot_binary_identical=True, accepted_kernel_and_root_reused_in_loader=True,
        embedded_kernel_sha256=old_loader['embedded_kernel_sha256'], embedded_root_sha256=old_loader['embedded_root_sha256'],
        stack_frames=frames, stack_budgets=budgets, kernel_results=kernel_results, kernel_link=kernel_link,
        loader_exports_descriptor_only=True, actual_normal_physmap_view_implemented=True,
        actual_private_osdata_copy_implemented=True, known_boot_seed_values_erased_in_copy=True,
        original_firmware_source_changed=False, final_kernel_link_proven=False,
        provider_registration_implemented=False, copy_consumed_by_pcie_owner=True,
        installed=False, pi_executed=False, power_clock_ownership_proven=False,
        hardware_recovery_proven=False, pcie_mmio_enabled=False, ethernet_proven=False,
        sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, sort_keys=True, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    report = build(parser.parse_args().output_dir)
    print(json.dumps(dict(image_sha256=report['image_sha256'],
                         kernel_object_sha256=report['kernel_link']['object_sha256'], pi_executed=False)))


if __name__ == '__main__':
    main()
