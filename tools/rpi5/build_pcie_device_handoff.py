#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a distinct Device-declaration loader; never install, reboot or claim PHY access."""
import argparse
import json
from pathlib import Path
import re
import shutil

try:
    from . import audit_apple_pci_build as audit
    from . import check_socket_identity_package as accepted
    from . import tree_stack
except ImportError:
    import audit_apple_pci_build as audit
    import check_socket_identity_package as accepted
    import tree_stack

ROOT = audit.ROOT
BASE = ROOT / 'build/rpi5/bl33-probe-vszhh6o4'
BASE_MANIFEST_SHA = '40dd908884cc1b031cbd081149ffc4c7238e991f841070b222ba8803c37b47be'
BASE_IMAGE_SHA = 'f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536'
SOURCE = ROOT / 'loader/rpi5/probe_main.c'
CORE = ROOT / 'loader/rpi5/pcie_device_handoff.c'
PATCH = ROOT / 'tools/rpi5/patches/pcie-device-handoff.patch'
MARKER = b'RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0'


def inputs():
    manifest = BASE / 'manifest.json'
    if audit.sha(manifest) != BASE_MANIFEST_SHA or audit.sha(BASE / 'probe.bin') != BASE_IMAGE_SHA:
        raise ValueError('Accepted zsh/socket loader changed')
    preflight = accepted.inspect(BASE)
    if not preflight['preflight_pass'] or preflight['image_sha256'] != BASE_IMAGE_SHA:
        raise ValueError('Accepted zsh/socket preflight failed')
    report = json.loads(manifest.read_text())
    captured = {str(ROOT / name): digest for name, digest in report['sha256'].items()}
    captured[str(manifest)] = BASE_MANIFEST_SHA
    # The original receipt does not pin each .o. Replaying its original link
    # below must reconstruct the already pinned binary before any reuse.
    for command in report['commands']:
        if command[-2] == '-o' and command[-1].endswith('.o'):
            obj = Path(command[-1])
            if obj.parent != BASE:
                raise ValueError('Unexpected accepted object location')
            captured[str(obj)] = audit.sha(obj)
    for path in (SOURCE, CORE, CORE.with_suffix('.h'), PATCH, Path(__file__).resolve(),
                 ROOT / 'tools/rpi5/audit_apple_pci_build.py',
                 ROOT / 'tools/rpi5/check_socket_identity_package.py',
                 ROOT / 'iokit/Kernel/BCM2712PCIePHYPolicy.h',
                 ROOT / 'osfmk/arm64/rpi5_memory_map.h'):
        pin = audit.sha(path)
        if str(path) in captured and captured[str(path)] != pin:
            raise ValueError('Accepted input pin conflict: ' + str(path))
        captured[str(path)] = pin
    for name, pin in captured.items():
        if audit.sha(Path(name)) != pin:
            raise ValueError('Handoff input changed: ' + name)
    return captured, report


def compile_command(record, source, output, enabled):
    args = list(record)
    args[args.index('-c') + 1] = str(source)
    args[args.index('-o') + 1] = str(output)
    args[2:2] = ['-I' + str(ROOT / 'loader/rpi5'),
                 '-DRPI5_PCIE_DEVICE_HANDOFF=' + str(int(enabled))]
    return args


def stack_frames(path, unit):
    result = []
    for line in path.read_text().splitlines():
        location, size, kind = line.split('\t')
        if kind != 'static' or not 0 <= int(size) < 0x4000:
            raise ValueError('Unsupported handoff stack frame: ' + line)
        # Normalize the copied source path to its original logical unit only
        # for existing call-chain auditors. Actual commands/hashes stay intact.
        result.append(dict(location=unit + ':' + location.split(':', 1)[1], bytes=int(size), kind=kind))
    return result


def device_stack(frames):
    units = {'loader/rpi5/' + unit + '.c' for unit in
             ('pcie_device_handoff', 'pcie_fdt', 'memory_type', 'uart')}
    # Same reviewed FDT/property/translation closure as the existing topology
    # auditor. SD, reservation-plan, CPU and RNG decoders are not callees of
    # this helper; including their large sequential frames is not a call chain.
    fdt = {'be32', 'be64', 'overlap', 'equal', 'value_equal', 'rpi5_fdt_structure',
           'rpi5_fdt_layout', 'rpi5_fdt_property', 'rpi5_fdt_phandles'}
    reg = {'cells', 'compatible', 'width', 'fits', 'enabled', 'parent', 'rpi5_fdt_reg'}
    outer = {'probe_el1_main', 'runtime_cpus', 'board_tree_diagnostic', 'text', 'hex'}
    selected = {}
    for row in frames:
        unit, name = row['location'].split(':')[0], row['location'].split(':')[-1]
        if (unit in units or unit == 'loader/rpi5/probe_main.c' and name in outer or
                unit == 'loader/rpi5/fdt.c' and name in fdt or unit == 'loader/rpi5/fdt_reg.c' and name in reg):
            key = unit + ':' + name
            if key in selected:
                raise ValueError('Ambiguous handoff stack evidence')
            selected[key] = row['bytes']
    required = {'loader/rpi5/probe_main.c:' + name for name in
                ('probe_el1_main', 'runtime_cpus', 'board_tree_diagnostic')}
    required |= {'loader/rpi5/pcie_device_handoff.c:rpi5_pcie_device_handoff',
                 'loader/rpi5/pcie_fdt.c:rpi5_fdt_pcie_rp1',
                 'loader/rpi5/memory_type.c:rpi5_memory_types_validate',
                 'loader/rpi5/fdt.c:rpi5_fdt_phandles', 'loader/rpi5/fdt.c:rpi5_fdt_property',
                 'loader/rpi5/fdt.c:rpi5_fdt_structure', 'loader/rpi5/fdt.c:rpi5_fdt_layout',
                 'loader/rpi5/fdt_reg.c:rpi5_fdt_reg'}
    if not required.issubset(selected):
        raise ValueError('Missing handoff call-chain evidence')
    # Decoder/helper/type units are nonrecursive. Deliberately overcount every
    # emitted frame in these units, including sequential alternatives.
    total = sum(selected.values())
    if total + 512 >= 0x4000:
        raise ValueError('Device handoff exhausts early stack headroom')
    return dict(conservative_bytes=total, stack_bytes=0x4000, reserved_headroom_bytes=512,
                minimum_remaining_bytes=0x4000-total, frames_bytes=selected,
                scope='Overcounted listed nonrecursive decoder/handoff C frames; not whole-program/hardware proof')


def build(output):
    captured, base = inputs()
    output = output.resolve()
    if any(output.is_relative_to(path) for path in
           (BASE, ROOT / 'loader', ROOT / 'iokit', ROOT / 'pexpert', audit.SDK, audit.OBJ)):
        raise ValueError('Handoff output must not be inside sources or accepted inputs')
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def execute(args, name):
        row = audit.execute(args, ROOT, output / (name + '.log'))
        commands.append(row)
        if row['returncode']:
            raise ValueError('Handoff build step failed: ' + row['log'])
        return row

    link = next(command for command in base['commands'] if command[0] == str(ROOT / 'tools/rpi5/tfa-lld'))
    old_main = str(BASE / 'probe_main.o')

    def replay(main, stem, extra=()):
        elf, binary = output / (stem + '.elf'), output / (stem + '.bin')
        args = [str(main) if arg == old_main else arg for arg in link]
        args[args.index('-o') + 1] = str(elf)
        args[args.index('-o'):args.index('-o')] = list(map(str, extra))
        execute(args, stem + '-link')
        execute([ROOT / 'tools/rpi5/tfa-objcopy', '-O', 'binary', elf, binary], stem + '-objcopy')
        accepted.old.inspect_elf(elf.read_bytes(), binary.read_bytes(), 0x9000000)
        return elf, binary

    _, baseline_binary = replay(Path(old_main), 'baseline-replay')
    if audit.sha(baseline_binary) != BASE_IMAGE_SHA:
        raise ValueError('Accepted object replay does not reproduce the pinned image')
    source = output / 'probe_main.c'
    shutil.copyfile(SOURCE, source)
    execute(['patch', '--batch', '--fuzz=0', '-p1', '-d', output, '-i', PATCH], 'patch')
    captured[str(source)] = audit.sha(source)
    record = next(command for command in base['commands'] if '-c' in command and
                  command[command.index('-c') + 1] == str(SOURCE))
    # Strong opt-out equivalence: same original objects/payload, rebuilt main
    # with the patch disabled, and identical entire boot binary, not just text.
    off = output / 'off-main.o'
    execute(compile_command(record, source, off, False), 'off-main')
    _, off_binary = replay(off, 'off-replay')
    if audit.sha(off_binary) != BASE_IMAGE_SHA:
        raise ValueError('Disabled handoff patch changes the accepted image')
    main, core = output / 'probe_main.o', output / 'pcie_device_handoff.o'
    execute(compile_command(record, source, main, True), 'main')
    execute(compile_command(record, CORE, core, True), 'core')
    elf, binary = replay(main, 'handoff', (core,))
    raw, payload = binary.read_bytes(), (BASE / 'payload.bin').read_bytes()
    payload_offset = raw.find(payload)
    if payload_offset < 0 or raw.find(payload, payload_offset + 1) >= 0 or payload_offset & 63:
        raise ValueError('Exact accepted payload is not uniquely aligned in the new image')
    if raw.count(MARKER) != 1 or audit.sha(binary) == BASE_IMAGE_SHA:
        raise ValueError('Distinct declaration-only marker/image required')
    symbols = audit.read_command(['xcrun', 'llvm-nm', '--defined-only', '--format=posix', elf])
    defined = {line.split()[0] for line in symbols.splitlines() if line.split()}
    if 'rpi5_pcie_device_handoff' not in defined or any(name.startswith(prefix) for name in defined for prefix in
            ('rpi5_pcie_reset_', 'rpi5_pcie_rescal_', 'rpi5_pcie_serdes_', 'rpi5_pcie_watchdog_',
             'rpi5_pcie_link_', 'rpi5_pcie_config_', 'rpi5_pcie_windows_', 'rpi5_gem_')):
        raise ValueError('Wrong declaration-only loader linkage')
    frames = [row for row in base['stack_frames'] if row['location'].split(':')[0] != 'loader/rpi5/probe_main.c']
    frames += stack_frames(main.with_suffix('.su'), 'loader/rpi5/probe_main.c')
    frames += stack_frames(core.with_suffix('.su'), 'loader/rpi5/pcie_device_handoff.c')
    depth = int(re.search(r'^#define RPI5_ADT_MAX_DEPTH ([0-9]+)$',
                         (ROOT / 'loader/rpi5/apple_dt.h').read_text(), re.M)[1])
    budgets = dict(device_handoff=device_stack(frames), runtime_plan=tree_stack.check_runtime_plan(frames, depth),
                   tree=tree_stack.check(frames, depth), topology=accepted.old.stack_check(frames))
    for name, digest in captured.items():
        if audit.sha(Path(name)) != digest:
            raise ValueError('Handoff build input changed: ' + name)
    generated = {str(path): audit.sha(path) for path in output.iterdir()
                 if path.is_file() and str(path) not in captured}
    # Deliberately NOT the old stager's manifest schema or probe.bin filename.
    # An expanded Device contract must never pass as the accepted socket image.
    report = dict(schema_version=1, profile='pcie-phy-device-handoff-v1',
        scope='Uninstalled exact-page Device declaration loader; no PHY hardware access',
        inputs_sha256=captured, generated_sha256=generated, commands=commands,
        image=str(binary), image_bytes=len(raw), image_sha256=audit.sha(binary),
        elf_audit=accepted.old.inspect_elf(elf.read_bytes(), raw, 0x9000000),
        baseline_image_sha256=BASE_IMAGE_SHA, baseline_manifest_sha256=BASE_MANIFEST_SHA,
        baseline_object_replay_identical=True, disabled_patch_boot_binary_identical=True,
        payload_sha256=audit.sha(BASE / 'payload.bin'), payload_offset=payload_offset,
        embedded_kernel_sha256=base['embedded_kernel']['sha256'],
        embedded_root_sha256=base['embedded_init']['sha256'],
        transfer_enabled=True, accepted_kernel_and_root_reused=True,
        stack_frames=frames, stack_budgets=budgets,
        added_device_ranges=[[0x1000118000, 0x100011c000], [0x1000120000, 0x100012c000],
                             [0x1001504000, 0x1001508000]], added_device_pages=5,
        legacy_installer_schema_compatible=False, device_typing_is_hardware_permission=False,
        pcie_mmio_enabled=False, phy_driver_registered=False, pcie_reset_writes=False,
        dma_authorized=False, irq_enabled=False, power_clock_admission_proven=False,
        reset_destination_proven=False, installed=False, pi_executed=False,
        sd_actions=0, serial_actions=0, reboots=0)
    (output / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path, help='New directory only')
    report = build(parser.parse_args().output_dir)
    print(json.dumps({key: report[key] for key in ('image', 'image_bytes', 'image_sha256',
        'baseline_object_replay_identical', 'disabled_patch_boot_binary_identical', 'pi_executed')}))


if __name__ == '__main__':
    main()
