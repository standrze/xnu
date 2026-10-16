#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Bind pthread startup semantics to actual linked Pi objects, offline only.

Recompilation verifies selected implementation bytes and relocations, not just
the presence of source strings. Kernel globals/feature decisions are decoded
from the final kernel. This does not execute registration or qualify entropy.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
KERNEL=ROOT/'build/rpi5/root96-ready-delay-kernel-20261013-final'
KERNEL_SHA='c00bc5250b5fc3c1b6b71da530a22eafcdaa61bd3d554511ceca60214b1c4336'
TREE=ROOT/'build/rpi5-xcode27/fresh-435uage7/obj/DEVELOPMENT_ARM64_BCM2712'
PROVIDER=ROOT/'build/rpi5-xcode27/pthread-provider/20148551e88bda2dbffd'
USER=ROOT/'build/rpi5/apple-libpthread-main-candidate-20261013'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MachO:
    def __init__(self,path):
        self.raw=Path(path).read_bytes();self.sections=[];self.symbols=[];self.commands=[]
        magic,_,_,_,ncmds,_,_,_=struct.unpack_from('<8I',self.raw)
        if magic!=0xfeedfacf:raise ValueError('Expected little-endian Mach-O64')
        cursor=32;table=None
        for _ in range(ncmds):
            cmd,size=struct.unpack_from('<II',self.raw,cursor);self.commands.append(cmd)
            if cmd==0x19:
                nsects=struct.unpack_from('<I',self.raw,cursor+64)[0]
                for i in range(nsects):
                    rec=struct.unpack_from('<16s16sQQ8I',self.raw,cursor+72+80*i)
                    self.sections.append(dict(name=rec[1].split(b'\0')[0].decode()+','+rec[0].split(b'\0')[0].decode(),
                        address=rec[2],size=rec[3],offset=rec[4],reloff=rec[6],nreloc=rec[7]))
            elif cmd==2:table=struct.unpack_from('<4I',self.raw,cursor+8)
            cursor+=size
        if table:
            so,ns,st,ss=table;strings=self.raw[st:st+ss]
            for i in range(ns):
                idx,kind,sect,desc,value=struct.unpack_from('<IBBHQ',self.raw,so+16*i)
                name=strings[idx:].split(b'\0')[0].decode()
                self.symbols.append(dict(name=name,type=kind,section=sect,address=value))
        self.names={s['name']:s for s in self.symbols if s['section']}

    def at(self,address,count):
        section=next(s for s in self.sections if s['address']<=address and address+count<=s['address']+s['size'])
        offset=section['offset']+address-section['address']
        return self.raw[offset:offset+count]

    def function(self,name):
        symbol=self.names[name];section=self.sections[symbol['section']-1];begin=symbol['address']
        end=min([s['address'] for s in self.symbols if s['section']==symbol['section'] and
                 s['address']>begin and s['type']&0xe==0xe]+[section['address']+section['size']])
        relocs=[]
        for i in range(section['nreloc']):
            addr,info=struct.unpack_from('<II',self.raw,section['reloff']+8*i)
            if begin-section['address']<=addr<end-section['address']:
                index=info&0xffffff;external=bool(info&(1<<27));kind=info>>28
                # ADDEND carries a signed immediate, not a symbol-table index.
                target=index if kind==10 else (self.symbols[index]['name'] if external else self.sections[index-1]['name'])
                relocs.append((addr-(begin-section['address']),info>>24,target))
        body=self.at(begin,end-begin)
        return dict(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),relocations=relocs)


def build():
    receipt=KERNEL/'manifest.json';kernel=json.loads(receipt.read_text());binary=Path(kernel['kernel'])
    if sha(binary)!=KERNEL_SHA or kernel['kernel_sha256']!=KERNEL_SHA:raise ValueError('Actual Pi kernel drift')
    dbpath=TREE/'compile_commands.json';db=json.loads(dbpath.read_text())
    provider_receipt=PROVIDER/'manifest.json';provider=json.loads(provider_receipt.read_text())
    pins={str(receipt):sha(receipt),str(binary):KERNEL_SHA,str(dbpath):sha(dbpath),
          str(provider_receipt):sha(provider_receipt),str(Path(__file__).resolve()):sha(__file__)}
    filelist=KERNEL/'kernel.ready.filelist';pins[str(filelist)]=sha(filelist)
    linked=set(filelist.read_text().splitlines())
    link_commands=[c['command'] for c in kernel['commands'] if '-filelist' in c['command']]
    if len(link_commands)!=1 or link_commands[0][link_commands[0].index('-filelist')+1]!=str(filelist):
        raise ValueError('Actual final link command/filelist mismatch')
    linked.update(p for p in link_commands[0] if p.endswith('.o'))
    out=Path(tempfile.mkdtemp(prefix='apple-pthread-kernel-contract-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers,comparisons=[],{},[]
    def run(args,label,cwd=ROOT):
        args=list(map(str,args));p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=90)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,cwd=str(cwd),returncode=p.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode:raise ValueError(label+': '+p.stderr[-4000:])
        return p
    def deps(raw,cwd):
        names=shlex.split(raw.replace('\\\n',' ').partition(':')[2])
        return {str((Path(cwd)/p).resolve()):sha((Path(cwd)/p).resolve()) for p in names}
    selected={
        'kern_exec.c':('_exec_add_apple_strings','_exec_add_entropy_key'),
        'mach_loader.c':('_load_unixthread',),
        'pthread_shims.c':('_bsdthread_register',),
        'machine_routines.c':('_user_cont_hwclock_allowed','_user_timebase_type'),
    }
    for filename,names in selected.items():
        # arm64, not the independent i386 machine_routines source.
        records=[c for c in db if Path(c['file']).name==filename and '/i386/' not in c['file']]
        if len(records)!=1:raise ValueError('Compile command is not unique: '+filename)
        record=records[0];original=Path(record['directory'])/record['output']
        if str(original) not in linked or sha(original)!=kernel['inputs_sha256'].get(str(original)):
            raise ValueError('Required object not bound to final kernel: '+str(original))
        pins[str(original)]=sha(original);pins[record['file']]=sha(record['file'])
        flags=list(record['arguments']);index=flags.index('-o');del flags[index:index+2];flags.remove('-c')
        before=deps(run(flags+['-M'],filename+'-deps',record['directory']).stdout,record['directory'])
        copied=out/(filename+'.o');dep=out/(filename+'.d')
        run(flags+['-MD','-MF',dep,'-c','-o',copied],filename+'-recompile',record['directory'])
        actual=deps(dep.read_text(),record['directory'])
        if before!=actual:raise ValueError('Actual consumed dependency mismatch')
        headers.update(actual)
        old,new=MachO(original),MachO(copied)
        for name in names:
            prior,current=old.function(name),new.function(name)
            if prior!=current:raise ValueError('Current source no longer reproduces linked function: '+name)
            comparisons.append(dict(name=name,object=str(original),recompiled=str(copied),source=record['file'],**prior))
    provider_object=Path(provider['object'])
    if str(provider_object) not in linked or sha(provider_object)!=kernel['inputs_sha256'].get(str(provider_object)):
        raise ValueError('Kernel provider not actual linked object')
    pins[str(provider_object)]=sha(provider_object)
    for record in provider['commands']:
        source=record['arguments'][record['arguments'].index('-xc')+1]
        if sha(source)!=record['source_sha256']:raise ValueError('Original provider source drift')
        pins[source]=record['source_sha256']
    actual=MachO(binary)
    table=actual.names['_pthread_internal_functions']['address']
    version=struct.unpack('<I',actual.at(table,4))[0]
    registration=struct.unpack('<Q',actual.at(table+0x58,8))[0]
    if version!=0 or registration!=actual.names['__bsdthread_register']['address']:
        raise ValueError('Actual kernel registration dispatch changed')
    observed=run(['xcrun','llvm-objdump','--disassemble-symbols=__bsdthread_register,_user_cont_hwclock_allowed,_user_timebase_type',binary],'actual-kernel-contract').stdout
    if not all(s in observed for s in ('mov\tw8, #0x1df','movk\tw8, #0x4000, lsl #16','str\tw8, [x19]')):
        raise ValueError('Actual provider feature mask not observed')
    if actual.at(actual.names['_user_cont_hwclock_allowed']['address'],8)!=bytes.fromhex('e0031f2ac0035fd6'):
        raise ValueError('Continuous hardware clock not disabled by actual kernel')
    if actual.at(actual.names['_user_timebase_type']['address'],8)!=bytes.fromhex('20008052c0035fd6'):
        raise ValueError('Actual kernel does not advertise ordinary speculative CNTVCT')
    user_source=USER/'src/pthread.c';user_header=USER/'kern/kern_internal.h'
    provider_header=PROVIDER/'libpthread-libpthread-539.100.4/kern/kern_internal.h'
    for path in (user_source,user_header,provider_header):pins[str(path)]=sha(path)
    required_names=('FINEPRIO','BSDTHREADCTL','SETSELF','QOS_MAINTENANCE','QOS_DEFAULT')
    features={}
    for name in required_names:
        values=[]
        for path in (user_header,provider_header):
            values.append(int(re.search(r'#define\s+PTHREAD_FEATURE_'+name+r'\s+(0x[0-9a-fA-F]+)',path.read_text()).group(1),16))
        if values[0]!=values[1]:raise ValueError('Feature ABI disagreement')
        features[name]=values[0]
    mask=0x400001df;required=sum(features.values())
    if mask&required!=required:raise ValueError('Required features not supplied')
    diagnostic=ROOT/'build/rpi5/apple-pthread-mach-state-8rohn6p5/NOT_RUN_init-live'
    pins[str(diagnostic)]=sha(diagnostic)
    if 5 not in MachO(diagnostic).commands:raise ValueError('Static candidate lacks LC_UNIXTHREAD')
    for path,digest in {**pins,**headers}.items():
        if sha(path)!=digest:raise ValueError('Contract input drift: '+path)
    report=dict(profile='actual-linked-pi-pthread-kernel-contract-v1',source_inputs_sha256=pins,headers_sha256=headers,
        commands=commands,exact_recompiled_function_comparisons=comparisons,
        kernel_sha256=KERNEL_SHA,actual_registration_table_version=version,actual_registration_entry=hex(registration),
        actual_provider_feature_mask=hex(mask),required_user_features=features,
        required_features_present=True,actual_kernel_continuous_hwclock=False,actual_kernel_user_timebase=1,
        actual_static_candidate_lc_unixthread=True,kernel_supplies_main_stack_four_values=True,
        kernel_supplies_ptr_munge_via_read_random=True,kernel_supplies_pinned_main_thread_port=True,
        kernel_api_runtime_executed=False,entropy_qualified=False,pthread_registration_runtime_executed=False,
        target_startup_created=False,target_main_thread_initialized=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),functions=len(comparisons),features=hex(mask),entropy_qualified=False),indent=2))
    return out,report


if __name__=='__main__':build()
