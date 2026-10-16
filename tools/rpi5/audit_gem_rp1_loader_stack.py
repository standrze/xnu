#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Separate actual RP1 Device-declaration loader stack phase, no hardware.

This phase completes before display/seed/finalization. It never sums those
sequential phases as if they were nested, nor widens the original32KiB stack.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from tools.rpi5 import build_gem_dma_batch_trial as b
from tools.rpi5.audit_reservation_kernel_stack import frames
UNITS=('fdt','fdt_reg','pcie_fdt','memory_type')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def elf_code(path):
    raw=Path(path).read_bytes()
    if len(raw)<64 or raw[:6]!=b'\x7fELF\x02\x01' or struct.unpack_from('<H',raw,18)[0]!=183:raise ValueError('Actual A76 ELF64 required')
    offset=struct.unpack_from('<Q',raw,40)[0];size,count,names=struct.unpack_from('<HHH',raw,58)
    if size!=64 or not count or names>=count or offset+size*count>len(raw):raise ValueError('Invalid sections')
    entries=[struct.unpack_from('<IIQQQQIIQQ',raw,offset+i*size) for i in range(count)]
    n=entries[names];strings=raw[n[4]:n[4]+n[5]];result=[]
    for section in entries:
        name,kind,flags,_,where,length,*_=section
        if flags&4:
            end=strings.find(b'\0',name)
            if name>=len(strings) or end<0 or where+length>len(raw):raise ValueError('Invalid instruction section')
            result.append((strings[name:end],raw[where:where+length]))
    if not result:raise ValueError('No executable sections')
    return result
def inspect(package,measurement):
    package=Path(package).resolve();measurement=Path(measurement).resolve()
    m=json.loads((package/'manifest.json').read_bytes());r=json.loads(measurement.read_bytes())
    if m['profile']!=b.PROFILE or r['package_manifest_sha256']!=sha(package/'manifest.json'):raise ValueError('Exact profile/receipt required')
    for key in ('inputs_sha256','generated_sha256'):
        for path,pin in r[key].items():
            if sha(path)!=pin:raise ValueError('Actual loader receipt drift')
    tables=r['frames']
    def get(table,name):
        row=tables[table][name]
        if row['kind']!='static' or row['bytes']<0:raise ValueError('Unbounded loader frame')
        return row['bytes']
    # Conservative sum of every emitted PCIe parser/register translator and
    # memory-type frame. These components are nonrecursive; sequential helper
    # calls are intentionally overcounted. FDT includes all emitted routines,
    # including phandle/cpus/reservation parsers not all used on this phase.
    core=0
    for unit in UNITS:
        core+=sum(get(unit,name) for name in tables[unit])
    caller=sum(get('loader-probe_main',name) for name in ('probe_el1_main','runtime_cpus','board_tree_diagnostic'))
    rp1=get('loader-rp1_device_handoff','rpi5_rp1_device_handoff')
    bound=caller+rp1+core
    symbols=m['loader_symbols'];stack=symbols['__stack_top']-symbols['__bss_end']
    if stack!=32768 or bound+512>=stack:raise ValueError('RP1 declaration phase exceeds original loader stack')
    return dict(profile='pi5-rp1-device-declaration-loader-stack-v1',
        package_manifest_sha256=sha(package/'manifest.json'),measurement_sha256=sha(measurement),
        caller_bytes=caller,rp1_bytes=rp1,nonrecursive_helpers_overcounted_bytes=core,
        maximum_conservative_bytes=bound,stack_bytes=stack,minimum_remaining_bytes=stack-bound,
        original_loader_objects_code_unchanged=True,hardware=False,
        record_finalization_nested=False,display_allocator_nested=False,
        scope='Successful RP1 Device-declaration phase only; no exception-stack claim')
def measure(package,output):
    package=Path(package).resolve();output=Path(output).resolve()
    if output.parent!=b.ROOT/'build/rpi5' or output.exists():raise ValueError('Distinct new audit path required')
    output.mkdir();m=json.loads((package/'manifest.json').read_bytes())
    if m['profile']!=b.PROFILE:raise ValueError('Exact real batch package required')
    pins={str(package/'manifest.json'):sha(package/'manifest.json'),str(Path(__file__).resolve()):sha(__file__)};tables={};commands=[]
    link=next(r['command'] for r in m['commands'] if r['log'].endswith('/loader-link.log'))
    original=next(r for r in m['commands'] if r['log'].endswith('/loader-rp1_device_handoff-compile.log'))
    for unit in UNITS:
        objects=[Path(p) for p in link if Path(p).name==unit+'.o']
        if len(objects)!=1:raise ValueError('Ambiguous exact loader owner: '+unit)
        actual=objects[0];pins[str(actual)]=sha(actual)
        source=b.ROOT/'loader/rpi5'/(unit+'.c');cmd=list(original['command'])
        cmd[cmd.index(str(b.ROOT/'loader/rpi5/rp1_device_handoff.c'))]=str(source)
        cmd[cmd.index('-o')+1]=str(output/(unit+'.o'));cmd[cmd.index('-MF')+1]=str(output/(unit+'.d'))
        if '-fstack-usage' not in cmd:cmd.append('-fstack-usage')
        result=subprocess.run(cmd,cwd=original['cwd'],capture_output=True,timeout=60)
        (output/(unit+'.log')).write_bytes(result.stdout+result.stderr)
        if result.returncode or result.stderr:raise ValueError('Exact loader measurement compile failed: '+unit)
        if elf_code(output/(unit+'.o'))!=elf_code(actual):raise ValueError('Actual reused loader instructions changed: '+unit)
        for p in b.old.display.dependencies(output/(unit+'.d'),original['cwd']):pins[p]=sha(p)
        commands.append(dict(command=cmd,cwd=original['cwd'],returncode=result.returncode,actual_original=str(actual)))
        tables[unit]=frames(output/(unit+'.su'))
    for unit in ('loader-probe_main','loader-rp1_device_handoff'):
        path=package/(unit+'.su');pins[str(path)]=sha(path)
        if m['generated_sha256'].get(str(path))!=pins[str(path)]:raise ValueError('Actual caller stack closure differs')
        tables[unit]=frames(path)
    for path,pin in pins.items():
        if sha(path)!=pin:raise ValueError('Loader measurement source drift')
    r=dict(profile='pi5-rp1-device-loader-stack-measurements-v1',package_manifest_sha256=sha(package/'manifest.json'),
        commands=commands,frames=tables,inputs_sha256=pins,generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    measurement=output/'measurements.json';measurement.write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
    result=inspect(package,measurement);(output/'audit.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();r=measure(args.package,args.output)
    print(json.dumps(dict(audit_sha256=sha(args.output/'audit.json'),bytes=r['maximum_conservative_bytes'],remaining=r['minimum_remaining_bytes'])))
