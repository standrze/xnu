#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Correct the failed root96 loader composition; no board operations.

The kernel/root bytes stay exact. Reuse the separately compiled retained-FDT
loader only after reproducing its original binary from the pinned link inputs.
The root is an opaque payload to BL33, not a 32-entry runtime parser there.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

try:
    from . import build_firmware_fdt_handoff as retained
    from . import check_root96_ssh_package as failed
    from .payload_container import encode
    from .build_recovery_probe import symbols_for, tool_identity
except ImportError:
    import build_firmware_fdt_handoff as retained
    import check_root96_ssh_package as failed
    from payload_container import encode
    from build_recovery_probe import symbols_for, tool_identity

ROOT = retained.ROOT
LOADER = ROOT / 'build/rpi5/firmware-fdt-handoff-20261012-final'
LOADER_SHA = 'eed613aaa91207b3c6db298fe811e4400bb4dca2d1a7ec8858243f817561b301'
FAILED = ROOT / 'build/rpi5/bl33-probe-gm1ci0lg'
PROFILE = 'root96-retained-fdt-bounded-v1'
BASE = 0x9000000
sha = retained.audit.sha


def verify(pins):
    for name, digest in pins.items():
        if sha(Path(name)) != digest:
            raise ValueError('Root96 FDT input changed: ' + name)


def dependencies(raw):
    return {str(Path(p).resolve()): sha(Path(p).resolve())
            for p in shlex.split(raw.replace('\\\n', ' ').partition(':')[2])}


def handoff_contract(package, kernel):
    """Actual linked symbols and loader-prefix evidence, not payload strings."""
    raw = (package / 'probe.bin').read_bytes()
    payload = (package / 'payload.bin').read_bytes()
    offset = raw.find(payload)
    symbols = symbols_for(package / 'probe.elf')
    kernel_bytes = kernel.read_bytes()
    if b'BCM2712: invalid retained firmware FDT descriptor' not in kernel_bytes:
        raise ValueError('Expected exact FDT-requiring kernel')
    required = ('rpi5_firmware_fdt_tree_attach', 'rpi5_firmware_seed_tree', 'rpi5_pcie_device_handoff')
    if offset <= 0 or raw.count(payload) != 1 or offset % 64 or any(
            name not in symbols or symbols[name][0] not in ('t', 'T') or
            not BASE <= int(symbols[name][1], 16) < BASE + offset for name in required):
        raise ValueError('FDT-requiring kernel lacks linked retained-FDT/Device handoff')
    prefix = raw[:offset]
    if any(marker not in prefix for marker in (
            retained.MARKER, retained.device.MARKER, b'rpi5-firmware-fdt\0')):
        raise ValueError('Retained descriptor must be emitted by the loader, not embedded kernel')
    return dict(required_by_kernel=True, linked_loader_handoff=True,
                descriptor_not_confused_with_kernel_string=True, payload_offset=offset)


def inputs():
    if sha(LOADER / 'manifest.json') != LOADER_SHA:
        raise ValueError('Frozen retained-FDT loader changed')
    old = json.loads((LOADER / 'manifest.json').read_text())
    # This proves source/layout identity of the FAILED composition, not boot.
    prior = failed.inspect(FAILED)
    composition = json.loads((FAILED / 'capacity.json').read_text())
    pins = old['inputs_sha256'] | old['generated_sha256'] | composition['inputs_sha256']
    for p in (LOADER / 'manifest.json', FAILED / 'capacity.json', FAILED / 'probe.bin',
              Path(__file__).resolve(), Path(failed.__file__).resolve()):
        digest = sha(p)
        if str(p) in pins and pins[str(p)] != digest:
            raise ValueError('Conflicting retained-FDT input')
        pins[str(p)] = digest
    verify(pins)
    return pins, old, prior


def build():
    pins, old, prior = inputs()
    tools = tool_identity()
    out = Path(tempfile.mkdtemp(prefix='root96-fdt-', dir=ROOT / 'build/rpi5'))
    commands, headers = [], {}

    def run(command, label):
        command = list(map(str, command))
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=60)
        log = out / (label + '.log')
        log.write_text(result.stdout + result.stderr)
        commands.append(dict(command=command, returncode=result.returncode, log=str(log)))
        if result.returncode or result.stderr:
            raise ValueError('Root96 FDT build failed: ' + str(log))
        return result.stdout

    link = next(row['command'] for row in old['commands'] if row['log'].endswith('/firmware-fdt-link.log'))
    replay = list(link)
    replay[replay.index('-o') + 1] = str(out / 'baseline.elf')
    run(replay, 'baseline-link')
    run([ROOT / 'tools/rpi5/tfa-objcopy', '-O', 'binary', out / 'baseline.elf', out / 'baseline.bin'], 'baseline-copy')
    if sha(out / 'baseline.bin') != old['image_sha256']:
        raise ValueError('Pinned loader object replay differs')
    kernel_manifest = Path(prior['kernel_manifest'])
    kernel = Path(json.loads(kernel_manifest.read_text())['kernel'])
    root = Path(prior['root_manifest']).parent / 'ramdisk.bin'
    if sha(kernel) != failed.KERNEL_SHA or sha(root) != failed.ROOT_SHA:
        raise ValueError('Do not change kernel or root in this loader correction')
    payload = encode(kernel.read_bytes(), root.read_bytes())
    (out / 'payload.bin').write_bytes(payload)
    (out / 'payload.S').write_text('.section .payload,"a"\n.balign 64\n.incbin "' + str(out / 'payload.bin') + '"\n')
    compile_args = ['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
                    '-mstrict-align', '-ffreestanding', '-fno-stack-protector', '-mgeneral-regs-only',
                    '-O2', '-Wall', '-Wextra', '-Werror']
    headers = dependencies(run(compile_args + ['-M', out / 'payload.S'], 'payload-dependencies'))
    run(compile_args + ['-MD', '-MF', out / 'payload.d', '-c', out / 'payload.S', '-o', out / 'payload.o'], 'payload-compile')
    if dependencies((out / 'payload.d').read_text()) != headers:
        raise ValueError('Payload dependency scan drift')
    old_payload = [value for value in link if value.endswith('/payload.o')]
    if len(old_payload) != 1:
        raise ValueError('Ambiguous preserved payload object')
    new_link = [str(out / 'payload.o') if value == old_payload[0] else value for value in link]
    new_link[new_link.index('-o') + 1] = str(out / 'probe.elf')
    run(new_link, 'corrected-link')
    run([ROOT / 'tools/rpi5/tfa-objcopy', '-O', 'binary', out / 'probe.elf', out / 'probe.bin'], 'corrected-copy')
    raw = (out / 'probe.bin').read_bytes()
    layout = retained.device.accepted.old.inspect_elf((out / 'probe.elf').read_bytes(), raw, BASE)
    if max(row['address'] + row['memory_size'] for row in layout['loads']) >= 0xb000000:
        raise ValueError('Corrected loader collides with firmware FDT load address')
    contract = handoff_contract(out, kernel)
    if raw.count(failed.terminal.TERMINAL_COMMAND + b'\0') != 1:
        raise ValueError('Retained loader changed actual terminal command')
    main = next(row['command'] for row in old['commands'] if row['log'].endswith('/loader-main.log'))
    if not all(flag in main for flag in ('-DRPI5_SERIAL_TERMINAL=1', '-DRPI5_FIRMWARE_FDT_HANDOFF=1', '-DRPI5_PCIE_DEVICE_HANDOFF=1')):
        raise ValueError('Retained loader missing real enabled handoff flags')
    verify(pins)
    verify(headers)
    if tool_identity() != tools:
        raise ValueError('Tool identity changed')
    report = dict(profile=PROFILE, inputs_sha256=pins, headers_sha256=headers, commands=commands,
                  image=str(out / 'probe.bin'), image_sha256=sha(out / 'probe.bin'), image_bytes=len(raw),
                  kernel=str(kernel), kernel_sha256=failed.KERNEL_SHA, root=str(root), root_sha256=failed.ROOT_SHA,
                  kernel_manifest=str(kernel_manifest), kernel_manifest_sha256=failed.KERNEL_MANIFEST_SHA,
                  root_manifest=prior['root_manifest'], root_manifest_sha256=failed.ROOT_MANIFEST_SHA,
                  entry=BASE, elf=layout, handoff=contract, tool_identity=tools,
                  original_loader_reproduced=True, loader_code_objects_unchanged=True,
                  original_loader_sha256=old['image_sha256'], original_link=link,
                  original_loader_manifest_sha256=LOADER_SHA,
                  stack_frames=old['stack_frames'], stack_budgets=old['stack_budgets'],
                  terminal_bootargs=failed.terminal.TERMINAL_COMMAND.decode(),
                  terminal_watchdog_seconds=180, hardware_watchdog_seconds=15,
                  normal_firmware_sha256=failed.NORMAL_FIRMWARE_SHA,
                  root96_geometry=prior, failed_package_preserved=True,
                  installed=False, physical_execution=False, controller_initialized=False,
                  generated_sha256={str(p): sha(p) for p in out.iterdir() if p.is_file()})
    (out / 'manifest.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    return out, report


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory, record = build()
    print(json.dumps({name: record[name] for name in ('image', 'image_sha256', 'image_bytes', 'handoff')}))
