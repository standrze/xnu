# SPDX-License-Identifier: BSD-2-Clause
"""Byte-only closure of the ring-only retry build recipe."""
import hashlib
import json
from pathlib import Path
import re
import struct
from tools.rpi5 import build_gem_cpu_ring_retry_trial as b

PROFILE=b.PROFILE
TEST=b.ROOT/'tools/rpi5/tests/test_gem_cpu_ring_retry_trial.py'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def same(a,c):return json.dumps(a,sort_keys=True,separators=(',',':'),allow_nan=False)==json.dumps(c,sort_keys=True,separators=(',',':'),allow_nan=False)
def identity(package,m):
    package=Path(package).resolve()
    if package.parent!=b.ROOT/'build/rpi5' or not package.name.startswith('gem-cpu-ring-retry-trial-') or m.get('profile')!=PROFILE:
        raise ValueError('Exact distinct retry trial required')
    if not re.fullmatch('[a-f0-9]{32}',m.get('tag','')):raise ValueError('Exact compiled tag required')
    return package
def command_bindings(package,m):
    package=identity(package,m);rows,scans=b.plan(package,m['tag'])
    expected={label:dict(command=args,cwd=cwd) for label,args,cwd in rows};observed={}
    if len(expected)!=len(rows):raise ValueError('Duplicate canonical recipe')
    for row in m['commands']:
        label=Path(row['log']).stem
        if label in observed or row['log']!=str(package/(label+'.log')) or type(row['returncode']) is not int or row['returncode']!=0 or sha(row['log'])!=row['log_sha256']:
            raise ValueError('Operation receipt incomplete/ambiguous')
        observed[label]=dict(command=row['command'],cwd=row['cwd'])
    if not same(observed,expected) or set(m['compiler_scans'])!=set(scans):raise ValueError('Complete commands/scans differ')
    return scans
def source_outputs(package,m):
    package=identity(package,m)
    for path in [*b.sources(),Path(__file__).resolve(),TEST]:
        if m['inputs_sha256'].get(str(path))!=sha(path):raise ValueError('Canonical source omitted/changed: '+str(path))
    derived=b.derived_sources()
    for name,data in derived.items():
        if (package/name).read_bytes()!=data:raise ValueError('Emitted source differs: '+name)
    objects,replaced,extra,added=b.kernel_objects(package)
    if (package/'kernel.filelist').read_bytes()!=('\n'.join(objects)+'\n').encode():raise ValueError('Linked object list differs')
    if not same(m['replaced_objects'],replaced) or not same(m['inherited_extra_objects'],extra) or not same(m['added_objects'],added):raise ValueError('Object delta differs')
    return len(derived)
def payload(package):
    package=Path(package).resolve();raw=(b.base.BASE/'payload.bin').read_bytes();off,n=struct.unpack_from('<QQ',raw,136)
    expected=b.base.old.payload_container.encode((package/'kernel.cpu-rings').read_bytes(),raw[off:off+n])
    if (package/'payload.bin').read_bytes()!=expected:raise ValueError('Payload/kernel/root differ')
    expected_asm='.section .payload,"a"\n.balign 64\n.incbin "'+str(package/'payload.bin')+'"\n'
    if (package/'payload.S').read_text()!=expected_asm:raise ValueError('Payload assembly differs')
def dependencies(package,m,scans):
    package=Path(package).resolve();headers={};pins=m['inputs_sha256']
    for label,record in scans.items():
        before=b.base.old.display.dependencies(package/(label+'.scan.d'),record['cwd'])
        after=b.base.old.display.dependencies(package/(label+'.d'),record['cwd'])
        if before!=after or sorted(before)!=m['compiler_scans'][label] or record['source'] not in before:raise ValueError('Dependency receipt differs: '+label)
        for name in before:
            if pins.get(name)!=sha(name):raise ValueError('Compiler input omitted/changed')
            headers[name]=pins[name]
    if not same(headers,m['actual_headers_sha256']):raise ValueError('Header closure differs')
    return len(headers)
def inspect(package,m):
    scans=command_bindings(package,m);members=dependencies(package,m,scans);outputs=source_outputs(package,m);payload(package)
    return dict(profile=PROFILE,canonical_commands=len(m['commands']),canonical_compile_labels=len(scans),
        actual_header_members=members,canonical_outputs=outputs,compiler_replayed=False,hardware_admission=False,
        active_dma_authority=False,packet_spans=0)
