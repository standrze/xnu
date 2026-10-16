#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct current Apple directory family, never mixed with legacy DIR owners.

Five complete original units, one narrowly corrected ownership unit and the
original syscall generator are retained, alongside the original failures.
The accepted archive is immutable; five old owners are removed only in a private
copy. Artifacts and native doubles are not evidence of target execution.
"""
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_spawn_group as prior
from tools.rpi5 import prepare_pid1

ROOT, LIBC, sha = prior.ROOT, prior.LIBC, prior.sha
BASE = ROOT/'build/rpi5/apple-ssh-spawn-contract-o1r3nnno'
BASE_SHA = '08e28e13a755e593ce315df0b0454b53339455675aedd81b05006ef6f85b09eb'
LIBC_COMMIT = '71bbe350ab79eef58113991d817ccc6165061a64'
FLAGS = ROOT/'build/rpi5/apple-ssh-tty-temp-bm2n0nkz/manifest.json'
SYSCALLS = ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7/manifest.json'
OLD = ROOT/'build/rpi5/apple-ssh-case-signal-z9p6dj86/private-apple-runtime-current-comparisons.a'
FRAGMENTS = ROOT/'build/rpi5/apple-runtime-api-fragments-bg8jq8u2/libapple-selected-runtime-apis.a'
UNITS = tuple('gen/FreeBSD/'+n+'.c' for n in
              ('opendir','readdir','closedir','telldir','seekdir','rewinddir'))
MEMBERS = tuple('gen-'+n+'.o' for n in ('closedir','opendir','readdir','telldir','seekdir'))
FORCE = ('_opendir','___opendir2','_fdopendir','_readdir','_readdir_r','_closedir',
         '_fdclosedir','_telldir','_seekdir','_rewinddir','__filldir',
         '__readdir_unlocked','__reclaim_telldir','__seekdir','__fixtelldir',
         '___getdirentries64')
HARNESS=ROOT/'tools/rpi5/tests/ssh_directory_host.c'
ABI_SOURCE=ROOT/'tools/rpi5/tests/ssh_directory_abi.c'
CLIENT=ROOT/'build/rpi5/apple-ssh-full-client-3xbnfnp5/manifest.json'
EXPECTED='APPLE_DIRECTORY PASS WHOLE_FAMILY=6 THREADS=4 ENTRIES=192 TEST_ONLY_FILESYSTEM TARGET_NOT_RUN\n'
RENAMES={name:'fixture_'+name.lstrip('_') for name in
         ('opendir','__opendir2','fdopendir','readdir','readdir_r','closedir','fdclosedir',
          'telldir','seekdir','rewinddir','_filldir','_readdir_unlocked','_reclaim_telldir',
          '_seekdir','_fixtelldir','__getdirentries64','__isthreaded','open','openat','close',
          'fcntl','fstat','fstatfs','lseek','malloc','free','reallocf')}
RENAMES['_seekdir']='fixture_internal_seekdir'


def checked_compat(text):
    old='(unsigned long)&((struct dirent *)0)->d_name'
    if text.count(old)!=1:raise ValueError('Exact original DIR size constant required')
    return text.replace(old,'(unsigned long)__builtin_offsetof(struct dirent, d_name)',1)


def checked_opendir(text):
    old='\t\tif (n < 0) {\n\t\t\tsaved_errno = errno;\n\t\t\t_close(fd2);'
    new='\t\tif (n < 0) {\n\t\t\tsaved_errno = errno;\n\t\t\tfree(buf);\n\t\t\t_close(fd2);'
    if text.count(old)!=1:raise ValueError('Exact union read-failure ownership site required')
    text=text.replace(old,new,1)
    old='\tdirp->dd_buf = buf;'
    if text.count(old)!=1:raise ValueError('Exact union successful replacement site required')
    return text.replace(old,'\tfree(dirp->dd_buf);\n'+old,1)


def const_bytes(path):
    """Extract the unique constant array from our small original A76 object."""
    data=Path(path).read_bytes()
    if len(data)<32 or struct.unpack_from('<I',data)[0]!=0xfeedfacf:raise ValueError('Mach-O64 object required')
    if struct.unpack_from('<I',data,12)[0]!=1:raise ValueError('Object file required')
    ncmds,cmdbytes=struct.unpack_from('<II',data,16);cursor=32;found=[]
    if cmdbytes>len(data)-32:raise ValueError('Command extent')
    for _ in range(ncmds):
        if cursor+8>32+cmdbytes:raise ValueError('Command header')
        cmd,size=struct.unpack_from('<II',data,cursor)
        if size<8 or cursor+size>32+cmdbytes:raise ValueError('Command size')
        if cmd==0x19:
            if size<72:raise ValueError('Segment header')
            count=struct.unpack_from('<I',data,cursor+64)[0]
            if size!=72+count*80:raise ValueError('Section extent')
            for i in range(count):
                p=cursor+72+i*80
                if data[p:p+16].rstrip(b'\0')!=b'__const':continue
                length=struct.unpack_from('<Q',data,p+40)[0];offset=struct.unpack_from('<I',data,p+48)[0]
                if length>len(data) or offset>len(data)-length:raise ValueError('Section bytes')
                found.append(data[offset:offset+length])
        cursor+=size
    if cursor!=32+cmdbytes or len(found)!=1 or len(found[0])!=22*8:raise ValueError('Exact ABI array required')
    return found[0]


def build():
    if sha(BASE/'manifest.json') != BASE_SHA: raise ValueError('Frozen41 predecessor differs')
    base = json.loads((BASE/'manifest.json').read_text())
    pins = {str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in base[key].items():
            if name in pins and pins[name] != digest: raise ValueError('Conflicting input pin')
            pins[name] = digest
    generator = ROOT/'libsyscall/xcodescripts/create-syscalls.pl'
    custom,platforms,master = ROOT/'libsyscall/custom',ROOT/'libsyscall/Platforms',ROOT/'bsd/kern/syscalls.master'
    tools={str(Path(subprocess.check_output(['xcrun','--find',name],text=True).strip()).resolve()):None
           for name in ('clang','ld','ar','llvm-objdump','nm')}
    tools.update({str(Path('/usr/bin/perl').resolve()):None,str(Path('/usr/bin/xcrun').resolve()):None})
    tools={name:sha(name) for name in tools}
    for name,digest in tools.items():
        if name in pins and pins[name]!=digest:raise ValueError('Tool source conflict')
        pins[name]=digest
    for p in (FLAGS,SYSCALLS,CLIENT,OLD,FRAGMENTS,HARNESS,ABI_SOURCE,generator,master,*custom.iterdir(),
              platforms/'syscall.map',platforms/'MacOSX/arm64/syscall.map',
              *[LIBC/n for n in UNITS],LIBC/'gen/__dirent.h',LIBC/'gen/FreeBSD/telldir.h',
              ROOT/'bsd/sys/dirent_private.h'):
        if p.is_file():
            digest=sha(p)
            if str(p) in pins and pins[str(p)]!=digest:raise ValueError('Original input conflict')
            pins[str(p)]=digest
    for name in UNITS:
        if (LIBC/name).read_bytes() != subprocess.check_output(['git','-C',LIBC,'show',LIBC_COMMIT+':'+name]):
            raise ValueError('Whole original unit changed '+name)
    def verify():
        for name,digest in pins.items():
            if sha(name) != digest: raise ValueError('Input drift '+name)
    verify()
    out = Path(tempfile.mkdtemp(prefix='apple-ssh-directory-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers,records,objects,failures = [],{},{},{},{}
    def run(args,label,allowed=False,env=None):
        args = list(map(str,args));r = subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90,env=env)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
                             stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-5000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label,allowed=False):
        scan = run([*flags,'-M',path],label+'-scan',allowed)
        if scan.returncode:failures[label]='scan';return None
        before = deps(scan.stdout);headers.update(before)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        r=run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile',allowed)
        after=deps(dep.read_text()) if dep.is_file() else {}
        records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        if r.returncode:failures[label]='compile';return None
        if before!=after:raise ValueError('Compiler dependency drift')
        return obj
    template=next(c['command'] for c in json.loads(FLAGS.read_text())['commands']
                  if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    flags=template[:template.index('-MD')]+['-include',str(LIBC/'gen/__dirent.h'),
                                          '-include',str(ROOT/'bsd/sys/dirent_private.h')]
    original_compat=str(LIBC/'fbsdcompat/_fbsd_compat_.h')
    compat=out/'fbsd_compat_checked.h';compat.write_text(checked_compat(Path(original_compat).read_text()))
    if flags.count(original_compat)!=1:raise ValueError('Original compatibility header slot required')
    flags[flags.index(original_compat)]=str(compat)
    checked_open=out/'opendir_ownership_checked.c'
    checked_open.write_text(checked_opendir((LIBC/UNITS[0]).read_text()))
    flags+=['-I',str(LIBC/'gen/FreeBSD')]
    client_command=next(c['command'] for c in json.loads(CLIENT.read_text())['commands']
                        if c['stdout'].endswith('/086-ssh-compile.stdout'))
    client_flags=client_command[:client_command.index('-MD')]
    client_abi=compile_(client_flags,ABI_SOURCE,'client-dir-abi')
    provider_abi=compile_(flags,ABI_SOURCE,'provider-dir-abi')
    abi=const_bytes(provider_abi)
    if const_bytes(client_abi)!=abi:raise ValueError('Original client/provider directory ABI mismatch')
    compile_(flags,LIBC/UNITS[0],'original-opendir')
    for name in UNITS:
        obj=compile_(flags,checked_open if name==UNITS[0] else LIBC/name,Path(name).stem,True)
        if obj:objects[Path(name).stem]=str(obj);run(['xcrun','nm','-g',obj],Path(name).stem+'-symbols')
    generated=out/'generated';generated.mkdir()
    run(['/usr/bin/perl',generator,master,custom,platforms,'MacOSX',generated],
        'original-generator',env=dict(os.environ,ARCHS='arm64'))
    original=json.loads(SYSCALLS.read_text())
    template=next(c['command'] for c in original['commands'] if c['stdout'].endswith('/bind-preprocess.stdout'))
    sflags=template[:template.index('-E')]
    source=generated/'___getdirentries64.s'
    if 'SYSCALL_NONAME(getdirentries64, 4, cerror_nocancel)' not in source.read_text():
        raise ValueError('Original private getdirentries64 policy differs')
    before=deps(run([*sflags,'-M',source],'getdirentries64-scan').stdout)
    dep,asm,obj=out/'getdirentries64.d',out/'getdirentries64.s',out/'getdirentries64.o'
    pre=run([*sflags,'-E','-P','-MD','-MF',dep,source],'getdirentries64-preprocess')
    after=deps(dep.read_text())
    if before!=after:raise ValueError('Syscall dependency drift')
    headers.update(before);records['getdirentries64']=dict(scanned_sha256=before,consumed_sha256=after)
    asm.write_text(pre.stdout.replace('%%','\n').replace(';','\n'))
    run([sflags[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',obj],'getdirentries64-assemble')
    run(['xcrun','llvm-objdump','-d','-r',obj],'getdirentries64-disassembly')
    objects['getdirentries64']=str(obj)
    archive=out/'libapple-current-directory.a';run(['xcrun','ar','rcs',archive,*objects.values()],'archive')
    private=out/'private-apple-runtime-current-directory.a';shutil.copyfile(OLD,private)
    members=run(['xcrun','ar','-t',OLD],'old-members').stdout.splitlines()
    if any(members.count(n)!=1 for n in MEMBERS):raise ValueError('Exact five old DIR owners required')
    run(['xcrun','ar','-d',private,*MEMBERS],'remove-old-directory')
    after_members=run(['xcrun','ar','-t',private],'private-members').stdout.splitlines()
    if after_members!=[n for n in members if n not in MEMBERS]:raise ValueError('Unrelated archive member changed')
    for name in after_members:
        if name!='__.SYMDEF SORTED' and subprocess.check_output(['xcrun','ar','-p',OLD,name])!=subprocess.check_output(['xcrun','ar','-p',private,name]):
            raise ValueError('Unrelated member bytes differ')
    def link_command(label,target):
        link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/'+label+'.stdout')))
        if link.count(str(OLD))!=1:raise ValueError('Exact old archive slot required')
        link[link.index(str(OLD))]=str(private);link[link.index('-o')+1]=str(out/target)
        link[link.index('-map')+1]=str(out/(label+'.map'))
        return [*link,str(FRAGMENTS),str(archive)]
    link=link_command('target-link','NOT_RUN_ssh');result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    if failures or duplicates or set(base['target_missing_symbols'])-set(missing)!={'_readdir_r'} or set(missing)-set(base['target_missing_symbols']):
        raise ValueError('Exact41 to40 complete client delta required')
    contract=link_command('contract-link','NOT_RUN_directory_contract')
    for symbol in FORCE:contract+=['-u',symbol]
    cr=run(contract,'contract-link');inspected=None;owners={}
    if cr.returncode==0:
        target=out/'NOT_RUN_directory_contract'
        if run(['xcrun','nm','-ju',target],'contract-undefined').stdout:raise ValueError('Forced target undefined')
        inspected=prepare_pid1.inspect(target.read_bytes())
        text=(out/'contract-link.map').read_text()
        table={int(n):p for n,p in re.findall(r'(?m)^\[\s*(\d+)\]\s+(.+)$',text)}
        for symbol in (*FORCE,'_pthread_mutex_lock','_pthread_mutex_unlock','_pthread_mutex_destroy',
                       '_fstatfs','_fstat','_open$NOCANCEL','_openat$NOCANCEL','_reallocf','_cerror_nocancel'):
            hits=re.findall(r'(?m)^0x[0-9A-Fa-f]+\s+0x[0-9A-Fa-f]+\s+\[\s*(\d+)\]\s+'+re.escape(symbol)+'$',text)
            if len(hits)!=1:raise ValueError('Forced provider absent '+symbol)
            owners[symbol]=table[int(hits[0])]
        if any(n in text for n in ('fixture_','__asan','__ubsan')):raise ValueError('Test provider in static target')
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    renamed=native+[f'-D{k}={v}' for k,v in RENAMES.items()]
    host_objects=[compile_(renamed,checked_open if name==UNITS[0] else LIBC/name,'host-'+Path(name).stem) for name in UNITS]
    harness=compile_(native,HARNESS,'host-harness')
    original_flags=list(renamed);original_flags[original_flags.index(str(compat))]=original_compat
    original_read=compile_(original_flags,LIBC/'gen/FreeBSD/readdir.c','host-original-readdir')
    original_open=compile_(original_flags,LIBC/UNITS[0],'host-original-opendir')
    original_host=out/'original-directory-host'
    run([*native,original_open,original_read,*host_objects[2:],harness,'-o',original_host],'original-host-link')
    original_result=run([original_host],'original-host-negative',True)
    if not original_result.returncode or 'member access within null pointer' not in original_result.stderr:
        raise ValueError('Original directory size UB was not reproduced')
    original_leaks=run([original_host,'original-leaks'],'original-leak-negative')
    if original_leaks.stdout!='APPLE_DIRECTORY LEAKS=2 ORIGINAL_ERRNO_PRESERVED\n' or original_leaks.stderr:
        raise ValueError('Original union buffer leaks were not reproduced')
    if run([original_host,'leak-oracle'],'original-leak-contract-failure',True).returncode!=38:
        raise ValueError('Original failing cleanup oracle accepted')
    host=out/'directory-host';run([*native,*host_objects,harness,'-o',host],'host-link')
    hr=run([host],'host-run')
    if hr.stdout!=EXPECTED or hr.stderr:raise ValueError('Native contract mismatch')
    if run([host,'bad-expectation'],'host-negative',True).returncode!=37:raise ValueError('Native negative oracle accepted')
    fixed_leaks=run([host,'leak-oracle'],'host-cleanup')
    if fixed_leaks.stdout!='APPLE_DIRECTORY LEAKS=0 ORIGINAL_ERRNO_PRESERVED\n' or fixed_leaks.stderr:
        raise ValueError('Derived cleanup oracle differs')
    if run([host,'original-leaks'],'host-cleanup-negative',True).returncode!=38:raise ValueError('Derived leak negative accepted')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Consumed header drift')
    report=dict(profile='whole-current-apple-directory-family-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,objects=objects,
        compile_failures=failures,original_units=list(UNITS),original_units_unchanged=False,
        whole_unchanged_units=list(UNITS[1:]),derived_opendir=str(checked_open),opendir_two_ownership_frees_only=True,
        target_archive=str(archive),private_archive=str(private),removed_old_members=list(MEMBERS),
        original_libc_commit=LIBC_COMMIT,original_generator_environment={'ARCHS':'arm64'},
        tools_sha256=tools,directory_client_provider_abi_identical=True,directory_abi=list(struct.unpack('<22Q',abi)),
        directory_abi_source=str(ABI_SOURCE),client_compile_flags_source=str(CLIENT),
        unrelated_members_byte_identical=True,forced_apis=list(FORCE),live_symbol_owners=owners,
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        contract_returncode=cr.returncode,static_inspection=inspected,
        target_executed=False,full_client_qualified=False,provider_stubs=False,
        accepted_runtime_modified=False,original_openssh_config_unchanged=True,
        native_contract_passed=True,native_asan_ubsan_pass=True,native_stdout=hr.stdout,
        derived_compat_header=str(compat),original_compat_null_member_ub_reproduced=True,
        original_union_buffer_leaks_reproduced=2,derived_union_buffer_leaks=0,
        native_filesystem_syscalls_and_allocator_are_test_only=True,
        target_directory_syscall_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),failures=failures,
        missing=len(missing),closed=report['closed_symbols'],new=report['newly_reachable_symbols'],
        duplicates=duplicates,contract_rc=cr.returncode),indent=2))
    return out,report


if __name__=='__main__':build()
