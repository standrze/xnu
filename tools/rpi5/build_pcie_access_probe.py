#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a distinct actual early-access diagnostic; NEVER install or reboot."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from build_probe import inspect as inspect_elf

ROOT = Path(__file__).resolve().parents[2]
BASE = 0x9000000
SOURCES = tuple(ROOT/'loader/rpi5'/name for name in (
    'probe_entry.S', 'probe_access_main.c', 'access_mmio.S', 'pcie_access.c',
    'uart.c', 'psci.S', 'fdt.c', 'fdt_reg.c', 'pcie_fdt.c', 'ranges.c', 'memory.S'))
INPUTS = SOURCES + tuple(ROOT/'loader/rpi5'/name for name in (
    'probe.ld', 'fdt.h', 'pcie_access.h', 'pcie_fdt.h', 'ranges.h', 'uart.h')) + (
    Path(__file__).resolve(), ROOT/'tools/rpi5/build_probe.py',
    ROOT/'tools/rpi5/check_pcie_access_package.py',
    ROOT/'tools/rpi5/tfa-lld', ROOT/'tools/rpi5/tfa-objcopy',
    ROOT/'tools/rpi5/loader-toolchain.lock.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    pins = {str(p.relative_to(ROOT)): sha(p) for p in INPUTS}
    run = Path(tempfile.mkdtemp(prefix='pcie-access-', dir=ROOT/'build/rpi5'))
    commands = []

    def execute(command):
        commands.append([str(v) for v in command])
        subprocess.run(commands[-1], cwd=ROOT, check=True, timeout=60)

    objects = []
    for source in SOURCES:
        obj = run/(source.stem+'.o')
        flags = ['-fstack-usage','-ffunction-sections','-fdata-sections'] if source.suffix == '.c' else []
        execute(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
                 '-mstrict-align','-ffreestanding','-fno-builtin','-fno-stack-protector',
                 '-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror',*flags,
                 '-c',source,'-o',obj])
        objects.append(obj)
    elf, binary = run/'probe.elf', run/'probe.bin'
    execute([ROOT/'tools/rpi5/tfa-lld','--gc-sections',f'--defsym=LOADER_BASE={hex(BASE)}',
             '-T',ROOT/'loader/rpi5/probe.ld',*objects,'-o',elf])
    execute([ROOT/'tools/rpi5/tfa-objcopy','-O','binary',elf,binary])
    report = inspect_elf(elf.read_bytes(),binary.read_bytes(),BASE)
    symbols = subprocess.check_output(['xcrun','llvm-nm','--defined-only','--format=posix',str(elf)],
                                      text=True,timeout=30)
    linked = {row.split()[0] for row in symbols.splitlines() if len(row.split()) >= 2 and row.split()[1] in ('t','T')}
    frames = []
    stack_files = [run/(p.stem+'.su') for p in SOURCES if p.suffix == '.c']
    for path in stack_files:
        for line in path.read_text().splitlines():
            location, size, kind = line.split('\t')
            if location.rsplit(':',1)[-1] not in linked:
                continue
            if kind != 'static' or int(size) < 0:
                raise ValueError('Unbounded stack frame: '+line)
            frames.append(dict(location=location, bytes=int(size), kind=kind))
    # Deliberately overcount all emitted linked C frames, even mutually exclusive
    # functions. The reviewed decoder/console code is nonrecursive. 512 bytes
    # remain reserved for assembly/alignment overhead, not measured high-water.
    total = sum(r['bytes'] for r in frames)
    if not frames or total+512 >= 0x4000:
        raise ValueError(f'Conservative linked C stack bound rejected: {total}')
    if {str(p.relative_to(ROOT)): sha(p) for p in INPUTS} != pins:
        raise ValueError('Sources changed during diagnostic build')
    outputs = [elf,binary,*objects,*stack_files]
    report.update(profile='pcie2-readonly-access-v1', image=str(binary), image_bytes=binary.stat().st_size,
                  commands=commands, stack_frames=frames,
                  stack_budget=dict(conservative_bytes=total, stack_bytes=0x4000, required_margin=512),
                  sha256={**pins, **{str(p.relative_to(ROOT)):sha(p) for p in outputs}},
                  sources_stable=True, xnu_transfer=False, kernel_embedded=False, root_embedded=False,
                  pcie_mmio=True, pcie_writes=False, config_access=False, irq_enable=False, dma=False,
                  reset_calibration_writes=False, watchdog_reload_once_seconds=15,
                  watchdog_destination_proven=False, hardware_recovery_proven=False,
                  physical_execution=False, installed=False,
                  scope='Actual read-only early-access implementation/build; not admission, hardware execution or recovery proof')
    with (run/'manifest.json').open('x') as stream:
        json.dump(report,stream,indent=2,sort_keys=True)
        stream.write('\n')
    return report


if __name__ == '__main__':
    report = build()
    print(json.dumps({k:report[k] for k in ('image','image_bytes','profile','stack_budget','physical_execution',
                                           'installed','hardware_recovery_proven')},indent=2))
