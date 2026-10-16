#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Force actual target providers live; run namespaced host locale contracts."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from tools.rpi5 import build_apple_ssh_locale_slice as old

ROOT,sha=old.ROOT,old.sha
PACKAGE=ROOT/'build/rpi5/apple-ssh-locale-slice-lu4cw5xx'


def build():
    report=json.loads((PACKAGE/'manifest.json').read_text())
    pins={str(PACKAGE/'manifest.json'):sha(PACKAGE/'manifest.json')}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in report[key].items():
            if name in pins and pins[name]!=digest:raise ValueError('Conflicting closure')
            pins[name]=digest
    harness=ROOT/'tools/rpi5/tests/ssh_locale_host.c'
    for path in (Path(__file__).resolve(),harness):pins[str(path)]=sha(path)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Input changed: '+name)
    verify()
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-locale-contract-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));p=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for suffix in ('stdout','stderr'):(out/(label+'.'+suffix)).write_text(getattr(p,suffix))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=p.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode and not allowed:raise ValueError(label+': '+p.stderr[-4000:])
        return p
    start=json.loads((old.START/'manifest.json').read_text())
    link=list(next(c['command'] for c in start['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_locale_contract')
    link[link.index('-map')+1]=str(out/'target.map')
    link[link.index(str(old.START/'startup.o'))]=report['objects']['startup-locale']
    link += [report['target_archive'],'-u','_strtoll','-u','_uselocale']
    linked=run(link,'target-link',True)
    if linked.returncode:raise ValueError('Forced actual locale target remains incomplete: '+linked.stderr)
    run(['xcrun','nm','-u',out/'NOT_RUN_locale_contract'],'target-undefined')
    run(['xcrun','llvm-objdump','-d',out/'NOT_RUN_locale_contract'],'target-disassembly')
    symbols=set()
    for name in old.UNITS:
        text=(PACKAGE/('target-'+Path(name).stem+'-symbols.stdout')).read_text()
        symbols.update(n[1:] for n in re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',text,re.M))
    # collate.c explicitly undefines this token before its global definition;
    # it is also a structure member. Hide the unused legacy global at link
    # time instead of creating mismatched field names through macro renaming.
    symbols.remove('__collate_load_error')
    rename=out/'native_names.h'
    rename.write_text('/* Host-only symbol isolation, no production source edits. */\n'+
        ''.join('#define '+n+' fixture_'+n+'\n' for n in sorted(symbols))+
        '#define pthread_key_init_np fixture_key_init_np\n')
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def native_flags(label):
        command=next(c['command'] for c in report['commands'] if c['stdout'].endswith('/'+label+'-compile.stdout'))
        flags=list(command[:command.index('-MD')]);i=flags.index('-target');del flags[i:i+2]
        flags=[f for f in flags if f not in ('-mcpu=cortex-a76','-ffreestanding')]
        return flags+['-O1','-g','-fsanitize=address,undefined','-include',str(rename)]
    def compile(flags,source,label):
        before=deps(run(flags+['-M',source],label+'-scan').stdout)
        obj=out/(label+'.o');dep=out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if before!=consumed:raise ValueError('Actual native dependency mismatch')
        records[label]=dict(scanned_sha256=before,consumed_sha256=consumed);headers.update(before)
        return obj
    objects=[]
    for name in old.UNITS:
        stem=Path(name).stem
        objects.append(compile(native_flags('target-'+stem),old.LIBC/name,'native-'+stem))
    flags=native_flags('target-strtoll')
    obj=compile(flags,harness,'native-harness')
    native=out/'locale-host'
    run(flags+[obj,*objects,'-Wl,-dead_strip',
               '-Wl,-unexported_symbol,___collate_load_error','-o',native],'native-link')
    result=run([native],'native-run')
    expected='APPLE_LOCALE PASS VECTORS=23 MODES=3 THREADS=4 ITERATIONS=2048 DESTRUCTORS=4 HOST_KEY_MAPPING_ONLY\n'
    if result.stdout!=expected or result.stderr:raise ValueError('Unexpected locale oracle output')
    bad=run([native,'bad-expected'],'native-negative',True)
    if bad.returncode!=11:raise ValueError('Negative oracle failed to reject bad expectation')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Native consumed input changed')
    value=dict(profile='original-apple-strtoll-locale-target-and-host-contract-v1',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        commands=commands,target=str(out/'NOT_RUN_locale_contract'),
        target_sha256=sha(out/'NOT_RUN_locale_contract'),target_link_complete=True,not_full_ssh_client=True,
        target_executed=False,target_locale_runtime_executed=False,
        native_asan_ubsan_pass=True,host_stdout=result.stdout,
        explicit_host_boundary='Only reserved key registration maps to a fresh host pthread key; host pthread/allocator/locks used',
        original_translation_units_unchanged=True,production_startup_wires_real_xlocale_init=True,
        non_c_locale_files_tested=False,network_access=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),target=value['target_sha256'],host=result.stdout),indent=2))
    return out,value


if __name__=='__main__':build()
