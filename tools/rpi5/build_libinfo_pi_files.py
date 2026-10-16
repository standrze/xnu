#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Explicit real file-backed Pi Libinfo composition, with honest runtime gaps."""
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from tools.rpi5 import build_apple_libinfo_numeric as prior
from tools.rpi5 import libinfo_pi_files_profile as profile

ROOT,sha,SOURCE=prior.ROOT,prior.sha,prior.SOURCE
BASE=ROOT/'build/rpi5/apple-libinfo-numeric-f893rytw'
BASE_SHA='4eabb37da4c78195671150c37342f2021582c7ad7a4194bd960d5929596d1a2c'
DISPATCH=ROOT/'build/rpi5/sources/libdispatch/libdispatch-libdispatch-1542.100.32'
DYLD=ROOT/'build/rpi5/apple-dyld-headers-main-candidate-20261013'
HARNESS=ROOT/'tools/rpi5/tests/libinfo_pi_files_host.c'
UNITS=('libinfo.c','si_module.c','si_data.c','file_module.c','search_module.c','cache_module.c',
       'si_getaddrinfo.c','thread_data.c','ils.c','getnameinfo_link.c')
EXPECTED='PI_LIBINFO_FILES PASS THREADS=4 ACCOUNT_ITERATIONS=512 UID_MODES=2 GROUPLIST=1 SERVICE=1 NUMERIC=1 HOST_FILE=1 MISSING_FILE=1 UNAVAILABLE_MODULES=3 NO_DNS\n'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Base50 changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[k])
    for p in (Path(__file__).resolve(),Path(profile.__file__).resolve(),HARNESS):pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Pinned drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='pi-libinfo-files-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);overlay=out/'overlay';overlay.mkdir();fixtures=out/'fixtures';fixtures.mkdir()
    for n,t in profile.FIXTURES.items():(fixtures/n).write_text(t)
    (overlay/'native-paths.h').write_text(profile.native_paths(fixtures))
    transforms={}
    for n in (*UNITS,'darwin_directory_enabled.h'):
        source=SOURCE/('Libinfo' if n.endswith('.h') else 'lookup.subproj')/n
        text=source.read_text();changed=profile.transform(n,text);(overlay/n).write_text(changed)
        transforms[n]=dict(source=str(source),source_sha256=sha(source),overlay=str(overlay/n),overlay_sha256=sha(overlay/n),changed=changed!=text)
    native_search=overlay/'native-search_module.c'
    native_search.write_text(profile.once((overlay/'search_module.c').read_text(),'#define _PATH_SI_CONF "/etc/sysinfo.conf"',f'#define _PATH_SI_CONF "{fixtures}/sysinfo.conf"'))
    # si_module uses just this original private enum. Keep the exact declaration
    # and notice; do not mix private source annotations with the public SDK or
    # invent private function declarations. This supplies no runtime behavior.
    p=DISPATCH/'private/queue_private.h';pins[str(p)]=sha(p);text=p.read_text()
    enums=re.findall(r'enum \{\n\tDISPATCH_QUEUE_OVERCOMMIT = .*?\n\};',text,re.S)
    if len(enums)!=1:raise ValueError('Original dispatch queue enum changed')
    header=overlay/'rpi5_dispatch_queue_flags.h'
    header.write_text(text[:text.index('#ifndef __DISPATCH_QUEUE_PRIVATE__')]+enums[0]+'\n')
    dispatch_headers={str(header):dict(source=str(p),sha256=sha(p))}
    commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile(source,label,flags):
        scan=deps(run(flags+['-M',source],label+'-scan').stdout);obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile');actual=deps(dep.read_text())
        if scan!=actual:raise ValueError('Actual dependency mismatch')
        headers.update(actual);records[label]=dict(scanned_sha256=scan,consumed_sha256=actual);return obj
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/si_getaddrinfo-compile.stdout'))
    target=old[:old.index('-MD')]
    target=[x for x in target if x not in ['-D'+m for m in prior.previous.MACROS]]
    target[1:1]=['-I',str(overlay)]
    target+=['-D'+m for m in profile.MACROS]
    objects=[compile(overlay/n,'target-'+Path(n).stem,target) for n in UNITS]
    archive=out/'libpi-libinfo-files.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    # Keep native CPU ABI; this is not target execution. The uid boundary tests
    # both original account-file policies without changing host credentials.
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-include',str(overlay/'native-paths.h'),'-Dgeteuid=rpi5_fixture_geteuid']
    hostobjects=[compile(native_search if n=='search_module.c' else overlay/n,'host-'+Path(n).stem,native) for n in UNITS]
    # Current original conversions/packing are already separately tested. Use
    # their real native objects, never a numeric provider shim.
    hostobjects+=[BASE/('host-'+n+'.o') for n in ('inet_addr','inet_ntop','inet_pton','inet_ntoa')]
    caller=compile(HARNESS,'host-caller',native+['-DFIXTURE_DIRECTORY="'+str(fixtures)+'"'])
    host=out/'host-pi-files'
    run(native+[caller,*hostobjects,'-Wl,-dead_strip','-Wl,-map,'+str(out/'host.map'),'-o',host],'host-link')
    result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Native full file service oracle failed')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    # Replace overlapping numeric/inventory Libinfo owners, retaining genuine
    # getifaddrs/h_errno and conversions from those frozen archives as needed.
    i=link.index(str(prior.BASE/'libapple-libinfo-compiled-inventory.a'))
    link.insert(i,str(archive))
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    report=dict(profile=profile.PROFILE,source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        commands=commands,target_archive=str(archive),source_transforms=transforms,dispatch_header_inputs=dispatch_headers,
        target_macros=profile.MACROS,fixtures={n:dict(path=str(fixtures/n),sha256=sha(fixtures/n)) for n in profile.FIXTURES},
        native_stdout=EXPECTED,native_asan_ubsan_pass=True,native_host_runtime_boundary=['libdispatch','Blocks','pthread','Libc allocator/I/O','os_log','network comparison SPI'],
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,previous_missing_count=len(base['target_missing_symbols']),
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        target_link_complete=not result.returncode,target_executed=False,host_account_files_accessed=False,dns_executed=False,
        provider_stubs=False,accepted_runtime_modified=False,original_macos_profile_unchanged=True,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=report['closed_symbols'],remaining=len(missing),new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
