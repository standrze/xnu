#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Short native adapter/oracle tests; no target startup or target threads run."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def check():
    out=Path(tempfile.mkdtemp(prefix='apple-pthread-static-native-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    pins={str(Path(__file__).resolve()):sha(__file__)};commands=[];headers={}
    def run(args,label):
        args=list(map(str,args));p=subprocess.run(args,cwd=out,capture_output=True,text=True,timeout=30)
        (out/(label+'.stdout')).write_text(p.stdout);(out/(label+'.stderr')).write_text(p.stderr)
        commands.append(dict(command=args,returncode=p.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode:raise ValueError(label+': '+p.stderr+str(p.returncode))
        return p
    def deps(raw):return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
    flags=['xcrun','clang','-std=gnu11','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined']
    def compile(source,label,extra=()):
        pins[str(source)]=sha(source);args=flags+list(extra)
        before=deps(run(args+['-M',source],label+'-deps').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        run(args+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        if deps(dep.read_text())!=before:raise ValueError('Native dependency drift')
        headers.update(before);return obj
    names='malloc calloc free realloc valloc malloc_printf malloc_zone_register malloc_zones malloc_num_zones'.split()
    allocator=compile(ROOT/'tools/rpi5/user/pthread_allocator.c','allocator',
                      ['-D'+n+'=rpi5_'+n for n in names]+['-Dcreate_scalable_zone=fixture_create_scalable_zone'])
    harness=compile(ROOT/'tools/rpi5/tests/pthread_static_host.c','harness')
    run(flags+[allocator,harness,'-o',out/'adapter-host'],'adapter-link')
    actual=run([out/'adapter-host'],'adapter-run').stdout
    smoke=compile(ROOT/'tools/rpi5/user/pthread_smoke.c','smoke',['-DRPI5_PTHREAD_HOST=1'])
    run(flags+[smoke,'-o',out/'smoke-host'],'smoke-link')
    workload=run([out/'smoke-host'],'smoke-run').stdout
    for p,d in {**pins,**headers}.items():
        if sha(p)!=d:raise ValueError('Native input drift: '+p)
    report=dict(profile='pthread-static-adapter-host-only-v1',source_inputs_sha256=pins,
        headers_sha256=headers,commands=commands,adapter_stdout=actual,host_workload_stdout=workload,
        native_sanitizers=['address','undefined'],host_real_threads=True,host_real_malloc_zones=True,
        target_original_scalable_allocator_executed=False,target_pthread_implementation_executed=False,
        target_startup_executed=False,pi_executed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(dict(package=str(out),adapter=actual,workload=workload),indent=2))
    return out,report

if __name__=='__main__':check()
