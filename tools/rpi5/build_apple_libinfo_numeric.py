#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Original Libinfo numeric/account parser proof plus real complete-client delta."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import audit_apple_libinfo_current as previous

ROOT,sha,SOURCE=previous.ROOT,previous.sha,previous.SOURCE
BASE=ROOT/'build/rpi5/apple-libinfo-current-kdmwyk4q'
BASE_SHA='a4f36e835877087e9bfc5fbafa73d2f0749f4bc722a9d001b9a0c9640e9f9443'
LIBC=ROOT/'build/rpi5/apple-libc-main-candidate-20261013'
KERNEL_HEADER=ROOT/'bsd/netinet/in_private.h'
HARNESS={k:ROOT/f'tools/rpi5/tests/libinfo_{k}_host.c' for k in ('file_parsers','numeric')}
EXPECTED={'file_parsers':'LIBINFO_FILE_PARSERS PASS USERS=6 GROUPS=3 REJECTED=15 PACKED_RECORDS_ONLY\n',
          'numeric':'LIBINFO_NUMERIC PASS SERVICES=9 HOSTS=16 SMALL_BUFFER=1 ERRORS=2 FREE_CHAIN=1 NO_DNS\n'}


def private_macros(text):
    names=('IN_DS_LITE','IN_6TO4_RELAY_ANYCAST')
    selected=[]
    for n in names:
        rows=re.findall(r'^#define '+n+r'\(i\) .*$',text,re.M)
        if len(rows)!=1:raise ValueError('Original private macro membership changed')
        selected+=rows
    # Preserve the complete Apple/BSD notice, then exact original definitions.
    notice=text[:text.index('#ifndef _NETINET_IN_PRIVATE_H_')]
    return notice+'\n/* Exact definitions selected from bsd/netinet/in_private.h. */\n#include <netinet/in.h>\n'+'\n'.join(selected)+'\n'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Original macOS inventory changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[k])
    sources=[LIBC/p for p in ('net/FreeBSD/inet_addr.c','net/inet_ntop.c','net/inet_pton.c','net/FreeBSD/inet_ntoa.c')]
    for p in [Path(__file__).resolve(),KERNEL_HEADER,*HARNESS.values(),*sources]:pins[str(p)]=sha(p)
    for p in sources:
        if p.read_bytes()!=subprocess.check_output(['git','-C',LIBC,'show','HEAD:'+str(p.relative_to(LIBC))]):raise ValueError('Original Libc changed')
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-libinfo-numeric-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    overlay=out/'original-ipv4-private-macros.h';overlay.write_text(private_macros(KERNEL_HEADER.read_text()))
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
        if scan!=actual:raise ValueError('Consumed dependency mismatch')
        headers.update(actual);records[label]=dict(scanned_sha256=scan,consumed_sha256=actual);return obj
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/06-si_getaddrinfo-compile.stdout'))
    target=old[:old.index('-MD')]+['-include',str(overlay),'-I',str(LIBC/'fbsdcompat'),'-include',str(LIBC/'fbsdcompat/_fbsd_compat_.h')]
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined']
    numeric_source=SOURCE/'lookup.subproj/si_getaddrinfo.c'
    objects=[compile(p,p.stem,target) for p in [numeric_source,*sources]]
    hostlibc=[compile(p,'host-'+p.stem,native) for p in sources]
    packing=[compile(SOURCE/'lookup.subproj'/p,'host-'+Path(p).stem,native) for p in ('ils.c','si_data.c')]
    callers={
        'file_parsers':['-DTEST_FILE_MODULE="'+str(SOURCE/'lookup.subproj/file_module.c')+'"'],
        'numeric':['-DTEST_NUMERIC_MODULE="'+str(numeric_source)+'"'],
    }
    native_results={}
    for name in callers:
        obj=compile(HARNESS[name],'host-'+name,native+callers[name]);binary=out/('host-'+name)
        run(native+[obj,*packing,*hostlibc,'-Wl,-dead_strip','-o',binary],'host-'+name+'-link')
        result=run([binary],'host-'+name+'-run')
        if result.stdout!=EXPECTED[name] or result.stderr:raise ValueError('Original parser native oracle mismatch: '+name)
        native_results[name]=result.stdout
    archive=out/'libapple-libinfo-numeric.a';run(['xcrun','ar','rcs',archive,*objects],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map');link.append(str(archive))
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Header drift')
    report=dict(profile='apple-libinfo600-original-numeric-and-account-parsers-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,target_archive=str(archive),
        original_sources=list(map(str,[numeric_source,*sources])),exact_private_kernel_macros=str(overlay),
        original_libinfo_configuration_unchanged=True,native_asan_ubsan_pass=True,native_stdout=native_results,
        native_service_boundary='Host libc/pthread/allocator; original source parsers, packing, retain/release and address conversions; no public account lookup or DNS',
        original_libc_inet_ntoa_static_storage=True,target_missing_symbols=missing,target_duplicate_symbols=duplicates,
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        previous_missing_count=len(base['target_missing_symbols']),target_link_complete=not result.returncode,
        target_executed=False,host_account_files_accessed=False,dns_executed=False,provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=report['closed_symbols'],remaining=len(missing),new=report['newly_reachable_symbols'],duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
