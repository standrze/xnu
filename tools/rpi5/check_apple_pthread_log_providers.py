#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Native namespaced original logging providers using real host services."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/rpi5/apple-pthread-log-clock-m3ct69va'
BASE_SHA='47ed14c78a38d0c81f2325228e44f8205bc6a778e11cd4297b3bec6b1a821d9b'
MEMORY=ROOT/'build/rpi5/apple-pthread-memory-4idfg5qr'


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA: raise ValueError('Frozen provider input drift')
    base=json.loads((BASE/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'): pins.update(base[key])
    harness=ROOT/'tools/rpi5/tests/pthread_log_providers_host.c';pins[str(harness)]=sha(harness)
    out=Path(tempfile.mkdtemp(prefix='apple-pthread-log-check-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands,headers=[],{}
    def run(args,label):
        args=list(map(str,args));p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=60)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,returncode=p.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode: raise ValueError(label+': '+p.stderr)
        return p
    def deps(raw):return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label,assembly=False):
        before=deps(run(flags+['-M',source],label+'-deps').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        if assembly:
            raw=run(flags+['-E','-P','-MD','-MF',dep,source],label+'-preprocess').stdout
            generated=out/(label+'.s');generated.write_text(raw.replace('%%','\n').replace(';','\n'))
            run([flags[0],'-x','assembler','-c',generated,'-o',obj],label+'-assemble')
        else: run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Native consumed dependency mismatch')
        headers.update(before);return obj
    def native_flags(label,assembly=False):
        suffix='-preprocess.stdout' if assembly else '-compile.stdout'
        c=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/'+label+suffix))
        flags=list(c[:c.index('-E' if assembly else '-MD')])
        index=flags.index('-target');del flags[index:index+2];flags.remove('-mcpu=cortex-a76')
        if not assembly:flags+=['-g','-fsanitize=address,undefined','-fno-sanitize-recover=all']
        return flags
    objects=[]
    stringflags=native_flags('platform-strlcpy')
    stringflags += ['-D'+n+'=rpi5_native_'+n for n in ('_platform_strlcpy','_platform_strlen','_platform_memmove')]
    objects.append(compile(stringflags,next(Path(u['source']) for u in base['units'] if u['label']=='platform-strlcpy'),'native-strlcpy'))
    for name in ('native-strlen.o','native-memmove.o'):
        pins[str(MEMORY/name)]=sha(MEMORY/name);objects.append(MEMORY/name)
    for label in ('libproc','continuous-time'):
        target=BASE/(label+'.o');symbols=run(['xcrun','nm','-g',target],label+'-symbols').stdout
        names=re.findall(r'^[0-9a-f]+ T _([a-zA-Z_0-9]+)$',symbols,re.M)
        flags=native_flags(label)+['-D'+n+'=rpi5_native_'+n for n in names]
        if label=='libproc': flags+=['-D__proc_info=rpi5_host_proc_info']
        else:flags+=['-Dmach_absolute_time=rpi5_native_mach_absolute_time']
        source=next(Path(u['source']) for u in base['units'] if u['label']==label)
        objects.append(compile(flags,source,'native-'+label))
    flags=native_flags('absolute-time',True)
    flags+=['-D'+n+'=rpi5_native_'+n for n in ('_mach_absolute_time','_mach_absolute_time_kernel','_mach_continuous_time_kernel')]
    # Assembly symbols include a leading underscore, unlike C identifiers.
    flags=[s.replace('=rpi5_native__mach','=_rpi5_native_mach') for s in flags]
    objects.append(compile(flags,ROOT/'libsyscall/wrappers/mach_absolute_time.s','native-absolute',True))
    flags=native_flags('log-traps',True)
    names={'_socket':'_rpi5_host_socket','___sendto':'_rpi5_host_sendto','___proc_info':'_rpi5_host_proc_info',
           '_close$NOCANCEL':'_rpi5_host_close','_fcntl$NOCANCEL':'_rpi5_host_fcntl','_connect$NOCANCEL':'_rpi5_host_connect'}
    # '$' is valid in assembler identifiers, not C preprocessor macro names.
    # Namespace only the symbol operands in a private emitter input copy.
    original=ROOT/'tools/rpi5/user/pthread_log_runtime_calls.S';raw=original.read_text()
    for a,b in names.items():
        if raw.count('('+a+',')!=1:raise ValueError('Exact syscall emitter changed')
        raw=raw.replace('('+a+',','('+b+',')
    copied=out/'host-log-calls.S';copied.write_text(raw)
    flags+=['-Dcerror_nocancel=rpi5_host_cerror']
    objects.append(compile(flags,copied,'native-traps',True))
    compiler=flags[0];sdk=flags[flags.index('-isysroot')+1]
    hostflags=[compiler,'-isysroot',sdk,'-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all']
    objects.append(compile(hostflags,harness,'native-harness'))
    binary=out/'log-provider-host'
    run(hostflags+objects+['-Wl,-dead_strip','-o',binary],'native-link')
    result=run([binary],'native-run')
    if result.stderr:raise ValueError('Unexpected native diagnostics')
    for path,digest in {**pins,**headers}.items():
        if sha(path)!=digest:raise ValueError('Input drift: '+path)
    report=dict(profile='original-apple-log-provider-real-native-tests-v1',source_inputs_sha256=pins,
        headers_sha256=headers,commands=commands,native_stdout=result.stdout,native_asan_ubsan=True,
        actual_host_kernel_services=True,host_vm_wrappers_tested=False,
        target_startup_created=False,target_main_thread_initialized=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),stdout=result.stdout),indent=2))
    return out,report


if __name__=='__main__':build()
