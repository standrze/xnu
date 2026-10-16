#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Relink the frozen passive-trace kernel with only three C1-aware AXI cores.

No controller caller, access guard, mapping, watchdog or trace source changes.
The failed physical candidate remains immutable and is the exact object parent.
"""
import argparse
import json
from pathlib import Path
try:
    from . import build_rp1_config_kernel as base
    from . import pcie_axi_reserved_profile as profile
except ImportError:
    import build_rp1_config_kernel as base
    import pcie_axi_reserved_profile as profile

ROOT,audit=base.ROOT,base.audit
BASE=ROOT/'build/rpi5/pcie-id-trace-kernel-20261013-checked'
BASE_SHA='7a4a7ea375d77b19c0d851c0f9a11f78a6591f314f8a01823d0f91e85e42c213'
CORES=('pcie_ubus.c','pcie_qos.c','pcie_clock.c')
TEST=ROOT/'tools/rpi5/tests/test_pcie_axi_trace_kernel.py'
PROFILE='pcie-id-passive-trace-c1-axi-kernel-v1'


def verify(pins):
    for name,digest in pins.items():
        if audit.sha(Path(name))!=digest:raise ValueError('C1 AXI input changed: '+name)


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen passive trace kernel changed')
    old=json.loads((BASE/'manifest.json').read_text())
    pins=old['inputs_sha256']|old['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for p in (Path(__file__).resolve(),TEST,ROOT/'tools/rpi5/pcie_axi_reserved_profile.py',
              ROOT/'tools/rpi5/tests/test_pcie_axi_reserved.py',
              *(ROOT/'tools/rpi5/tests'/name for name in ('pcie_ubus_host.c','pcie_qos_host.c','pcie_clock_host.c'))):
        pins[str(p)]=audit.sha(p)
    verify(pins)
    return old,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Duplicate original link input')
    replacements={}
    for name in CORES:
        selected=[p for p in original if p.name==name+'.o']
        if len(selected)!=1:raise ValueError('Ambiguous original AXI object: '+name)
        replacements[selected[0]]=output/(name+'.o')
    return original,[replacements.get(p,p) for p in original],replacements


def compile_args(old,source):
    command=old['compiles'][1]['command']
    previous=str(ROOT/'loader/rpi5/rp1_config_snapshot_checked.c')
    if command.count(previous)!=1 or command[-2]!='-o':raise ValueError('Frozen core compiler changed')
    return [command[0],'-iquote',str(ROOT/'loader/rpi5'),
            *(str(source) if a==previous else a for a in command[1:-2])]


def build(output):
    old,pins=inputs();output=output.resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh distinct build output required')
    output.mkdir(exist_ok=False);sources=profile.emit(output/'overlay')
    for p in (output/'overlay').iterdir():pins[str(p)]=audit.sha(p)
    commands=[];compiles=[];cwd=audit.OBJ/'pexpert/DEVELOPMENT'
    def execute(args,name,where=ROOT,allow_warnings=False):
        row=audit.execute(list(map(str,args)),where,output/(name+'.log'));commands.append(row)
        if row['returncode'] or (row['warning_count'] and not allow_warnings):
            raise ValueError('AXI trace operation failed: '+row['log'])
        return row
    for source in sources:
        args=compile_args(old,source);dep=output/(source.name+'.d');actual=output/(source.name+'.actual.d')
        execute([a for a in args if a!='-c']+['-M','-MF',dep],source.name+'-deps',cwd)
        deps=audit.dependency_paths(dep,cwd)
        for p in deps:
            digest=audit.sha(p)
            if str(p) in pins and pins[str(p)]!=digest:raise ValueError('AXI dependency conflict: '+str(p))
            pins[str(p)]=digest
        row=execute(args+['-MD','-MF',actual,'-o',output/(source.name+'.o')],source.name+'-compile',cwd)
        compiles.append(row)
        if deps!=audit.dependency_paths(actual,cwd):raise ValueError('Actual AXI dependency closure changed')
        execute([a for a in args if a!='-c']+['-S','-o',output/(source.name+'.s')],source.name+'-assembly',cwd)
    original,current,replacements=objects(output)
    filelist=output/'kernel.rp1-config.filelist';filelist.write_text(''.join(str(p)+'\n' for p in current))
    kernel=output/'kernel.rp1-config';linkmap=output/'kernel.map';unstripped=output/'kernel.unstripped'
    link=next(r['command'] for r in old['commands'] if r['log'].endswith('/link.log'))
    paths={str(BASE/'kernel.rp1-config.filelist'):str(filelist),
        str(BASE/'kernel.unstripped'):str(unstripped),'-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(linkmap)}
    if any(link.count(p)!=1 for p in paths):raise ValueError('Frozen trace link command changed')
    row=execute([paths.get(a,a) for a in link],'link',allow_warnings=True)
    warnings=[line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings!=old['baseline_linker_warnings']:raise ValueError('New AXI linker warnings')
    execute(['xcrun','strip','-S',unstripped,'-o',kernel],'strip')
    listing=audit.read_command(['xcrun','nm','-nm',kernel]);(output/'kernel.symbols').write_text(listing+'\n')
    if audit.read_command(['xcrun','nm','-ju',kernel]):raise ValueError('Undefined corrected trace kernel symbol')
    mapped=linkmap.read_text(errors='surrogateescape')
    if any(str(p) in mapped for p in replacements) or any(str(p) not in mapped for p in current):
        raise ValueError('Exactly three actual AXI replacements not proven')
    linked=base.full.linked_audit(kernel.read_bytes(),listing,mapped);names=base.full.symbols(listing)
    required=old['required_implementations']+old['id_required_implementations']+[
        '_rpi5_pcie_ubus_configure','_rpi5_pcie_qos_configure','_rpi5_pcie_clock_prepare','_rpi5_pcie_clock_finish']
    for name in set(required):
        if len(names.get(name,[]))!=1:raise ValueError('Missing/ambiguous executable implementation: '+name)
        address=names[name][0]
        if not any(s['initprot']&4 and s['vmaddr']<=address<s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Non-executable implementation: '+name)
    raw=kernel.read_bytes();oldraw=(BASE/'kernel.rp1-config').read_bytes()
    start=oldraw.index(b'RPI5XNU:PCIEID:END OK=');end=oldraw.index(b'\0',start)+1
    if raw.count(oldraw[start:end])!=1:raise ValueError('Passive END format changed')
    verify(pins)
    # Preserve historical policy fields, but replace all own link/build claims.
    result=dict(old)
    result.update(profile=PROFILE,parent_manifest_sha256=BASE_SHA,
        kernel=str(kernel),kernel_sha256=audit.sha(kernel),kernel_bytes=kernel.stat().st_size,
        inputs_sha256=pins,generated_sha256={str(p):audit.sha(p) for p in output.rglob('*') if p.is_file()},
        commands=commands,compiles=compiles,link=linked,baseline_linker_warnings=warnings,
        axi_object_replacements={str(p):str(q) for p,q in replacements.items()},
        axi_supported_fix_fields=[0x3800,0x2800,0],axi_fallback_max_outstanding=15,
        axi_unrelated_bits_preserved=True,axi_fallback_readback_exact=True,
        unchanged_original_objects=len(original)-3,controller_caller_unchanged=True,
        firmware_guard_unchanged=True,watchdog_unchanged=True,passive_trace_unchanged=True,
        complete_kernel_link_proven=True,installed=False,pi_executed=False,ethernet_proven=False,
        candidate_only=True,hardware_failure_receipt='build/rpi5/rp1-trace-serial-20261013')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',required=True,type=Path)
    result=build(p.parse_args().output_dir)
    print(json.dumps({k:result[k] for k in ('kernel','kernel_sha256','kernel_bytes','profile')}))
