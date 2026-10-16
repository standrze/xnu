#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Current official Libinfo macOS-profile compile/link inventory, no services run."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import link_apple_ssh_runtime_groups as previous

ROOT,sha=previous.ROOT,previous.sha
SOURCE=ROOT/'build/rpi5/apple-libinfo-main-candidate-20261013'
COMMIT='39b70c515baee5b609e7e91693edbd934b6845a1'
BASE=ROOT/'build/rpi5/apple-ssh-runtime-groups-12k4lp6u'
BASE_SHA='b1bc88e185700a8cfd0c55f6ccc3fa81fb5072f7e242b458026ca081924eb552'
UNITS=('lookup.subproj/libinfo.c','lookup.subproj/si_module.c','lookup.subproj/si_data.c',
       'lookup.subproj/file_module.c','lookup.subproj/search_module.c','lookup.subproj/cache_module.c',
       'lookup.subproj/si_getaddrinfo.c','lookup.subproj/si_compare.c','lookup.subproj/thread_data.c',
       'lookup.subproj/ds_module.c','lookup.subproj/mdns_module.c','lookup.subproj/darwin_directory.c',
       'lookup.subproj/ils.c','gen.subproj/getifaddrs.c','dns.subproj/herror.c')
MACROS=('DEBUG=0','__DARWIN_NON_CANCELABLE=1','__MigTypeCheck=1','INET6=1','CONFIG_MAC',
        'DARWIN_DIRECTORY_AVAILABLE','DS_AVAILABLE','SYNTH_ROOTFS')


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen client composition changed')
    if subprocess.check_output(['git','-C',SOURCE,'rev-parse','HEAD'],text=True).strip()!=COMMIT:raise ValueError('Official source commit changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    pins.update(base['source_inputs_sha256']);pins.update(base['generated_sha256'])
    tracked=subprocess.check_output(['git','-C',SOURCE,'ls-files','-z'],text=True).split('\0')
    for name in filter(None,tracked):
        path=SOURCE/name
        if path.read_bytes()!=subprocess.check_output(['git','-C',SOURCE,'show','HEAD:'+name]):raise ValueError('Pristine source changed: '+name)
        pins[str(path)]=sha(path)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned byte drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-libinfo-current-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={};objects={};failures=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    compiler=subprocess.check_output(['xcrun','-f','clang'],text=True).strip()
    sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()
    flags=[compiler,'-isysroot',sdk,'-target','arm64-apple-darwin','-mcpu=cortex-a76','-ffreestanding',
           '-O2','-fno-stack-protector','-fno-builtin','-fblocks','-std=gnu99','-Werror','-Wno-error=deprecated-declarations',
           '-fvisibility=hidden']+['-D'+m for m in MACROS]
    for d in ('Libinfo','lookup.subproj','gen.subproj','dns.subproj','membership.subproj','util.subproj'):
        flags+=['-I',str(SOURCE/d)]
    flags+=['-I',sdk+'/System/Library/Frameworks/System.framework/PrivateHeaders']
    pins[compiler]=sha(compiler)
    for i,name in enumerate(UNITS):
        source=SOURCE/name;label='%02d-%s'%(i,source.stem);obj=out/(label+'.o');dep=out/(label+'.d')
        scan=run(flags+['-M',source],label+'-scan',True)
        result=run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile',True)
        if result.returncode:
            failures.append(dict(source=str(source),diagnostic=result.stderr,scan_returncode=scan.returncode))
            continue
        if scan.returncode:raise ValueError('Successful compile lacks dependency scan')
        before=deps(scan.stdout);consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actual consumed dependency mismatch')
        headers.update(consumed);records[name]=dict(scanned_sha256=before,consumed_sha256=consumed)
        objects[name]=str(obj)
    archive=out/'libapple-libinfo-compiled-inventory.a'
    if not objects:raise ValueError('No source compiled; diagnostics retained at '+str(out))
    run(['xcrun','ar','rcs',archive,*objects.values()],'archive')
    link=list(base['commands'][0]['command']);link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map');link.append(str(archive))
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    report=dict(profile='official-libinfo600-original-macos-configuration-inventory-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,source_commit=COMMIT,
        source_url='https://github.com/apple-oss-distributions/Libinfo/tree/'+COMMIT,
        release='Libinfo-600',original_macros=MACROS,requested_units=UNITS,compiled_objects=objects,compile_failures=failures,
        target_archive=str(archive),target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        target_link_complete=not result.returncode,target_executed=False,native_executed=False,
        original_openssh_config_unchanged=True,libinfo_macros_removed=False,provider_stubs=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),compiled=len(objects),failed=len(failures),closed=report['closed_symbols'],
                          remaining=len(missing),new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
