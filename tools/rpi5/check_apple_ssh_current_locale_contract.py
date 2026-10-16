#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Verify current locale ownership and native group; never run target Mach-O."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_locale_slice as old

ROOT,sha=old.ROOT,old.sha
PACKAGE=ROOT/'build/rpi5/apple-ssh-current-locale-ebd652yw'
PACKAGE_SHA='4c722fcbab48d012865d2071953cf3994d27e1220a8eacddac7adf23c0fd0395'


def build():
    if sha(PACKAGE/'manifest.json')!=PACKAGE_SHA:raise ValueError('Current locale ownership changed')
    owner=json.loads((PACKAGE/'manifest.json').read_text())
    group=Path(owner['current_locale_package'])
    report=json.loads((group/'manifest.json').read_text())
    pins={str(PACKAGE/'manifest.json'):PACKAGE_SHA}
    for document in (owner,report):
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for name,digest in document[key].items():
                if name in pins and pins[name]!=digest:raise ValueError('Conflicting closure')
                pins[name]=digest
    harness=ROOT/'tools/rpi5/tests/ssh_current_locale_host.c'
    for path in (Path(__file__).resolve(),harness,harness.with_name('ssh_locale_host.c')):
        pins[str(path)]=sha(path)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Input changed: '+name)
    verify()
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-current-locale-contract-',dir=ROOT/'build/rpi5'))
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
    link[link.index(str(old.START/'startup.o'))]=owner['startup_replacement_object']
    link[link.index(str(old.START/'private-apple-runtime.a'))]=owner['runtime_archive']
    link += [owner['target_archive']]
    forced=['strtoll','uselocale','mbtowc','wcwidth','isalnum','isalpha','isblank','iscntrl',
            'isdigit','isgraph','islower','isprint','ispunct','isspace','isupper','isxdigit',
            'tolower','toupper']
    for name in forced:link += ['-u','_'+name]
    linked=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    if duplicate:raise ValueError('Duplicate current provider')
    if not linked.returncode:
        run(['xcrun','nm','-u',out/'NOT_RUN_locale_contract'],'target-undefined')
        run(['xcrun','llvm-objdump','-d',out/'NOT_RUN_locale_contract'],'target-disassembly')
    symbols=set()
    for name in report['original_units']:
        text=(group/('target-'+Path(name).stem+'-symbols.stdout')).read_text()
        symbols.update(n[1:] for n in re.findall(r'^[0-9a-f]+ [A-Z] (_\S+)$',text,re.M))
    # These original files explicitly undefine public/deprecated macro names.
    # Keep their actual names consistent and hide them from host interposition.
    unrenamed=('__collate_load_error','wcwidth','sgetrune','sputrune','__sgetrune','__sputrune')
    for name in unrenamed:symbols.remove(name)
    rename=out/'native_names.h'
    rename.write_text('/* Native-only names, all original translation units unchanged. */\n'+
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
    for name in report['original_units']:
        stem=Path(name).stem
        objects.append(compile(native_flags('target-'+stem),old.LIBC/name,'native-'+stem))
    flags=native_flags('target-strtoll')
    obj=compile(flags,harness,'native-harness')
    native=out/'current-locale-host'
    run(flags+[obj,*objects,'-Wl,-dead_strip',
               *['-Wl,-unexported_symbol,_'+n for n in unrenamed],'-Wl,-map,'+str(out/'native.map'),
               '-o',native],'native-link')
    result=run([native],'native-run')
    expected=('APPLE_LOCALE PASS VECTORS=23 MODES=3 THREADS=4 ITERATIONS=2048 DESTRUCTORS=4 HOST_KEY_MAPPING_ONLY\n'
              'APPLE_CURRENT_LOCALE PASS CTYPES=3084 CASEMAPS=514 MBTOWC=6 WCWIDTH=4 C_LOCALE_APIS=10 HOST_SERVICES_ONLY\n')
    if result.stdout!=expected or result.stderr:raise ValueError('Unexpected current locale output')
    for arg,code in (('bad-expected',11),('bad-api',31)):
        if run([native,arg],'native-'+arg,True).returncode!=code:raise ValueError('Bad oracle not rejected')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Native input changed')
    target=out/'NOT_RUN_locale_contract'
    value=dict(profile='original-apple-current-locale-target-and-host-contract-v2',
        source_inputs_sha256=pins,headers_sha256=headers,dependency_records=records,
        commands=commands,target=str(target) if not linked.returncode else None,
        target_sha256=sha(target) if not linked.returncode else None,
        target_link_complete=not linked.returncode,target_missing_symbols=missing,
        target_duplicate_symbols=duplicate,target_forced_functions=forced,
        target_executed=False,target_locale_runtime_executed=False,not_full_ssh_client=True,
        native_asan_ubsan_pass=True,host_stdout=result.stdout,original_unit_count=len(objects),
        explicit_host_boundary='Reserved locale-key registration maps to host key; real host pthread, allocator, file, and crash services',
        original_translation_units_unchanged=True,production_startup_wires_real_xlocale_init=True,
        non_c_locale_files_tested=False,network_access=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),target=value['target_sha256'],missing=missing,host=result.stdout),indent=2))
    return out,value


if __name__=='__main__':build()
