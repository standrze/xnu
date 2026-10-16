#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct single-CPU XNU PCIe identification loader, never install or reboot."""
import argparse
import difflib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_firmware_fdt_handoff as retained
import build_recovery_probe as recovery
from build_probe import inspect as inspect_elf
from payload_container import encode as encode_container
import pcie_id_handoff_contract as handoff_contract

ROOT, BASE = retained.ROOT, 0x9000000
PROFILE = 'pcie-first-id-single-cpu-loader-v1'
LOADER = ROOT / 'build/rpi5/firmware-fdt-handoff-20261012-final'
LOADER_SHA = 'eed613aaa91207b3c6db298fe811e4400bb4dca2d1a7ec8858243f817561b301'
KERNEL_PACKAGE = ROOT / 'build/rpi5/pcie-id-progress-kernel-20261013-final'
KERNEL_MANIFEST_SHA = 'd57393c77dffea0a55249756c034becd04e5257222f6afe891f1bbc89aa2dd5e'
KERNEL_SHA = '50c8fb6080468498d85a07bdbd8d3fd7ad65d767b43256fbff91b210e8d6ffbb'
FIRMWARE = ROOT / 'build/rpi5/pcie-el3-verifier-20261012-checked'
FIRMWARE_MANIFEST_SHA = 'cd2fc81f2576f44a63587b917ef42eb421b317061a35311163a3d2c27c069a60'
FIRMWARE_BIN = FIRMWARE / 'build/rpi5/debug/bl31.bin'
FIRMWARE_SHA = 'dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
BOOTARGS = 'serial=1 debug=0xa -enable_kprintf_spam kt=2 -noprogress cpus=1'
CHECKER = ROOT / 'tools/rpi5/check_pcie_id_trial_package.py'
WATCHDOG = dict(lease_reload_seconds=15, ns_guard_seconds=9, secure_guard_seconds=10,
    preentry_kernel_max_service_seconds=120, preentry_max_reset_seconds=135,
    transfer_to_bootsys_bound_seconds=150, physical_timing_proven=False)
sha, symbols_for, tool_identity = recovery.sha, recovery.symbols_for, recovery.tool_identity


def verify(pins):
    for name, digest in pins.items():
        if sha(Path(name)) != digest:
            raise ValueError('PCIe-ID dependency changed: ' + name)


def inputs():
    pins, reports = {}, []
    for directory, digest in ((LOADER, LOADER_SHA), (KERNEL_PACKAGE, KERNEL_MANIFEST_SHA),
                              (FIRMWARE, FIRMWARE_MANIFEST_SHA)):
        manifest = directory / 'manifest.json'
        if sha(manifest) != digest:
            raise ValueError('Frozen PCIe-ID prerequisite changed: ' + str(manifest))
        record = json.loads(manifest.read_text())
        captured = record['inputs_sha256'] | record['generated_sha256'] | {str(manifest): digest}
        for name, value in captured.items():
            if name in pins and pins[name] != value:
                raise ValueError('Conflicting frozen PCIe-ID input: ' + name)
            pins[name] = value
        reports.append(record)
    kernel = KERNEL_PACKAGE / 'kernel.rp1-config'
    if sha(kernel) != KERNEL_SHA or sha(FIRMWARE_BIN) != FIRMWARE_SHA:
        raise ValueError('Wrong paired PCIe-ID kernel/firmware')
    for path in (kernel, FIRMWARE_BIN, Path(__file__).resolve(), CHECKER,
                 ROOT / 'tools/rpi5/compare_native_macho.py',
                 ROOT / 'tools/rpi5/audit_macho.py',
                 Path(handoff_contract.__file__).resolve(),
                 ROOT / 'tools/rpi5/tests/pcie_id_handoff_host.c',
                 ROOT / 'tools/rpi5/tests/firmware_fdt_host.c',
                 ROOT / 'tools/rpi5/tests/test_pcie_fdt.py',
                 ROOT / 'tools/rpi5/tests/test_handoff.py',
                 ROOT / 'tools/rpi5/tests/test_macho.py'):
        pins[str(path)] = sha(path)
    verify(pins)
    return pins, reports


def marker(tag):
    if not isinstance(tag, str) or not re.fullmatch(r'[0-9a-f]{32}', tag):
        raise ValueError('Fresh 128-bit trial tag required')
    return 'RPI5XNU:BL33:PCIE_ID_TRIAL TAG=' + tag + ' CPUS=1 NO_CPU_ON NO_INIT ZERO_SERIAL_INPUT'


def boot_markers(tag):
    # Materialization extent comes from the actual Mach-O segments, not its file size.
    from audit_macho import inspect
    parsed = inspect((KERNEL_PACKAGE / 'kernel.rp1-config').read_bytes())
    extent = max(s['vmaddr'] + s['vmsize'] for s in parsed['segments'] if s['vmsize']) - parsed['virtual_base']
    return [marker(tag),
        'RPI5XNU:BL33:PCIE_DEVICE_HANDOFF RANGES=3 PAGES=5 DECLARATIONS_ONLY PCIE_MMIO=0 IRQ=0 DMA=0',
        'RPI5XNU:BL33:FIRMWARE_FDT RETAINED_DESCRIPTOR_ONLY NO_RAW_TREE_OR_SEED_PUBLISHED PCIE_MMIO=0',
        'RPI5XNU:BL33:KERNEL_MATERIALIZED BYTES=' + format(extent, '016x') +
        ' FULL_ENVELOPE_VERIFIED NO_BOOT_ARGS_WRITTEN NO_TRANSFER']


def dependencies(raw):
    return {str(Path(v).resolve()): sha(Path(v).resolve())
            for v in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}


def scan_command(args):
    skip, scan = False, []
    for token in args:
        if skip: skip = False
        elif token == '-o': skip = True
        elif token != '-c': scan.append(token)
    return scan + ['-M']


def actual_header_closure(package):
    headers = {}
    for index, args in enumerate(commands_for(package)):
        if '-c' not in args: continue
        result = subprocess.run(scan_command(args), cwd=ROOT, text=True, capture_output=True, timeout=60)
        if result.returncode or result.stderr: raise ValueError('Actual header scan failed')
        now = dependencies(result.stdout)
        if now != dependencies((package / ('step-' + str(index) + '.d')).read_text()) or \
           now != dependencies((package / ('step-' + str(index) + '-scan.txt')).read_text()):
            raise ValueError('Actual compiled header closure changed')
        headers.update(now)
    return headers


def generated_names():
    names = {'probe_main.c', 'probe_main.c.diff', 'probe_main.o', 'probe_main.su',
        'psci.S', 'psci.S.diff', 'psci.o', 'payload.bin', 'payload.S', 'payload.o', 'probe.elf', 'probe.bin'}
    names.update('step-' + str(i) + '.log' for i in range(5))
    names.update('step-' + str(i) + suffix for i in range(3) for suffix in ('.d', '-scan.txt'))
    return names


def kernel_handoff_binding():
    filelist = KERNEL_PACKAGE / 'kernel.rp1-config.filelist'
    objects = filelist.read_text().splitlines()
    selected = [p for p in objects if Path(p).name == 'arm_init.c.o' or Path(p).name == 'arm_init.o']
    arm_object, arm_source = LOADER / 'arm_init.c.o', LOADER / 'arm_init.c'
    receipt = json.loads((LOADER / 'manifest.json').read_text())
    compile = next(r for r in receipt['commands'] if r['log'].endswith('/arm_init.c-compile.log'))
    source = arm_source.read_text()
    required = ['SecureDTGetProperty(chosen, "rpi5-firmware-fdt"',
        'rpi5_fdt_record_decode(', 'rpi5_physical_memory_type(',
        'panic("BCM2712: invalid retained firmware FDT descriptor")']
    start = source.index("RPI5_BOOT_MARK('K')")
    end = source.index("RPI5_BOOT_MARK('W')", start)
    if selected != [str(arm_object)] or '-DRPI5_FIRMWARE_FDT_HANDOFF=1' not in compile['command'] or \
       compile['object_sha256'] != sha(arm_object) or not all(s in source[start:end] for s in required):
        raise ValueError('Actual linked kernel retained-FDT contract changed')
    return dict(linked_object=str(arm_object), object_sha256=sha(arm_object),
        source_sha256=sha(arm_source), filelist_sha256=sha(filelist),
        property='chosen:rpi5-firmware-fdt', bytes=32, memory_type=1,
        validated_before_vm=True, decoder_sha256=sha(ROOT / 'loader/rpi5/firmware_fdt_record.h'),
        memory_type_decoder_sha256=sha(ROOT / 'osfmk/arm64/rpi5_memory_map.h'))


def derive_main(tag):
    original = (LOADER / 'probe_main.c').read_text()
    text = original
    # Only this derived diagnostic permits the Device/full-FDT path without a
    # terminal. Explicitly require terminal OFF rather than dropping the guard.
    if text.count('|| !RPI5_SERIAL_TERMINAL || RPI5_GATE4_STORAGE') != 2:
        raise ValueError('Device/FDT compile admission guards changed')
    text = text.replace('|| !RPI5_SERIAL_TERMINAL || RPI5_GATE4_STORAGE',
                        '|| RPI5_SERIAL_TERMINAL || RPI5_GATE4_STORAGE')
    start = text.index('static int start_secondaries(')
    end = text.index('static int psci_affinity_inventory(', start)
    text = text[:start] + text[end:]
    declaration = 'extern uint64_t rpi5_psci_cpu_on(uint64_t affinity, uintptr_t entry, uint64_t context);\n'
    if text.count(declaration) != 1:
        raise ValueError('CPU_ON declaration changed')
    text = text.replace(declaration, '')
    old = '    if (!psci_affinity_inventory(cpus)) return 0;\n    return start_secondaries(cpus);'
    if text.count(old) != 1:
        raise ValueError('PSCI diagnostic tail changed')
    text = text.replace(old, '    return psci_affinity_inventory(cpus);')
    anchor = '    size_t command_length=0;'
    if text.count(anchor) != 1:
        raise ValueError('Bootarg publication anchor changed')
    text = text.replace(anchor, '    command_line = "' + BOOTARGS + '";\n' + anchor)
    anchor = 'void probe_el1_main(uintptr_t fdt_pa)\n{\n'
    if text.count(anchor) != 1:
        raise ValueError('Primary entry changed')
    text = text.replace(anchor, anchor + '    if (!text("' + marker(tag) + '\\r\\n")) return;\n')
    if 'start_secondaries' in text or 'rpi5_psci_cpu_on(' in text:
        raise ValueError('Actual loader CPU_ON still present')
    return original, text


def derive_psci():
    original = (ROOT / 'loader/rpi5/psci.S').read_text()
    begin = original.index('/* CPU_ON64:')
    end = original.index('/* CPU_OFF32', begin)
    derived = original[:begin] + original[end:]
    if 'rpi5_psci_cpu_on' in derived:
        raise ValueError('CPU_ON assembly helper remains')
    return original, derived


def commands_for(package):
    old = json.loads((LOADER / 'manifest.json').read_text())
    main = next(r['command'] for r in old['commands'] if r['log'].endswith('/loader-main.log'))
    main = list(main)
    main[main.index('-c') + 1] = str(package / 'probe_main.c')
    main[main.index('-o') + 1] = str(package / 'probe_main.o')
    for index, value in enumerate(main):
        if value.startswith(('-DRPI5_GATE3_', '-DRPI5_SERIAL_TERMINAL=', '-DRPI5_GATE4_')):
            key, _, old_value = value.partition('=')
            main[index] = key + ('=""' if old_value == '""' else '=0')
    link = next(r['command'] for r in old['commands'] if r['log'].endswith('/firmware-fdt-link.log'))
    replacements = {str(LOADER / 'probe_main.o'): str(package / 'probe_main.o')}
    for name in ('psci.o', 'payload.o'):
        matches = [value for value in link if value.endswith('/' + name)]
        if len(matches) != 1:
            raise ValueError('Unexpected loader object: ' + name)
        replacements[matches[0]] = str(package / name)
    link = [replacements.get(value, value) for value in link]
    link[link.index('-o') + 1] = str(package / 'probe.elf')
    assembler = ['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                 '-mstrict-align', '-ffreestanding', '-fno-stack-protector', '-mgeneral-regs-only',
                 '-O2', '-Wall', '-Wextra', '-Werror']
    return [main, assembler + ['-c', str(package / 'psci.S'), '-o', str(package / 'psci.o')],
            assembler + ['-c', str(package / 'payload.S'), '-o', str(package / 'payload.o')], link,
            [str(ROOT / 'tools/rpi5/tfa-objcopy'), '-O', 'binary', str(package / 'probe.elf'), str(package / 'probe.bin')]]


def stack_for(package, old):
    device = retained.device
    frames = [r for r in old['stack_frames'] if r['location'].split(':')[0] != 'loader/rpi5/probe_main.c']
    frames += device.stack_frames(package / 'probe_main.su', 'loader/rpi5/probe_main.c')
    depth = int(re.search(r'^#define RPI5_ADT_MAX_DEPTH ([0-9]+)$',
                         (ROOT / 'loader/rpi5/apple_dt.h').read_text(), re.M)[1])
    budgets = dict(device_handoff=device.device_stack(frames),
                   tree=device.tree_stack.check(frames, depth),
                   runtime_plan=device.tree_stack.check_runtime_plan(frames, depth))
    added = [r for r in frames if r['location'].startswith('loader/rpi5/firmware_fdt_tree.c:')]
    total = budgets['device_handoff']['conservative_bytes'] + sum(r['bytes'] for r in added)
    if not added or total + 512 >= 0x4000:
        raise ValueError('Unbounded retained-FDT stack')
    budgets['firmware_fdt'] = dict(conservative_bytes=total, minimum_remaining_bytes=0x4000 - total)
    return frames, budgets


def build():
    pins, reports = inputs()
    identities = tool_identity()
    package = Path(tempfile.mkdtemp(prefix='pcie-id-trial-', dir=ROOT / 'build/rpi5'))
    tag = uuid.uuid4().hex
    for name, pair in (('probe_main.c', derive_main(tag)), ('psci.S', derive_psci())):
        original, derived = pair
        (package / name).write_text(derived)
        (package / (name + '.diff')).write_text(''.join(difflib.unified_diff(
            original.splitlines(True), derived.splitlines(True), fromfile='frozen/' + name, tofile=name)))
    kernel = KERNEL_PACKAGE / 'kernel.rp1-config'
    payload = encode_container(kernel.read_bytes(), None)
    (package / 'payload.bin').write_bytes(payload)
    (package / 'payload.S').write_text('.section .payload,"a"\n.balign 64\n.incbin "' + str(package / 'payload.bin') + '"\n')
    commands, records, headers = commands_for(package), [], {}
    for index, args in enumerate(commands):
        scan = None
        if '-c' in args:
            skip, scan = False, []
            for token in args:
                if skip:
                    skip = False
                elif token == '-o':
                    skip = True
                elif token != '-c':
                    scan.append(token)
            r = subprocess.run(scan + ['-M'], cwd=ROOT, text=True, capture_output=True, timeout=60)
            if r.returncode:
                raise ValueError('PCIe-ID dependency scan failed: ' + r.stderr)

            def dependencies(raw):
                return {str(Path(v).resolve()): sha(Path(v).resolve())
                        for v in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}

            before = dependencies(r.stdout)
            (package / ('step-' + str(index) + '-scan.txt')).write_text(r.stdout)
        actual = args + ['-MD', '-MF', str(package / ('step-' + str(index) + '.d'))] if scan else args
        r = subprocess.run(actual, cwd=ROOT, text=True, capture_output=True, timeout=60)
        log = package / ('step-' + str(index) + '.log')
        log.write_text(r.stdout + r.stderr)
        records.append(dict(command=actual, returncode=r.returncode, log=str(log)))
        if r.returncode or r.stderr:
            raise ValueError('PCIe-ID compile/link error or warning: ' + str(log))
        if scan:
            after = dependencies((package / ('step-' + str(index) + '.d')).read_text())
            if before != after:
                raise ValueError('PCIe-ID compiler selected changing dependencies')
            headers.update(after)
    raw, elf = (package / 'probe.bin').read_bytes(), package / 'probe.elf'
    layout = inspect_elf(elf.read_bytes(), raw, BASE)
    offset = raw.find(payload)
    if offset < 0 or offset & 63 or raw.count(payload) != 1:
        raise ValueError('Exact unique aligned kernel-only container missing')
    frames, budgets = stack_for(package, reports[0])
    header_closure = actual_header_closure(package)
    if headers != header_closure:
        raise ValueError('Recorded actual header closure incomplete')
    native_handoff = handoff_contract.audit(LOADER)
    handoff_binding = kernel_handoff_binding()
    verify(pins)
    verify(headers)
    if tool_identity() != identities:
        raise ValueError('Actual loader tools changed during build')
    report = dict(profile=PROFILE, trial_tag=tag, marker=marker(tag), bootargs=BOOTARGS,
                  boot_markers=boot_markers(tag), native_handoff_contract=native_handoff,
                  kernel_handoff_binding=handoff_binding,
                  inputs_sha256=pins, headers_sha256=headers, commands=commands, actual_commands=records,
                  tool_identity=identities, image=str(package / 'probe.bin'), image_bytes=len(raw),
                  image_sha256=sha(package / 'probe.bin'), kernel=str(kernel), kernel_sha256=KERNEL_SHA,
                  kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
                  firmware=str(FIRMWARE_BIN), firmware_sha256=FIRMWARE_SHA,
                  firmware_manifest_sha256=FIRMWARE_MANIFEST_SHA,
                  entry=layout['entry'], loads=layout['loads'], payload_offset=offset, embedded_init=None,
                  stack_frames=frames, stack_budgets=budgets, source_stable=True,
                  watchdog=WATCHDOG,
                  cpu_on=False, root_embedded=False, serial_input_allowed=False, storage=False,
                  dma=False, ethernet_proven=False, installed=False, physical_execution=False,
                  generated_sha256={str(p): sha(p) for p in package.iterdir() if p.is_file()})
    if {Path(p).name for p in report['generated_sha256']} != generated_names():
        raise ValueError('Unexpected generated file closure')
    (package / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return package, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    package, report = build()
    print(json.dumps({k: report[k] for k in ('image', 'image_sha256', 'image_bytes', 'trial_tag', 'kernel_sha256')}, indent=2))
