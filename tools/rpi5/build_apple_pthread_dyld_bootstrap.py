#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original VARIANT_DYLD main-thread owner plus original normal pthread APIs.

Only the genuine bootstrap implementation is privately namespaced. Public
pthread APIs still resolve to the normal, fully featured library; this does not
replace them with the intentionally restricted dyld product's API variants.
"""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/rpi5/apple-pthread-mach-state-8rohn6p5'
BASE_SHA='6f23ca213bd8760dfd79bb12bcc3c7155e7ee54e6ebef2413ff42a43aff880dc'
NORMAL=ROOT/'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'
MACH=ROOT/'build/rpi5/apple-pthread-messaging-headers-mubxo_kh'
SOURCE=ROOT/'build/rpi5/apple-libpthread-main-candidate-20261013/src/pthread.c'


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen runtime closure drift')
    base=json.loads((BASE/'manifest.json').read_text())
    normal=json.loads((NORMAL/'manifest.json').read_text())
    mach=json.loads((MACH/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])
    project=SOURCE.parents[1]/'libpthread.xcodeproj/project.pbxproj'
    static=SOURCE.parents[1]/'xcodescripts/static.xcconfig'
    for path in (SOURCE,project,static):pins[str(path)]=sha(path)
    if 'VARIANT_DYLD=1' not in project.read_text() or 'VARIANT_STATIC=1' not in static.read_text():
        raise ValueError('Original product configuration missing')
    out=Path(tempfile.mkdtemp(prefix='apple-pthread-dyld-bootstrap-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers=[],{}
    def run(args,label,allowed=False):
        args=list(map(str,args));p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=90)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,returncode=p.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode and not allowed:raise ValueError(label+': '+p.stderr[-7000:])
        return p
    def deps(raw):return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        before=deps(run(flags+['-M',source],label+'-deps').stdout)
        dep,obj=out/(label+'.d'),out/(label+'.o')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Actual consumed bootstrap dependency mismatch')
        headers.update(before);return obj
    template=next(c['command'] for c in normal['commands'] if c['stdout'].endswith('/pthread-pthread-compile.stdout'))
    flags=list(template[:template.index('-H')])+['-DVARIANT_DYLD=1']
    inventory=compile(flags,SOURCE,'dyld-inventory')
    symbols=run(['xcrun','nm','-g',inventory],'dyld-inventory-symbols').stdout
    definitions=re.findall(r'^[0-9a-f]+ [A-Z] _([a-zA-Z_][a-zA-Z_0-9]*)$',symbols,re.M)
    if '_pthread_set_self' not in definitions or '_main_thread' not in definitions:
        raise ValueError('Actual dyld owner and bootstrap missing')
    scoped=compile(flags+['-D'+n+'=rpi5_dyld_'+n for n in definitions],SOURCE,'dyld-scoped')
    after=run(['xcrun','nm','-g',scoped],'dyld-scoped-symbols').stdout
    scoped_names=re.findall(r'^[0-9a-f]+ [A-Z] _([a-zA-Z_][a-zA-Z_0-9]*)$',after,re.M)
    if set(scoped_names)!={'rpi5_dyld_'+n for n in definitions}:raise ValueError('Bootstrap global namespace not closed')
    archive=out/'libapple-pthread-dyld-bootstrap.a';run(['xcrun','ar','rcs',archive,scoped],'bootstrap-archive')
    template=next(c['command'] for c in mach['commands'] if c['stdout'].endswith('/mach_init-compile.stdout'))
    machflags=list(template[:template.index('-MD')])+['-D_pthread_set_self=rpi5_dyld__pthread_set_self']
    # Original upstream comment explicitly permits the dyld entrypoint to be
    # adopted by static libsyscall. No pthread structure or TSD is invented.
    original_mach=ROOT/'libsyscall/mach/mach_init.c'
    new_mach=compile(machflags,original_mach,'mach-init-dyld')
    original_archive=Path(mach['target_archive'])
    members=run(['xcrun','ar','t',original_archive],'original-mach-members').stdout.splitlines()
    if len(members)!=len(set(members)) or any('/' in n or n in ('.','..') for n in members):raise ValueError('Unsafe archive members')
    run(['xcrun','ar','x',original_archive],'extract-mach-members')
    before_members={n:sha(out/n) for n in members}
    (out/'mach_init.o').write_bytes(new_mach.read_bytes())
    after_members={n:sha(out/n) for n in members}
    if {n for n in members if before_members[n]!=after_members[n]}!={'mach_init.o'}:raise ValueError('Unexpected Mach replacement')
    new_archive=out/'libapple-pthread-mach-dyld-bootstrap.a'
    run(['xcrun','ar','rcs',new_archive,*[out/n for n in members]],'mach-private-archive')
    link=next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    if link.count(str(original_archive))!=1:raise ValueError('Original provider link binding missing')
    link[link.index(str(original_archive))]=str(new_archive)
    link[link.index('-o')+1]=str(out/'NOT_RUN_init-live')
    link[link.index('-map')+1]=str(out/'init-live.map')
    link+=[str(archive)]
    attempt=run(link,'init-live-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',attempt.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",attempt.stderr)))
    if not attempt.returncode:
        run(['xcrun','nm','-u',out/'NOT_RUN_init-live'],'target-undefined')
        run(['xcrun','llvm-objdump','--disassemble-symbols=_mach_init_doit,_rpi5_dyld__pthread_set_self,_rpi5_dyld__pthread_set_self_dyld,__pthread_set_self',out/'NOT_RUN_init-live'],'actual-bootstrap-disassembly')
    for path,digest in {**pins,**headers}.items():
        if sha(path)!=digest:raise ValueError('Bootstrap input drift: '+path)
    report=dict(profile='original-apple-dyld-bootstrap-owner-private-link-v1',source_inputs_sha256=pins,
        headers_sha256=headers,commands=commands,namespaced_original_definitions=definitions,
        original_mach_archive_members_sha256=before_members,private_mach_archive_members_sha256=after_members,
        target_archive=str(archive),target_archive_sha256=sha(archive),
        private_mach_archive=str(new_archive),private_mach_archive_sha256=sha(new_archive),
        target_link_complete=not attempt.returncode,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        original_dyld_owns_real_main_pthread=True,normal_pthread_apis_remain_normal_variant=True,
        mach_init_uses_original_dyld_bootstrap=True,target_startup_created=False,
        target_main_thread_initialized=False,constructors_order_wired=False,
        accepted_runtime_modified=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),linked=not attempt.returncode,missing=missing,duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
