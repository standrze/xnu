#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Whole current Apple daemon prerequisite, never a target process/service.

Normal bootstrap migration remains enabled. Missing genuine bootstrap services
stay linker errors; native Mach/process/signal/filesystem boundaries are spies.
No accepted runtime, configuration or original Apple translation unit is edited.
"""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_directory as preceding

ROOT, LIBC, sha = preceding.ROOT, preceding.LIBC, preceding.sha
BASE = ROOT/'build/rpi5/apple-ssh-directory-5vnm2xih'
BASE_SHA = 'a31b1f23788746c51ba590d5a560eb61155618fb49ffcdf95af0142d1b359cd9'
SOURCE = LIBC/'gen/FreeBSD/daemon.c'
HARNESS = ROOT/'tools/rpi5/tests/ssh_daemon_host.c'
TEST = ROOT/'tools/rpi5/tests/test_apple_ssh_daemon.py'
TRAP = ROOT/'build/rpi5/apple-ssh-socket-syscalls-n4wc59z7/generated/_setsid.s'
MASTER = ROOT/'bsd/kern/syscalls.master'
LIBC_COMMIT = preceding.LIBC_COMMIT
RENAMES = {n:'fixture_'+n for n in ('daemon','fork','setsid','sigaction','_exit','chdir',
    'open','dup2','close','bootstrap_parent','task_set_special_port',
    'mach_port_deallocate','bootstrap_port','mach_task_self_')}
EXPECTED = 'APPLE_DAEMON PASS CASES=176 WHOLE_CURRENT_TU BOOTSTRAP_ENABLED PROCESS_MACH_SIGNAL_FS_SPIES_ONLY\n'


def categories(symbols):
    groups = {
        'gss_kerberos': lambda n:n.startswith(('_gss_', '_GSS_')),
        'dyld': lambda n:n in ('_dlopen','_dlclose','_dlsym','_dlerror'),
        'resolver_libinfo': lambda n:n in ('___res_9_state','_res_9_dn_expand','_res_9_init','_res_9_query','_si_destination_compare'),
        'logging_notify': lambda n:n.startswith(('_os_log','__os_log','_notify_')) or n in ('_openlog','_closelog','_syslog$DARWIN_EXTSN','_vsyslog'),
        'stdio_file_abi': lambda n:n in ('_asprintf','_vasprintf','_sscanf','_getline','_perror','_popen','_pclose'),
        'time_notify': lambda n:n == '_localtime_r',
        'process_bootstrap': lambda n:n in ('_daemon','_bootstrap_parent','_bootstrap_port','_task_set_special_port'),
    }
    result={k:[] for k in groups}
    for name in symbols:
        found=[k for k,predicate in groups.items() if predicate(name)]
        if len(found)!=1:raise ValueError('Exact provider classification required '+name)
        result[found[0]].append(name)
    return result


def build():
    if sha(BASE/'manifest.json') != BASE_SHA:raise ValueError('Exact full40 predecessor required')
    base=json.loads((BASE/'manifest.json').read_text())
    pins={str(BASE/'manifest.json'):BASE_SHA,str(Path(__file__).resolve()):sha(__file__),
          str(SOURCE):sha(SOURCE),str(HARNESS):sha(HARNESS),str(TEST):sha(TEST),str(TRAP):sha(TRAP),str(MASTER):sha(MASTER)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in base[key].items():
            if name in pins and pins[name]!=digest:raise ValueError('Conflicting inherited input')
            pins[name]=digest
    if SOURCE.read_bytes()!=subprocess.check_output(['git','-C',LIBC,'show',LIBC_COMMIT+':gen/FreeBSD/daemon.c']):
        raise ValueError('Whole original daemon differs')
    tools={str(Path(subprocess.check_output(['xcrun','--find',n],text=True).strip()).resolve()):None
           for n in ('clang','ar','nm','ld','llvm-objdump')}
    tools[str(Path('/usr/bin/xcrun').resolve())]=None
    tools={n:sha(n) for n in tools};pins.update(tools)
    def verify():
        for name,digest in pins.items():
            if sha(name)!=digest:raise ValueError('Input drift '+name)
    verify()
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-daemon-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True)
    commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for stream in ('stdout','stderr'):(out/(label+'.'+stream)).write_text(getattr(r,stream))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-4500:])
        return r
    def deps(text):
        return {str(Path(n).resolve()):sha(Path(n).resolve()) for n in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile_(flags,path,label):
        before=deps(run([*flags,'-M',path],label+'-scan').stdout)
        dep,obj=out/(label+'.d'),out/(label+'.o')
        run([*flags,'-MD','-MF',dep,'-c',path,'-o',obj],label+'-compile')
        after=deps(dep.read_text())
        if before!=after:raise ValueError('Consumed dependency drift')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=after)
        return obj
    flag_manifest=json.loads(preceding.FLAGS.read_text())
    command=next(c['command'] for c in flag_manifest['commands'] if c['stdout'].endswith('/readpassphrase-compile.stdout'))
    flags=command[:command.index('-MD')]
    if any('VARIANT_PRE1050' in n for n in flags):raise ValueError('Normal bootstrap feature must stay enabled')
    obj=compile_(flags,SOURCE,'target-daemon')
    symbols=run(['xcrun','nm','-g',obj],'target-symbols').stdout
    imports=run(['xcrun','nm','-ju',obj],'target-undefined').stdout.splitlines()
    if '_daemon' not in symbols or not {'_bootstrap_parent','_bootstrap_port','_task_set_special_port'}<=set(imports):
        raise ValueError('Whole normal bootstrap daemon required')
    run(['xcrun','llvm-objdump','-d','-r',obj],'target-disassembly')
    if not re.search(r'^147\s+[^\n]*int setsid\(void\);',MASTER.read_text(),re.M) or \
            'SYSCALL_NONAME(setsid, 0, cerror_nocancel)' not in TRAP.read_text():
        raise ValueError('Original setsid syscall ABI required')
    assembly_doc=json.loads(preceding.SYSCALLS.read_text())
    template=next(c['command'] for c in assembly_doc['commands'] if c['stdout'].endswith('/bind-preprocess.stdout'))
    assembly=template[:template.index('-E')]
    before=deps(run([*assembly,'-M',TRAP],'setsid-scan').stdout)
    dep,asm,trap=out/'setsid.d',out/'setsid.s',out/'setsid.o'
    raw=run([*assembly,'-E','-P','-MD','-MF',dep,TRAP],'setsid-preprocess').stdout
    after=deps(dep.read_text())
    if before!=after:raise ValueError('Consumed syscall dependency drift')
    headers.update(before);records['setsid']=dict(scanned_sha256=before,consumed_sha256=after)
    asm.write_text(raw.replace('%%','\n').replace(';','\n'))
    run([assembly[0],'-target','arm64-apple-darwin','-mcpu=cortex-a76','-x','assembler','-c',asm,'-o',trap],'setsid-assemble')
    dis=run(['xcrun','llvm-objdump','-d','-r',trap],'setsid-disassembly').stdout
    if 'mov\tx16, #0x93' not in dis or 'svc\t#0x80' not in dis or \
            run(['xcrun','nm','-ju',trap],'setsid-undefined').stdout!='_cerror_nocancel\n':
        raise ValueError('Actual setsid trap/error owner differs')
    archive=out/'libapple-current-daemon.a';run(['xcrun','ar','rcs',archive,obj,trap],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    original_link=list(link)
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    linked=run([*link,archive],'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',linked.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",linked.stderr)))
    closed=sorted(set(base['target_missing_symbols'])-set(missing));added=sorted(set(missing)-set(base['target_missing_symbols']))
    if linked.returncode==0 or duplicate or closed!=['_daemon'] or added!=['_bootstrap_parent']:
        raise ValueError('Unexpected normal daemon closure delta '+repr((closed,added,duplicate)))
    native=[n for n in flags if n not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=undefined']
    host_obj=compile_([*native,*['-D'+k+'='+v for k,v in RENAMES.items()]],SOURCE,'host-daemon')
    caller=compile_(native,HARNESS,'host-caller')
    host=out/'daemon-host';run([*native,host_obj,caller,'-o',host],'host-link')
    good=run([host],'host-run')
    if (good.stdout,good.stderr)!=(EXPECTED,''):raise ValueError('Native daemon oracle differs')
    if run([host,'bad-expectation'],'host-negative',True).returncode!=37:raise ValueError('Negative oracle accepted')
    verify()
    for name,digest in headers.items():
        if sha(name)!=digest:raise ValueError('Consumed header changed')
    report=dict(profile='whole-current-apple-daemon-bootstrap-prerequisite-v1',source_inputs_sha256=pins,
        headers_sha256=headers,generated_sha256={},dependency_records=records,commands=commands,
        tools_sha256=tools,original_unit=str(SOURCE),original_libc_commit=LIBC_COMMIT,
        original_unit_unchanged=True,normal_bootstrap_migration_enabled=True,
        target_archive=str(archive),target_object=str(obj),target_object_imports=imports,
        original_setsid_syscall_number=147,original_setsid_error_policy='cerror_nocancel',
        target_setsid_object=str(trap),target_setsid_executed=False,
        target_missing_symbols=missing,target_duplicate_symbols=duplicate,closed_symbols=closed,
        newly_reachable_symbols=added,previous_missing_count=40,remaining_missing_count=len(missing),
        previous_provider_groups=categories(base['target_missing_symbols']),remaining_provider_groups=categories(missing),
        original_full_client_link_command=original_link,all176_original_client_inputs_unchanged=True,
        original_openssh_config_unchanged=True,accepted_runtime_modified=False,provider_stubs=False,
        native_asan_ubsan_pass=True,native_stdout=good.stdout,native_symbol_namespacing_only=RENAMES,
        native_process_mach_signal_filesystem_are_test_spies=True,
        original_fork_failure_leaves_sighup_ignored=True,original_bootstrap_failure_behavior_preserved=True,
        full_client_qualified=False,target_executed=False,target_daemon_executed=False,
        target_bootstrap_service_available=False,target_process_creation_qualified=False,
        formatting_next_slice='Private coherent current FILE implementation; never bind current internals to legacy FILE owners')
    report['generated_sha256']={str(p):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(output=str(out),manifest_sha256=sha(out/'manifest.json'),closed=closed,
        added=added,remaining=len(missing),native_cases=176),indent=2))
    return out,report


if __name__=='__main__':build()
