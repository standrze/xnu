#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Build a distinct paired-firmware ABI trial; never install or reboot."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid

# Historical helper modules are CLI-first and use local absolute imports.
# Keep both direct-script and package imports functional without editing them.
sys.path.insert(0,str(Path(__file__).resolve().parent))

try:
    from . import build_recovery_probe as recovery
    from .build_probe import inspect as inspect_elf
except ImportError:
    import build_recovery_probe as recovery
    from build_probe import inspect as inspect_elf

ROOT,BASE=recovery.ROOT,recovery.BASE
PROFILE='pcie-firmware-abi-trial-v1'
FIRMWARE=ROOT/'build/rpi5/pcie-el3-verifier-20261012-checked'
FIRMWARE_MANIFEST_SHA='cd2fc81f2576f44a63587b917ef42eb421b317061a35311163a3d2c27c069a60'
FIRMWARE_BIN=FIRMWARE/'build/rpi5/debug/bl31.bin'
FIRMWARE_SHA='dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b'
SOURCES=tuple(ROOT/'loader/rpi5'/name for name in (
    'recovery_entry.S','probe_fw_trial_main.c','recovery_pm.S','pcie_fw_trial_mmio.S',
    'pcie_fw_smccc.S','pcie_fw_client.c','pcie_irq_mask.c','pcie_watchdog_lease.c',
    'uart.c','fdt.c','fdt_reg.c','pcie_fdt.c','ranges.c','memory.S'))
INPUTS=SOURCES+tuple(ROOT/'loader/rpi5'/name for name in (
    'probe.ld','pcie_fw_trial.h','pcie_fw_trial.inc','recovery_pm.h','pcie_fw_client.h',
    'pcie_irq_mask.h','pcie_watchdog_lease.h','fdt.h','pcie_fdt.h','ranges.h','uart.h'))+(
    ROOT/'firmware/rpi5/pcie_verifier.h',)+tuple(ROOT/'tools/rpi5'/name for name in (
    'build_pcie_fw_trial.py','check_pcie_fw_trial_package.py','build_recovery_probe.py',
    'check_recovery_package.py','build_probe.py','payload_container.py','audit_macho.py',
    'ramroot.py','prepare_pid1.py','tests/test_pcie_fw_trial.py','tests/pcie_fw_trial_host.c',
    'pcie_fw_trial_serial_core.py','tests/test_pcie_fw_trial_serial.py',
    'tfa-lld','tfa-objcopy','loader-toolchain.lock.json'))
FALSE_CLAIMS=('installed','firmware_installed','physical_execution','hardware_recovery_proven',
    'watchdog_destination_proven','xnu_transfer','kernel_embedded','root_embedded',
    'pcie_mmio','pcie_writes','config_access','irq_enable','dma','ethernet_proven',
    'reset_calibration_writes','reset_route_writes','cpu_on','full_controller_ownership_proven')
sha=recovery.sha
tool_identity=recovery.tool_identity
symbols_for=recovery.symbols_for


def input_pins():
    if sha(FIRMWARE/'manifest.json')!=FIRMWARE_MANIFEST_SHA or sha(FIRMWARE_BIN)!=FIRMWARE_SHA:
        raise ValueError('Accepted firmware producer changed')
    fw=json.loads((FIRMWARE/'manifest.json').read_text())
    pins={**fw['inputs_sha256'],**fw['generated_sha256'],str(FIRMWARE/'manifest.json'):FIRMWARE_MANIFEST_SHA}
    for p in INPUTS:
        key=str(p);digest=sha(p)
        if key in pins and pins[key]!=digest:raise ValueError('Conflicting firmware/trial input: '+key)
        pins[key]=digest
    for name,pin in pins.items():
        if sha(Path(name))!=pin:raise ValueError('Firmware/trial input changed: '+name)
    return pins


def commands_for(run,tag):
    if not isinstance(tag,str) or not re.fullmatch('[0-9a-f]{32}',tag):raise ValueError('Invalid fresh trial tag')
    commands=[];objects=[]
    for source in SOURCES:
        obj=run/(source.stem+'.o')
        flags=['-fstack-usage','-ffunction-sections','-fdata-sections'] if source.suffix=='.c' else []
        commands.append(['xcrun','clang','--target=aarch64-none-elf','-mcpu=cortex-a76',
            '-mstrict-align','-ffreestanding','-fno-builtin','-fno-stack-protector',
            '-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror',
            '-DRPI5_PCIE_FW_TRIAL=1','-DRPI5_PCIE_FW_CLIENT=1',f'-DRPI5_FW_TRIAL_TAG="{tag}"',
            *flags,'-c',str(source),'-o',str(obj)])
        objects.append(obj)
    commands.append([str(ROOT/'tools/rpi5/tfa-lld'),'--gc-sections',f'--defsym=LOADER_BASE={hex(BASE)}',
        '-T',str(ROOT/'loader/rpi5/probe.ld'),*map(str,objects),'-o',str(run/'probe.elf')])
    commands.append([str(ROOT/'tools/rpi5/tfa-objcopy'),'-O','binary',str(run/'probe.elf'),str(run/'probe.bin')])
    return commands


def outputs_for(run):
    return (run/'probe.elf',run/'probe.bin',*(run/(p.stem+'.o') for p in SOURCES),
        *(run/(p.stem+'.su') for p in SOURCES if p.suffix=='.c'))


def stack_for(run,symbols):
    frames=[]
    for source in SOURCES:
        if source.suffix!='.c':continue
        for line in (run/(source.stem+'.su')).read_text().splitlines():
            location,size,kind=line.split('\t');name=location.rsplit(':',1)[-1]
            if name not in symbols or symbols[name][0] not in ('t','T'):continue
            if kind!='static' or int(size)<0:raise ValueError('Unbounded emitted C stack: '+line)
            frames.append(dict(location=location,bytes=int(size),kind=kind))
    total=sum(row['bytes'] for row in frames)
    if not frames or total+512>=0x4000:raise ValueError('Conservative stack sum exceeds standalone stack')
    return frames,dict(conservative_bytes=total,stack_bytes=0x4000,required_margin=512)


def build():
    pins=input_pins();tools=tool_identity()
    run=Path(tempfile.mkdtemp(prefix='pcie-fwabi-',dir=ROOT/'build/rpi5'))
    tag=uuid.uuid4().hex;commands=commands_for(run,tag)
    for cmd in commands:subprocess.run(cmd,cwd=ROOT,check=True,timeout=60)
    binary,elf=run/'probe.bin',run/'probe.elf'
    report=inspect_elf(elf.read_bytes(),binary.read_bytes(),BASE)
    frames,budget=stack_for(run,symbols_for(elf))
    if input_pins()!=pins or tool_identity()!=tools:raise ValueError('Inputs/tools changed during build')
    report.update(profile=PROFILE,trial_tag=tag,image=str(binary),image_bytes=binary.stat().st_size,
        commands=commands,tool_identity=tools,stack_frames=frames,stack_budget=budget,
        inputs_sha256=pins,generated_sha256={str(p):sha(p) for p in outputs_for(run)},
        firmware_image=str(FIRMWARE_BIN),firmware_sha256=FIRMWARE_SHA,
        firmware_manifest_sha256=FIRMWARE_MANIFEST_SHA,sources_stable=True,
        selective_gic_disable_writes=3,watchdog_reload_once_seconds=15,firmware_checks=3,
        secure_verifier_mmio_reads=True,**dict.fromkeys(FALSE_CLAIMS,False),
        scope='Standalone actual firmware/client ABI build, not XNU PE/IOKit runtime or controller/board acceptance')
    with (run/'manifest.json').open('x') as stream:
        json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    r=build()
    print(json.dumps({k:r[k] for k in ('image','image_bytes','trial_tag','profile','firmware_sha256','stack_budget')},indent=2))
