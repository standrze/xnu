#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a separate watchdog-only BL33 trial. Never install or reboot."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from build_probe import inspect as inspect_elf

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x9000000
PROFILE = 'pm-watchdog-only-v1'
SOURCES = tuple(ROOT/'loader/rpi5'/name for name in (
    'recovery_entry.S', 'probe_recovery_main.c', 'recovery_pm.S', 'pcie_watchdog_lease.c',
    'uart.c', 'fdt.c', 'fdt_reg.c', 'ranges.c', 'memory.S'))
INPUTS = SOURCES + tuple(ROOT/'loader/rpi5'/name for name in (
    'probe.ld', 'probe_entry.S', 'recovery_pm.h', 'recovery_pm.inc', 'pcie_watchdog_lease.h',
    'fdt.h', 'ranges.h', 'uart.h')) + tuple(ROOT/'tools/rpi5'/name for name in (
    'build_recovery_probe.py', 'check_recovery_package.py', 'build_probe.py',
    'payload_container.py', 'audit_macho.py', 'ramroot.py', 'prepare_pid1.py',
    'tests/test_recovery_probe.py', 'tests/recovery_probe_host.c',
    'tfa-lld', 'tfa-objcopy', 'loader-toolchain.lock.json'))
FALSE_CLAIMS = ('installed', 'physical_execution', 'hardware_recovery_proven',
    'watchdog_destination_proven', 'xnu_transfer', 'kernel_embedded', 'root_embedded',
    'pcie_mmio', 'pcie_writes', 'config_access', 'irq_enable', 'dma',
    'reset_calibration_writes', 'reset_route_writes', 'cpu_on')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tool_identity():
    # Resolve only the configured local tools, never a manifest-supplied path.
    result = {}
    for name in ('clang', 'llvm-nm'):
        path = Path(subprocess.check_output(['xcrun', '--find', name], text=True, timeout=30).strip())
        result[name] = dict(path=str(path), sha256=sha(path))
    zig = ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig'
    result['zig'] = dict(path=str(zig), sha256=sha(zig))
    return result


def commands_for(run, tag):
    if not re.fullmatch('[0-9a-f]{32}', tag):
        raise ValueError('Fresh image tag must be 32 lowercase hex digits')
    commands, objects = [], []
    for source in SOURCES:
        obj = run/(source.stem+'.o')
        flags = ['-fstack-usage', '-ffunction-sections', '-fdata-sections'] if source.suffix == '.c' else []
        commands.append(['xcrun', 'clang', '--target=aarch64-none-elf', '-mcpu=cortex-a76',
            '-mstrict-align', '-ffreestanding', '-fno-builtin', '-fno-stack-protector',
            '-mgeneral-regs-only', '-O2', '-Wall', '-Wextra', '-Werror',
            '-DRPI5_RECOVERY_PM_PROBE=1', f'-DRPI5_RECOVERY_TRIAL_TAG="{tag}"', *flags,
            '-c', str(source), '-o', str(obj)])
        objects.append(obj)
    commands.append([str(ROOT/'tools/rpi5/tfa-lld'), '--gc-sections',
        f'--defsym=LOADER_BASE={hex(BASE)}', '-T', str(ROOT/'loader/rpi5/probe.ld'),
        *map(str, objects), '-o', str(run/'probe.elf')])
    commands.append([str(ROOT/'tools/rpi5/tfa-objcopy'), '-O', 'binary',
        str(run/'probe.elf'), str(run/'probe.bin')])
    return commands


def outputs_for(run):
    return (run/'probe.elf', run/'probe.bin',
        *(run/(p.stem+'.o') for p in SOURCES),
        *(run/(p.stem+'.su') for p in SOURCES if p.suffix == '.c'))


def symbols_for(elf):
    rows = subprocess.check_output(['xcrun', 'llvm-nm', '--defined-only',
        '--format=posix', str(elf)], text=True, timeout=30)
    return {r[0]:r[1:4] for line in rows.splitlines() if len(r := line.split()) >= 4}


def stack_for(run, symbols):
    frames = []
    for source in SOURCES:
        if source.suffix != '.c':
            continue
        for line in (run/(source.stem+'.su')).read_text().splitlines():
            location, size, kind = line.split('\t')
            name = location.rsplit(':', 1)[-1]
            if name not in symbols or symbols[name][0] not in ('t', 'T'):
                continue
            if kind != 'static' or int(size) < 0:
                raise ValueError('Unbounded emitted C frame: '+line)
            frames.append(dict(location=location, bytes=int(size), kind=kind))
    total = sum(row['bytes'] for row in frames)
    # Sum all linked nonrecursive C frames, including mutually exclusive ones.
    # Not a measured stack high-water or proof about arbitrary recursive code.
    if not frames or total+512 >= 0x4000:
        raise ValueError(f'Conservative stack bound refused: {total}')
    return frames, dict(conservative_bytes=total, stack_bytes=0x4000, required_margin=512)


def build():
    pins = {str(p.relative_to(ROOT)):sha(p) for p in INPUTS}
    tools = tool_identity()
    run = Path(tempfile.mkdtemp(prefix='pm-recovery-', dir=ROOT/'build/rpi5'))
    tag = uuid.uuid4().hex
    commands = commands_for(run, tag)
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True, timeout=60)
    binary, elf = run/'probe.bin', run/'probe.elf'
    report = inspect_elf(elf.read_bytes(), binary.read_bytes(), BASE)
    frames, budget = stack_for(run, symbols_for(elf))
    if {str(p.relative_to(ROOT)):sha(p) for p in INPUTS} != pins or tool_identity() != tools:
        raise ValueError('Source or tool changed during build')
    report.update(profile=PROFILE, trial_tag=tag, image=str(binary), image_bytes=binary.stat().st_size,
        commands=commands, tool_identity=tools, stack_frames=frames, stack_budget=budget,
        sha256={**pins, **{str(p.relative_to(ROOT)):sha(p) for p in outputs_for(run)}},
        sources_stable=True, watchdog_reload_once_seconds=15, **dict.fromkeys(FALSE_CLAIMS, False),
        scope='Standalone PM watchdog code/build only; no install, autonomous reset or SSD-return acceptance')
    with (run/'manifest.json').open('x') as stream:
        json.dump(report, stream, indent=2, sort_keys=True)
        stream.write('\n')
    return report


if __name__ == '__main__':
    report = build()
    print(json.dumps({k:report[k] for k in ('image', 'image_bytes', 'trial_tag', 'profile',
        'stack_budget', 'installed', 'physical_execution', 'hardware_recovery_proven')}, indent=2))
