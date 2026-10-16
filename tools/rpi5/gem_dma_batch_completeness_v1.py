# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only completeness for the distinct real CPU-owned batch trial.

No compiler, historical semantic replay or hardware. The outer checker must
independently pin the retained manifest, validate its byte closure and inspect
actual linked binaries. This does not authorize queue publication or DMA.
"""
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.rpi5 import build_gem_dma_batch_trial as b
PROFILE='bcm2712-gem-real-cpu-owned-batch-trial-v1'
TEST=b.ROOT/'tools/rpi5/tests/test_gem_dma_batch_completeness_v1.py'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def same(a,c):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(c,sort_keys=True,separators=(',',':'),allow_nan=False)
def identity(package,m):
    package=Path(package).resolve()
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-dma-batch-trial-') or m.get('profile')!=PROFILE or b.PROFILE!=PROFILE:
        raise ValueError('Exact real CPU-owned batch profile required')
    if not isinstance(m.get('tag'),str) or not re.fullmatch('[a-f0-9]{32}',m['tag']):raise ValueError('Exact compiled tag required')
    return package
def command_bindings(package,m):
    package=identity(package,m);rows,scans=b.plan(package,m['tag'])
    expected={label:dict(command=args,cwd=cwd) for label,args,cwd in rows}
    if len(expected)!=len(rows):raise ValueError('Duplicate canonical recipe')
    observed={}
    for row in m['commands']:
        label=Path(row['log']).stem
        if label in observed or row['log']!=str(package/(label+'.log')) or not same(row['returncode'],0) or sha(row['log'])!=row['log_sha256']:
            raise ValueError('Operation receipt incomplete/ambiguous')
        observed[label]=dict(command=row['command'],cwd=row['cwd'])
    if not same(observed,expected):raise ValueError('Complete exact commands/cwds differ')
    if set(m['compiler_scans'])!=set(scans):raise ValueError('Complete compiler-label set differs')
    return scans
def source_outputs(package,m,require_pins=True):
    package=identity(package,m)
    if require_pins:
        for path in [*b.sources(),Path(__file__).resolve(),TEST]:
            if m['inputs_sha256'].get(str(path))!=sha(path):raise ValueError('Canonical recipe source omitted/changed: '+str(path))
    derived=b.derived_sources()
    if not derived or any(not isinstance(name,str) or not isinstance(data,bytes) for name,data in derived.items()):raise ValueError('Invalid source recipe')
    for name,data in derived.items():
        if (package/name).read_bytes()!=data:raise ValueError('Actual emitted source differs: '+name)
    objects,replaced,extra,added=b.kernel_objects(package)
    if (package/'kernel.filelist').read_bytes()!=('\n'.join(objects)+'\n').encode():raise ValueError('Complete actual linked object list differs')
    if not same(m['replaced_objects'],replaced) or not same(m['inherited_extra_objects'],extra) or not same(m['added_objects'],added):raise ValueError('Exact logical object delta differs')
    return len(derived)
def payload(package):
    package=Path(package).resolve();original=(b.BASE/'payload.bin').read_bytes()
    offset,count=struct.unpack_from('<QQ',original,136);root=original[offset:offset+count]
    expected=b.old.payload_container.encode((package/'kernel.cpu-rings').read_bytes(),root)
    if (package/'payload.bin').read_bytes()!=expected:raise ValueError('Whole payload/kernel/root/padding differs')
    assembly='.section .payload,"a"\n.balign 64\n.incbin "'+str(package/'payload.bin')+'"\n'
    if (package/'payload.S').read_bytes()!=assembly.encode():raise ValueError('Exact embedded payload assembly differs')
def dependencies(package,m,scans):
    package=Path(package).resolve();headers={};pins=m['inputs_sha256']
    for label,record in scans.items():
        before=b.old.display.dependencies(package/(label+'.scan.d'),record['cwd'])
        after=b.old.display.dependencies(package/(label+'.d'),record['cwd'])
        if before!=after or sorted(before)!=m['compiler_scans'][label] or record['source'] not in before:
            raise ValueError('Exact actual dependency receipt differs: '+label)
        for name in before:
            if pins.get(name)!=sha(name):raise ValueError('Required actual compiler input omitted/changed')
            headers[name]=pins[name]
    if not same(headers,m['actual_headers_sha256']):raise ValueError('Complete actual header map differs')
    return len(headers)
def inspect(package,m):
    scans=command_bindings(package,m);members=dependencies(package,m,scans)
    outputs=source_outputs(package,m);payload(package)
    return dict(profile=PROFILE,canonical_commands=len(m['commands']),canonical_compile_labels=len(scans),
                actual_header_members=members,canonical_outputs=outputs,compiler_replayed=False,
                hardware_admission=False,active_dma_authority=False)
