#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile original normal Apple arc4random and retain honest static gaps."""
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_entropy_probe as prior

ROOT,sha=prior.ROOT,prior.sha
BASE=ROOT/'build/rpi5/apple-entropy-api-x4zxvaug'
BASE_SHA='b488248ba8522edfd445d5b4d36bc0b260feef92171451d41d2af1dedc842c47'
LIBC=ROOT/'build/rpi5/apple-libc-main-candidate-20261013'
COMMIT='71bbe350ab79eef58113991d817ccc6165061a64'
SOURCE=LIBC/'gen/FreeBSD/arc4random.c'


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Diagnostic prerequisite changed')
    base=json.loads((BASE/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):pins.update(base[key])
    for path in (SOURCE,ROOT/'EXTERNAL_HEADERS/corecrypto/ccrng.h',ROOT/'tools/rpi5/user/ssh_runtime_build.h',
                 LIBC/'xcodescripts/generate_features.pl', LIBC/'Platforms/macosx/Makefile.inc', Path(__file__).resolve()):
        pins[str(path)]=sha(path)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Input drift: '+name)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-arc4random-normal-audit-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={}
    def run(args,label,allowed=False,environment=None):
        args=list(map(str,args));result=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=60,
            env=None if environment is None else dict(os.environ, **environment))
        (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
        commands.append(dict(command=args,cwd=str(ROOT),returncode=result.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr')),environment_overrides=environment or {}))
        if result.returncode and not allowed:raise ValueError(label+': '+result.stderr[-5000:])
        return result
    if run(['git','-C',LIBC,'rev-parse','HEAD'],'libc-revision').stdout.strip()!=COMMIT:raise ValueError('Apple Libc revision differs')
    if run(['git','-C',LIBC,'show','HEAD:gen/FreeBSD/arc4random.c'],'original-source').stdout!=SOURCE.read_text():
        raise ValueError('Original Apple source modified')
    if (LIBC/'Platforms/macosx/Makefile.arm64.inc').exists():raise ValueError('Generator platform selection changed')
    run(['/usr/bin/perl',LIBC/'xcodescripts/generate_features.pl'],'generate-original-features',environment={
        'ARCHS':'arm64','VARIANT_PLATFORM_NAME':'macosx','SRCROOT':str(LIBC),'DERIVED_FILES_DIR':str(out/'derived')})
    overlay=out/'include';overlay.mkdir();installations={}
    command=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/source-compile.stdout'))
    flags=command[:command.index('-MD')]+['-I'+str(overlay),'-I'+str(out/'derived/arm64'),'-I'+str(LIBC/'darwin'),'-I'+str(LIBC/'include'),
        '-I'+str(LIBC),'-I'+str(ROOT/'libkern'),'-idirafter',str(ROOT/'EXTERNAL_HEADERS'),
        '-include',str(ROOT/'tools/rpi5/user/ssh_runtime_build.h')]
    if any('VARIANT_STATIC' in f for f in flags):raise ValueError('Normal corecrypto path required, not RC4')
    for iteration in range(8):
        scan=run(flags+['-M','-MG',SOURCE],f'closure-scan-{iteration}',True)
        if scan.returncode:break
        added=[]
        for name in shlex.split(scan.stdout.replace('\\\n',' ').partition(':')[2]):
            rel=Path(name)
            if rel.is_file() or rel.is_absolute() or '..' in rel.parts:continue
            candidates=[root/rel for root in (ROOT/'osfmk',ROOT/'bsd') if (root/rel).is_file()]
            if len(candidates)!=1:continue
            original=candidates[0];dest=overlay/rel;dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(original.read_bytes());pins[str(original)]=sha(original)
            installations[str(dest)]=dict(source=str(original),sha256=sha(original));added.append(name)
        if not added:break
    else:raise ValueError('Original header installation bound exceeded')
    dependency=run(flags+['-M',SOURCE],'header-scan',True)
    result=None;imports=[];missing=[];consumed={};link_attempted=False
    if not dependency.returncode:
        def deps(raw):
            return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(raw.replace('\\\n',' ').partition(':')[2])}
        headers=deps(dependency.stdout);obj=out/'apple-arc4random.o'
        result=run(flags+['-MD','-MF',out/'apple-arc4random.d','-c',SOURCE,'-o',obj],'target-compile',True)
        if (out/'apple-arc4random.d').is_file():
            consumed=deps((out/'apple-arc4random.d').read_text())
            if consumed!=headers:raise ValueError('Consumed headers changed, including failed compilation')
        if not result.returncode:
            run(flags+['-E',SOURCE],'target-preprocessed')
            imports=run(['xcrun','nm','-ju',obj],'target-imports').stdout.splitlines()
            run(['xcrun','llvm-objdump','--disassemble',obj],'target-disassembly')
            link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/rng-force-link.stdout')))
            link[link.index('-o')+1]=str(out/'NOT_RUN_randbytes_link')
            link[link.index('-map')+1]=str(out/'randbytes.map');link += [str(obj)]
            linked=run(link,'randbytes-target-link',True);link_attempted=True
            missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
            uniform=list(link);uniform[uniform.index('-o')+1]=str(out/'NOT_RUN_uniform_link')
            uniform[uniform.index('-map')+1]=str(out/'uniform.map');uniform+=['-u','_arc4random_uniform']
            linked_uniform=run(uniform,'uniform-target-link',True)
            uniform_missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked_uniform.stderr,re.M)))
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Header drift')
    report=dict(profile='original-apple-normal-arc4random-link-audit-v1',current_libc_commit=COMMIT,
        source_inputs_sha256=pins,headers_sha256=headers,commands=commands,
        original_header_installations=installations,
        original_source_modified=False,variant_static_selected=False,rc4_fallback_selected=False,
        actual_consumed_headers_sha256=consumed,link_attempted=link_attempted,
        compile_complete=result is not None and result.returncode==0,object_imports=imports,
        randbytes_missing=missing,uniform_missing=locals().get('uniform_missing',[]),
        compile_diagnostics=[] if result is None else [line for line in result.stderr.splitlines() if 'error:' in line],
        gap_lists_valid_only_when_link_attempted=True,
        incompatible_kernel_logging_header_is_not_user_provider=True,
        private_corecrypto_implementation_present=False,ccrng_adapter_implemented=False,
        applicable_ccrng_license_header=str(ROOT/'EXTERNAL_HEADERS/corecrypto/ccrng.h'),
        entropy_qualified=False,live_keys=False,pi_executed=False,installed=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'package':str(out),'compile_complete':report['compile_complete'],
        'imports':imports,'randbytes_missing':missing,'uniform_missing':report['uniform_missing']},indent=2))
    return out,report


if __name__=='__main__':build()
