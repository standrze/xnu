#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Real current Apple fortify providers, explicit Pi policy and strcpy repair.

Compile complete secure TUs. Only strcpy moves validation ahead of its copy.
The public crash header boundary selects exact original declarations/macros;
the previously checked genuine Apple crash callback and caller trap remain.
No original OpenSSH/Libinfo consumer flags or frozen artifacts are changed.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_runtime_api_fragments as api

ROOT,sha,LIBC=api.ROOT,api.sha,api.LIBC
BASE=ROOT/'build/rpi5/pi-libinfo-files-wj7_spx1'
BASE_SHA='544943437813436add20988cbbca221f4aafb37da3b6815244a0d2c664a5bc9e'
APIS=ROOT/'build/rpi5/apple-runtime-api-fragments-bg8jq8u2'
APIS_SHA='6c858250877f14585768a8d3beb77b44a0c321c68227fc8cfe3934df88193ade'
BLOCKS=ROOT/'build/rpi5/apple-blocks-runtime-ga1_x5sg'
BLOCKS_SHA='447d6841cc058fd09ad8ef39ed9e338db364c88850ad207b7df4e56e709f49f5'
HARNESS=ROOT/'tools/rpi5/tests/apple_fortify_host.c'
UNITS=('memcpy_chk','memmove_chk','memset_chk','strcpy_chk','strlcpy_chk','strlcat_chk','snprintf_chk','sprintf_chk','chk_fail')
NAMES=('__memcpy_chk','__memmove_chk','__memset_chk','__strcpy_chk','__strlcpy_chk','__strlcat_chk',
       '__snprintf_chk','__sprintf_chk','__snprintf_object_size_chk','__sprintf_object_size_chk',
       '__chk_fail_overflow','__chk_fail_overlap','__chk_overlap','__chk_init','__chk_assert_no_overlap',
       '_os_crash','_os_crash_callback')
EXPECTED='APPLE_FORTIFY PASS VALID=12 FATAL=14 STRCPY_PREWRITE=1 ORIGINAL_CALLER_TRAP=1\n'


def strcpy_overlay(text):
    old='  // stpcpy returns a pointer to the \\0\n  size_t len = stpcpy(dest, src) - dest + 1;'
    new=('  /* Pi correctness overlay: validate before any destination write. */\n'
         '  size_t len = strlen(src) + 1;')
    if text.count(old)!=1 or text.count('  return dest;')!=1:
        raise ValueError('Original strcpy correction boundary changed')
    return text.replace(old,new).replace('  return dest;','  stpcpy(dest, src);\n  return dest;')


def build():
    pins={};reports={}
    for path,digest in ((BASE,BASE_SHA),(APIS,APIS_SHA),(BLOCKS,BLOCKS_SHA)):
        if sha(path/'manifest.json')!=digest:raise ValueError('Frozen input receipt changed')
        pins[str(path/'manifest.json')]=digest;r=json.loads((path/'manifest.json').read_text());reports[path]=r
        for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in r.get(k,{}).items():
                if n in pins and pins[n]!=h:raise ValueError('Conflicting predecessor pin')
                pins[n]=h
    for path in (Path(__file__).resolve(),Path(api.__file__).resolve(),HARNESS):pins[str(path)]=sha(path)
    original_paths=[LIBC/'secure'/(n+'.c') for n in UNITS]+[LIBC/'secure/secure.h',LIBC/'os/assumes.h']
    for p in original_paths:
        if subprocess.check_output(['git','-C',str(LIBC),'show','HEAD:'+str(p.relative_to(LIBC))])!=p.read_bytes():
            raise ValueError('Original current Apple source drift')
        pins[str(p)]=sha(p)
    if subprocess.check_output(['git','-C',str(LIBC),'rev-parse','HEAD'],text=True).strip()!=api.COMMITS[LIBC]:
        raise ValueError('Wrong original current Apple commit')
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-fortify-runtime-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);overlay=out/'overlay';(overlay/'os').mkdir(parents=True)
    original=(LIBC/'secure/strcpy_chk.c').read_text();fixed=overlay/'strcpy_chk.c';fixed.write_text(strcpy_overlay(original))
    fragment=api.fragments();(overlay/'selected-apis.h').write_text(fragment['header'])
    crash=overlay/'selected-crash.c';crash.write_text(fragment['crash'])
    h=(LIBC/'os/assumes.h').read_text();macro='#define os_crash(msg) __os_crash_simple(msg)\n'
    if h.count(macro)!=1:raise ValueError('Original single-message crash macro changed')
    (overlay/'os/assumes.h').write_text(h[:h.index('*/')+2]+'\n#include "selected-apis.h"\n'+macro)
    commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    def deps(text):return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,source,label):
        scan=deps(run(flags+['-M',source],label+'-scan').stdout);obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile');actual=deps(dep.read_text())
        if actual!=scan:raise ValueError('Actual compiler dependency mismatch')
        headers.update(actual);records[label]=dict(scanned_sha256=scan,consumed_sha256=actual);return obj
    # SDK public ABI plus the exact selected Apple crash macro/header boundary.
    old=next(c['command'] for c in reports[BASE]['commands'] if c['stdout'].endswith('/target-ils-compile.stdout'))
    target=[old[0],'-isysroot',old[old.index('-isysroot')+1],'-target','arm64-apple-darwin',
            '-mcpu=cortex-a76','-ffreestanding','-O2','-fno-stack-protector','-fno-builtin',
            '-std=gnu99','-Wall','-Wextra','-Wno-unused-parameter','-DPR_13085474_CHECK=0',
            '-I',str(overlay),'-I',str(LIBC/'secure')]
    native=[x for x in target if x not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined']+['-D'+n+'=fixture_'+n for n in NAMES]
    objs=[];host=[]
    for n in UNITS:
        source=fixed if n=='strcpy_chk' else LIBC/'secure'/(n+'.c')
        objs.append(compile_(target,source,'target-'+n));host.append(compile_(native,source,'native-'+n))
    host.append(compile_(native,crash,'native-crash'));caller=compile_(native,HARNESS,'native-caller')
    executable=out/'host-fortify';run(native+[caller,*host,'-Wl,-map,'+str(out/'host.map'),'-o',executable],'native-link')
    result=run([executable],'native-run')
    if (result.stdout,result.stderr)!=(EXPECTED,''):raise ValueError('Native fortify oracle failed')
    pristine=compile_(native,LIBC/'secure/strcpy_chk.c','native-original-strcpy')
    negative=out/'host-original-negative';oldhost=[pristine if p.name=='native-strcpy_chk.o' else p for p in host]
    run(native+[caller,*oldhost,'-o',negative],'negative-link')
    negative_result=run([negative,'original-overflow'],'negative-run',True)
    if not negative_result.returncode or 'AddressSanitizer: heap-buffer-overflow' not in negative_result.stderr:
        raise ValueError('Original pre-validation overflow regression was not reproduced')
    archive=out/'libapple-fortify.a';run(['xcrun','ar','rcs',archive,*objs],'archive')
    run(['xcrun','nm','-g',archive],'symbols');run(['xcrun','llvm-objdump','-d','-r',*objs],'disassembly')
    link=list(next(c['command'] for c in reports[BASE]['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    additions=[archive,APIS/'libapple-selected-runtime-apis.a',BLOCKS/'libapple-blocks-runtime.a']
    result=run(link+additions,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    if not result.returncode or duplicates:raise ValueError('Unexpected full-client link result')
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Consumed header/source drift')
    report=dict(profile='pi-current-apple-fortify-prewrite-strcpy-v1',source_inputs_sha256=pins,headers_sha256=headers,
        dependency_records=records,commands=commands,target_archive=str(archive),added_archives=list(map(str,additions)),
        original_libc_commit=api.COMMITS[LIBC],whole_original_secure_translation_units=True,original_units=list(UNITS),
        modified_original_units=['strcpy_chk'],strcpy_bounds_and_overlap_before_copy=True,
        original_negative_heap_overflow_observed=True,original_os_crash_callback_and_caller_trap=True,
        private_header_boundary='exact selected original os_crash macro, declarations and caller trap; no implementation stub',
        original_supported_overlap_policy='PR_13085474_CHECK=0: never disable checks based on macOS SDK version',
        original_memcpy_overlap_policy_retained=True,universal_constructor_or_overlap_arithmetic_safety_claimed=False,
        native_stdout=EXPECTED,native_asan_ubsan_pass=True,native_runtime_boundary=['host Libc strings/formatters/fork'],
        previous_missing_count=len(reports[BASE]['target_missing_symbols']),target_missing_symbols=missing,
        closed_symbols=sorted(set(reports[BASE]['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(reports[BASE]['target_missing_symbols'])),
        target_duplicate_symbols=duplicates,target_link_complete=False,target_executed=False,
        original_openssh_config_unchanged=True,accepted_runtime_modified=False,live_keys=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),manifest_sha256=sha(out/'manifest.json'),closed=report['closed_symbols'],
        new=report['newly_reachable_symbols'],remaining=len(missing)),indent=2));return out,report


if __name__=='__main__':build()
