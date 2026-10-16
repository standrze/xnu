#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct FDT-only observation BL33. Never publishes, opens UART or reboots."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import uuid
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/rpi5'))
elf_inspector=importlib.import_module('build_probe')
BASE=0x9000000
PROFILE='pi5-framebuffer-fdt-observation-only-v1'
SOURCES=tuple(ROOT/'loader/rpi5'/s for s in ('probe_entry.S','probe_framebuffer_observe_main.c',
    'access_mmio.S','framebuffer_observation.c','framebuffer_descriptor.c','uart.c','psci.S','fdt.c','fdt_reg.c','ranges.c','memory.S'))
FILES=tuple(ROOT/p for p in ('tools/rpi5/build_framebuffer_observation.py','tools/rpi5/check_framebuffer_observation.py',
    'tools/rpi5/framebuffer_observation_serial.py','tools/rpi5/tests/test_framebuffer_observation.py',
    'tools/rpi5/tests/framebuffer_observation_host.c','tools/rpi5/tests/test_framebuffer_observation_package.py',
    'tools/rpi5/tests/test_framebuffer_observation_serial.py','tools/rpi5/tests/test_framebuffer_observation_guard.py',
    'tools/rpi5/tests/test_framebuffer_descriptor.py','tools/rpi5/tests/test_pcie_fdt.py',
    'loader/rpi5/probe.ld','tools/rpi5/tfa-lld','tools/rpi5/tfa-objcopy','tools/rpi5/loader-toolchain.lock.json'))
FALSE_FIELDS=('physical_execution','installed','xnu_transfer','kernel_embedded','root_embedded','cpu_on_called',
    'mailbox_requests','framebuffer_access','framebuffer_allocation','framebuffer_mapping','drawing','mirror_enabled',
    'ownership_proven','scanout_cache_contract_proven','hardware_recovery_proven','reset_destination_proven')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def deps(p):
    tokens=shlex.split(Path(p).read_text().replace('\\\n',' '))
    if not tokens or not tokens[0].endswith(':'):raise ValueError('Invalid actual dependency document')
    return sorted({str((ROOT/t).resolve()) for t in tokens[1:]})
def imported():
    # Fixed source graph of the actual reused ELF inspector. Other unrelated
    # modules loaded by a caller never expand this package's authority/closure.
    todo=[ROOT/'tools/rpi5/build_probe.py'];found=set()
    while todo:
        path=todo.pop().resolve()
        if str(path) in found:continue
        found.add(str(path))
        for node in ast.walk(ast.parse(path.read_text())):
            names=[a.name for a in node.names] if isinstance(node,ast.Import) else [node.module] if isinstance(node,ast.ImportFrom) and node.module else []
            for name in names:
                candidate=ROOT/'tools/rpi5'/(name+'.py')
                if candidate.is_file():todo.append(candidate)
    return sorted(found)
def tools():
    return dict(clang=subprocess.check_output(['xcrun','--find','clang'],text=True).strip(),
        nm=subprocess.check_output(['xcrun','--find','llvm-nm'],text=True).strip(),
        objdump=subprocess.check_output(['xcrun','--find','llvm-objdump'],text=True).strip(),
        linker=str(ROOT/'tools/rpi5/tfa-lld'),objcopy=str(ROOT/'tools/rpi5/tfa-objcopy'),
        zig=str(ROOT/'build/rpi5/zig-aarch64-macos-0.16.0/zig'))
def commands(out,tag,t):
    rows=[];objects=[]
    for source in SOURCES:
        label=source.stem;obj=out/(label+'.o');objects.append(obj)
        flags=[t['clang'],'--target=aarch64-none-elf','-mcpu=cortex-a76','-mstrict-align','-ffreestanding',
            '-fno-builtin','-fno-stack-protector','-mgeneral-regs-only','-O2','-Wall','-Wextra','-Werror',
            '-ffunction-sections','-fdata-sections',f'-DRPI5_FB_OBSERVE_TAG="{tag}"']
        if source.suffix=='.c':flags+=['-std=c11','-fstack-usage']
        rows.extend([(label+'-scan',[*flags,'-M','-MF',str(out/(label+'.scan.d')),str(source)]),
            (label+'-compile',[*flags,'-c','-MD','-MF',str(out/(label+'.actual.d')),str(source),'-o',str(obj)])])
    rows.extend([('link',[t['linker'],'--gc-sections',f'--defsym=LOADER_BASE={hex(BASE)}','-T',str(ROOT/'loader/rpi5/probe.ld'),
        *map(str,objects),'-o',str(out/'probe.elf')]),('objcopy',[t['objcopy'],'-O','binary',str(out/'probe.elf'),str(out/'probe.bin')]),
        ('symbols',[t['nm'],'--defined-only','--format=posix',str(out/'probe.elf')]),
        ('disassembly',[t['objdump'],'-d',str(out/'probe.elf')])])
    return rows
def stack(out):
    symbols={r.split()[0] for r in (out/'symbols.log').read_text().splitlines() if len(r.split())>=2 and r.split()[1] in ('t','T')}
    frames=[]
    for s in SOURCES:
        if s.suffix!='.c':continue
        for line in (out/(s.stem+'.su')).read_text().splitlines():
            loc,size,kind=line.split('\t')
            if loc.rsplit(':',1)[-1] not in symbols:continue
            if kind!='static' or int(size)<0:raise ValueError('Unbounded stack frame')
            frames.append(dict(location=loc,bytes=int(size),kind=kind))
    total=sum(f['bytes'] for f in frames)
    if not frames or total+512>=16384:raise ValueError('Conservative nonrecursive stack bound rejected '+str(total))
    return frames,dict(conservative_bytes=total,stack_bytes=16384,required_margin=512)
def build():
    out=Path(tempfile.mkdtemp(prefix='framebuffer-observe-',dir=ROOT/'build/rpi5'));tag=uuid.uuid4().hex;t=tools()
    pins={};headers={};scans={};records=[]
    def pin(p):
        p=str(Path(p).resolve());v=sha(p)
        if p in pins and pins[p]!=v:raise ValueError('Changed pinned input '+p)
        pins[p]=v
    for p in (*SOURCES,*FILES,*imported(),*t.values()):pin(p)
    for label,command in commands(out,tag,t):
        r=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=60)
        log=out/(label+'.log');log.write_bytes(r.stdout+r.stderr)
        records.append(dict(label=label,command=command,cwd=str(ROOT),returncode=r.returncode))
        if r.returncode or b'warning:' in r.stderr:raise ValueError('Build failed; retained '+str(log))
        if label.endswith('-scan'):
            name=label.removesuffix('-scan');found=deps(out/(name+'.scan.d'));scans[name]=found
            for p in found:pin(p);headers[p]=pins[str(Path(p).resolve())]
        elif label.endswith('-compile'):
            name=label.removesuffix('-compile')
            if deps(out/(name+'.actual.d'))!=scans[name]:raise ValueError('Header set changed at compile')
            for p in scans[name]:pin(p)
    report=elf_inspector.inspect((out/'probe.elf').read_bytes(),(out/'probe.bin').read_bytes(),BASE)
    frames,budget=stack(out)
    for p,v in pins.items():
        if sha(p)!=v:raise ValueError('Source changed '+p)
    generated={str(p):sha(p) for p in sorted(out.iterdir()) if p.is_file()}
    report.update(profile=PROFILE,tag=tag,image=str(out/'probe.bin'),image_sha256=sha(out/'probe.bin'),
        image_bytes=(out/'probe.bin').stat().st_size,inputs_sha256=pins,headers_sha256=headers,source_scan=scans,
        generated_sha256=generated,commands=records,tool_paths=t,stack_frames=frames,stack_budget=budget,
        watchdog=dict(already_active_required=True,countdown_write_once_seconds=15,software_output_seconds=8,
            reset_route_writes=False,reload_after_arm=False),output_limit_bytes=32768,scope='Same-boot FDT facts only; no scanout or ownership proof',
        **{key:False for key in FALSE_FIELDS})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),image_sha256=report['image_sha256'],
        image_bytes=report['image_bytes'],tag=tag,stack_budget=budget),indent=2));return report
if __name__=='__main__':build()
