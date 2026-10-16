#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct corrected-AXI child: elapsed settling plus passive link telemetry.

Only the platform transport and link C object change. Retain all three accepted
C1-aware AXI cores, exact firmware guards and the original watchdog deadlines.
"""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_pcie_axi_trace_kernel as previous
    from . import pcie_link_elapsed_profile as profile
except ImportError:
    import build_pcie_axi_trace_kernel as previous
    import pcie_link_elapsed_profile as profile

ROOT,audit,base=previous.ROOT,previous.audit,previous.base
BASE=ROOT/'build/rpi5/pcie-axi-trace-kernel-20261013-v2'
BASE_SHA='fa38950c85264d4a635f1b20b511071f7af9d564f53c9600756312dc6924d644'
PROFILE='pcie-id-link-elapsed-trace-kernel-v1'
TEST=ROOT/'tools/rpi5/tests/test_pcie_link_elapsed_kernel.py'
verify=previous.verify


def inputs():
    if audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen physical AXI trial kernel changed')
    parent=json.loads((BASE/'manifest.json').read_text())
    pins=parent['inputs_sha256']|parent['generated_sha256']|{str(BASE/'manifest.json'):BASE_SHA}
    for p in (Path(__file__).resolve(),TEST,ROOT/'tools/rpi5/pcie_link_elapsed_profile.py',
              ROOT/'tools/rpi5/tests/test_pcie_link_elapsed.py',ROOT/'tools/rpi5/tests/pcie_link_host.c'):
        pins[str(p)]=audit.sha(p)
    verify(pins)
    trace=json.loads((previous.BASE/'manifest.json').read_text())
    return parent,trace,pins


def objects(output):
    original=[Path(p) for p in (BASE/'kernel.rp1-config.filelist').read_text().splitlines()]
    if len(original)!=len(set(original)):raise ValueError('Duplicate parent object')
    replace={}
    for name in ('BCM2712PCIePHYTransport.cpp','pcie_link.c'):
        found=[p for p in original if p.name==name+'.o']
        if len(found)!=1:raise ValueError('Ambiguous link elapsed replacement')
        replace[found[0]]=output/(name+'.o')
    return original,[replace.get(p,p) for p in original],replace


def compile_args(trace,source):
    if source.suffix=='.cpp':
        command=trace['compiles'][0]['command'];old=str(profile.FROZEN/source.name)
    else:
        command=trace['compiles'][1]['command'];old=str(ROOT/'loader/rpi5/rp1_config_snapshot_checked.c')
    if command.count(old)!=1 or command[-2]!='-o':raise ValueError('Exact parent compile command changed')
    return [command[0],'-iquote',str(source.parent),'-iquote',str(ROOT/'loader/rpi5'),
            *(str(source) if a==old else a for a in command[1:-2])]


def class_layout_audit(current,transport,mapped):
    owners=re.findall(r'^\[(\d+)\] '+re.escape(str(transport))+r'$',mapped,re.M)
    if len(owners)!=1:raise ValueError('One new transport link owner required')
    rows=[line for line in mapped.splitlines() if line.startswith('0x') and 'BCM2712PCIePHYTransport' in line]
    if len(rows)<25 or any('['+owners[0]+']' not in line for line in rows):
        raise ValueError('Old object still emits class layout-dependent code/data')
    # No unchanged object imports its methods, constructors, allocator, vtable,
    # or metadata. The boot hook uses the separately named C entry point only.
    unchanged=[p for p in current if p!=transport]
    imports=audit.read_command(['xcrun','nm','-u',*unchanged])
    if 'BCM2712PCIePHYTransport' in imports:raise ValueError('Old object consumes transport class ABI')
    return dict(class_link_owner=int(owners[0]),class_symbol_rows=len(rows),
        other_objects_checked=len(unchanged),other_class_imports=0,
        constructors_allocators_vtable_and_methods_recompiled=True)


def build(output):
    parent,trace,pins=inputs();output=output.resolve()
    if output.parent!=ROOT/'build/rpi5':raise ValueError('Fresh separate build output required')
    output.mkdir(exist_ok=False);sources=profile.emit(output/'overlay')
    for p in (output/'overlay').iterdir():pins[str(p)]=audit.sha(p)
    commands=[];compiles=[]
    def execute(args,name,where=ROOT,allow_warnings=False):
        row=audit.execute(list(map(str,args)),where,output/(name+'.log'));commands.append(row)
        if row['returncode'] or (row['warning_count'] and not allow_warnings):
            raise ValueError('Link elapsed operation failed: '+row['log'])
        return row
    for source in sources:
        cwd=audit.OBJ/('iokit/DEVELOPMENT' if source.suffix=='.cpp' else 'pexpert/DEVELOPMENT')
        args=compile_args(trace,source);dep=output/(source.name+'.d');actual=output/(source.name+'.actual.d')
        execute([a for a in args if a!='-c']+['-M','-MF',dep],source.name+'-deps',cwd)
        deps=audit.dependency_paths(dep,cwd)
        for p in deps:
            digest=audit.sha(p)
            if str(p) in pins and pins[str(p)]!=digest:raise ValueError('Link elapsed dependency conflict: '+str(p))
            pins[str(p)]=digest
        row=execute(args+['-MD','-MF',actual,'-o',output/(source.name+'.o')],source.name+'-compile',cwd)
        compiles.append(row)
        if deps!=audit.dependency_paths(actual,cwd):raise ValueError('Actual dependency closure changed')
        execute([a for a in args if a!='-c']+['-S','-o',output/(source.name+'.s')],source.name+'-assembly',cwd)
    original,current,replacements=objects(output)
    filelist=output/'kernel.rp1-config.filelist';filelist.write_text(''.join(str(p)+'\n' for p in current))
    kernel=output/'kernel.rp1-config';linkmap=output/'kernel.map';unstripped=output/'kernel.unstripped'
    link=next(r['command'] for r in parent['commands'] if r['log'].endswith('/link.log'))
    paths={str(BASE/'kernel.rp1-config.filelist'):str(filelist),str(BASE/'kernel.unstripped'):str(unstripped),
           '-Wl,-map,'+str(BASE/'kernel.map'):'-Wl,-map,'+str(linkmap)}
    if any(link.count(p)!=1 for p in paths):raise ValueError('Exact parent link command changed')
    row=execute([paths.get(a,a) for a in link],'link',allow_warnings=True)
    warnings=[line for line in Path(row['log']).read_text().splitlines() if 'warning:' in line]
    if warnings!=parent['baseline_linker_warnings']:raise ValueError('New elapsed kernel link warnings')
    execute(['xcrun','strip','-S',unstripped,'-o',kernel],'strip')
    listing=audit.read_command(['xcrun','nm','-nm',kernel]);(output/'kernel.symbols').write_text(listing+'\n')
    if audit.read_command(['xcrun','nm','-ju',kernel]):raise ValueError('Undefined elapsed kernel symbol')
    mapped=linkmap.read_text(errors='surrogateescape')
    if any(str(p) in mapped for p in replacements) or any(str(p) not in mapped for p in current):
        raise ValueError('Exactly two link/transport replacements not proven')
    layout=class_layout_audit(current,output/'BCM2712PCIePHYTransport.cpp.o',mapped)
    linked=base.full.linked_audit(kernel.read_bytes(),listing,mapped);symbols=base.full.symbols(listing)
    required=set(parent['required_implementations']+parent['id_required_implementations']+[
        '_rpi5_pcie_link_train','_rpi5_pcie_link_train_elapsed_trace'])
    for name in required:
        addresses=symbols.get(name,[])
        if len(addresses)!=1:raise ValueError('Missing/ambiguous implementation: '+name)
        if not any(s['initprot']&4 and s['vmaddr']<=addresses[0]<s['vmaddr']+s['filesize'] for s in linked['macho']['segments']):
            raise ValueError('Non-executable implementation: '+name)
    if kernel.read_bytes().count(profile.FIELDS.encode())!=1:raise ValueError('Exact linked timing trace missing')
    verify(pins)
    result=dict(parent)
    result.update(profile=PROFILE,parent_manifest_sha256=BASE_SHA,kernel=str(kernel),
        kernel_sha256=audit.sha(kernel),kernel_bytes=kernel.stat().st_size,inputs_sha256=pins,
        generated_sha256={str(p):audit.sha(p) for p in output.rglob('*') if p.is_file()},
        commands=commands,compiles=compiles,link=linked,baseline_linker_warnings=warnings,
        elapsed_object_replacements={str(p):str(q) for p,q in replacements.items()},
        transport_class_layout=layout,
        unchanged_parent_objects=len(original)-2,axi_objects_unchanged=True,
        controller_caller_unchanged=False,passive_trace_unchanged=False,
        link_trace_fields=profile.FIELDS,link_trace_call_steps={1:'guard-before',2:'init',3:'train',4:'guard-after',5:'complete'},
        link_trace_core_steps={1:'entry',2:'profile-and-release',3:'reset-start-time',4:'reset-delay',
            5:'reset-end-time',6:'reset-duration-check',7:'released-lifecycle',8:'poll-start-time',
            9:'poll-status',10:'poll-time',11:'poll-delay',12:'post-delay-time',13:'negotiated-final-profile',14:'complete'},
        delay_accounts_guard_time=True,delay_max_chunk_us=1000,delay_max_chunks=100,
        reset_min_us=100000,reset_max_us=110000,poll_max_us=100000,
        trace_adds_mmio=False,trace_changes_permissions=False,trace_changes_deadlines=False,
        firmware_guard_unchanged=True,watchdog_unchanged=True,complete_kernel_link_proven=True,
        installed=False,pi_executed=False,ethernet_proven=False,candidate_only=True,
        hardware_failure_receipt='build/rpi5/rp1-axi-serial-20261013')
    (output/'manifest.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,required=True)
    r=build(p.parse_args().output_dir)
    print(json.dumps({k:r[k] for k in ('profile','kernel','kernel_sha256','kernel_bytes')}))
