#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Private genuine Apple pthread startup candidate; never runs it on the host."""
import difflib
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'build/rpi5/apple-pthread-join-wait-ri8lyyub'
BASE_SHA = '7a1b4a1953a3d565e30526d6f27fbb7e1ee99ce04dbbd0736fed62d899295fd8'
NORMAL = ROOT/'build/rpi5/apple-pthread-bcm2712-qualified-x9kp1ral'
MACH_STATE = ROOT/'build/rpi5/apple-pthread-mach-state-8rohn6p5'
USERLAND = ROOT/'experiments/darwin-container/userland'
RUNTIME = USERLAND/'build/zsh-working-2026-10-12'
SOURCE = ROOT/'tools/rpi5/user'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE/'manifest.json') != BASE_SHA: raise ValueError('Frozen closure changed')
    base = json.loads((BASE/'manifest.json').read_text())
    normal = json.loads((NORMAL/'manifest.json').read_text())
    owned = json.loads((MACH_STATE/'manifest.json').read_text())
    runtime = json.loads((RUNTIME/'provenance/apple-runtime.json').read_text())
    pins = {str(BASE/'manifest.json'):BASE_SHA, str(Path(__file__).resolve()):sha(__file__)}
    for field in ('source_inputs_sha256','headers_sha256','generated_sha256'): pins.update(base[field])
    for p in (NORMAL/'manifest.json', MACH_STATE/'manifest.json', RUNTIME/'provenance/apple-runtime.json',
              ROOT/'build/rpi5/apple-libplatform-main-candidate-20261013/src/init.c'):
        pins[str(p)] = sha(p)
    for p,d in pins.items():
        if sha(p) != d: raise ValueError('Input drift: '+p)
    out = Path(tempfile.mkdtemp(prefix='apple-pthread-static-smoke-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands, headers = [], {}
    def run(args,label,allowed=False,cwd=None):
        args=list(map(str,args)); cwd=cwd or out
        p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=90)
        (out/(label+'.stdout')).write_text(p.stdout); (out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,cwd=str(cwd),returncode=p.returncode,
                             stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode and not allowed: raise ValueError(label+': '+p.stderr[-6000:])
        return p
    def deps(raw):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        pins[str(source)] = sha(source)
        before = deps(run(flags+['-M',source],label+'-deps').stdout)
        dep,obj=out/(label+'.d'),out/(label+'.o')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text()) != before: raise ValueError('Consumed dependency mismatch')
        headers.update(before)
        return obj
    original = MACH_STATE/'darwin_static_mach_owned.c'
    text = original.read_text()
    start = text.index('/* The static experiment has no dyld or pthread-created threads.')
    text = text[:start]
    for obsolete in ('static uintptr_t main_tsd[128];\n','static int main_errno;\n','extern int zsh_main(int, char **);\n'):
        if text.count(obsolete) != 1: raise ValueError('Original entry derivation drift')
        text=text.replace(obsolete,'')
    derived=out/'darwin_abi_without_legacy_start.c'; derived.write_text(text)
    (out/'legacy-entry-removal.diff').write_text(''.join(difflib.unified_diff(original.read_text().splitlines(True),text.splitlines(True),fromfile=str(original),tofile=str(derived))))
    template=next(c['command'] for c in owned['commands'] if c['stdout'].endswith('/runtime-compile.stdout'))
    abiflags=list(template[:template.index('-MD')])+['-mcpu=cortex-a76']
    abi=compile(abiflags,derived,'private-abi')
    template=next(s['command'] for s in runtime['sources'] if s['source'].endswith('/allocator.c'))
    allocflags=list(template[:template.index('-c')])+['-std=gnu11','-mcpu=cortex-a76']
    allocator=compile(allocflags,SOURCE/'pthread_allocator.c','private-allocator')
    template=next(c['command'] for c in normal['commands'] if c['stdout'].endswith('/pthread-pthread-compile.stdout'))
    privateflags=list(template[:template.index('-H')])+['-I',str(ROOT/'libsyscall/wrappers'),'-I',str(ROOT/'build/rpi5/apple-libpthread-main-candidate-20261013/src')]
    # This is a consumer, not the non-cancellable library implementation variant.
    privateflags=[f for f in privateflags if f not in ('-D__LIBC__','-D__POSIX_LIB__','-D__DARWIN_NON_CANCELABLE=1','-D__PTHREAD_BUILDING_PTHREAD__=1')]
    privateflags[1:1]=['-I',str(ROOT/'build/rpi5/apple-pthread-messaging-headers-mubxo_kh/include'),
                       '-I',str(ROOT/'build/rpi5/apple-pthread-messaging-headers-mubxo_kh/include/mach')]
    startup=compile(privateflags,SOURCE/'pthread_static_start.c','startup')
    sdk=run(['xcrun','--sdk','macosx','--show-sdk-path'],'sdk').stdout.strip()
    publicflags=['xcrun','clang','-target','arm64-apple-macosx13.0','-mcpu=cortex-a76','-isysroot',sdk,'-std=gnu11','-Os','-ffreestanding','-fno-builtin','-fno-stack-protector']
    smoke=compile(publicflags,SOURCE/'pthread_smoke.c','smoke')
    replacement_records=[]
    def replace_archive(original,member,replacement,label):
        pins[str(original)]=sha(original)
        directory=out/label;directory.mkdir()
        members=run(['xcrun','ar','t',original],label+'-members').stdout.splitlines()
        members=[n for n in members if not n.startswith('__.SYMDEF')]
        if len(set(members))!=len(members) or member not in members or any('/' in n or n in ('.','..') for n in members):
            raise ValueError('Unsafe private archive members')
        run(['xcrun','ar','x',original],label+'-extract',cwd=directory)
        before={n:sha(directory/n) for n in members}
        (directory/member).write_bytes(replacement.read_bytes())
        after={n:sha(directory/n) for n in members}
        if {n for n in members if before[n]!=after[n]}!={member}: raise ValueError('Wrong private replacement')
        target=out/(label+'.a');run(['xcrun','ar','rcs',target,*[directory/n for n in members]],label+'-archive')
        replacement_records.append(dict(original=str(original),private=str(target),member=member,before=before,after=after))
        return target
    private_abi=replace_archive(Path(owned['target_archive']),'14-darwin_static.o',abi,'private-abi-runtime')
    original_runtime=RUNTIME/'archives/apple-runtime/libapple-runtime.a'
    private_runtime=replace_archive(original_runtime,'glue-allocator.o',allocator,'private-apple-runtime')
    link=next(list(c['command']) for c in base['commands'] if c['stdout'].endswith('/init-live-link.stdout'))
    removals=[p for p in link if p.endswith('/probe-target.o') or p.endswith('/argv-entry.o') or p.endswith('/libapple-ssh-libressl-packet.a') or p.endswith('/libcrypto.a')]
    if len(removals)!=4: raise ValueError('Expected exact old packet/entry link inputs')
    link=[p for p in link if p not in removals]
    link[link.index(str(Path(owned['target_archive'])))]=str(private_abi)
    link[link.index(str(original_runtime))]=str(private_runtime)
    target=out/'NOT_RUN_pthreadprobe'
    link[link.index('-o')+1]=str(target);link[link.index('-map')+1]=str(out/'target.map')
    link += [str(startup),str(smoke)]
    result=run(link,'target-link',allowed=True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    if not result.returncode:
        run(['xcrun','nm','-u',target],'target-undefined')
        run(['xcrun','nm','-g',target],'target-symbols')
        run(['xcrun','otool','-l',target],'target-loadcommands')
        run(['xcrun','llvm-objdump','--disassemble-symbols=_darwin_static_start,_pthread_join,__pthread_set_self_dyld',target],'target-startup-disassembly')
    for p,d in {**pins,**headers}.items():
        if sha(p)!=d: raise ValueError('Private input drift: '+p)
    report=dict(profile='genuine-apple-pthread-private-static-startup-smoke-v1',
        source_inputs_sha256=pins,headers_sha256=headers,commands=commands,
        target=str(target),target_sha256=sha(target) if target.exists() else None,
        target_link_complete=not result.returncode,target_missing_symbols=missing,target_duplicate_symbols=duplicate,
        exact_archive_replacements=replacement_records,removed_old_link_inputs=removals,
        target_startup_created=True,constructors_order_wired=True,
        libkernel_callbacks_version=4,pthread_callbacks_version=2,
        original_dyld_main_thread_owner=True,original_normal_pthread_implementation=True,
        selected_libc='preserved static/lazy Apple source slice, not modern full Libc initialization',
        selected_allocator='preserved Apple scalable_malloc with private concurrent frontend',
        dynamic_loader_services=False,modern_libsystem_coverage=False,
        target_main_thread_initialized=False,target_created_threads=False,
        kernel_entropy_qualified=False,accepted_runtime_modified=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(package=str(out),linked=not result.returncode,missing=missing,duplicates=duplicate),indent=2))
    return out,report


if __name__=='__main__': build()
