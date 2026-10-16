#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Close genuine option parsing/error/secure memory in the full SSH link."""
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
from tools.rpi5 import audit_apple_ssh_full_client as previous

ROOT, sha = previous.ROOT, previous.sha
BASE=ROOT/'build/rpi5/apple-ssh-full-client-3xbnfnp5'
BASE_SHA='0d65015d2d1c4f7d33a4ab45789949df0fe72bf1c518e2c64d096c898524d1c8'
LIBC=ROOT/'build/rpi5/apple-libc-main-candidate-20261013'
LIBC_COMMIT='71bbe350ab79eef58113991d817ccc6165061a64'
UNITS=('stdlib/FreeBSD/getopt.c','stdlib/FreeBSD/strtonum.c')
REUSED=(ROOT/'build/rpi5/apple-ssh-packet-leaves-we7s8n0w/apple-timingsafe-target.o',
        ROOT/'build/rpi5/apple-ssh-probe-v2-1tmwow6z/5-memset_s.o')
RENAMES=['-D'+s+'=fixture_'+s for s in ('getopt','opterr','optind','optopt','optreset','optarg','strtonum')]
EXPECTED='APPLE_SSH_CLIENT_LEAVES PASS GETOPT_GROUPS=8 STRTONUM_CASES=15 HOST_SERVICES_ONLY\n'
CLOSED={'_getopt','_optarg','_optind','_optreset','_strtonum','_memset_s','_timingsafe_bcmp'}


def categories(missing):
    groups={
        'enabled_gss_kerberos_integration':set(),
        'enabled_zlib_compression':set(),
        'dynamic_loader_pkcs11_crypto_engine':set(),
        'account_resolver_libinfo':set(),
        'locale_multibyte_time':set(),
        'socket_syscall_and_process':set(),
        'random_api':set(),
        'libc_text_files_logging':set(),
    }
    gss={n for n in missing if n.startswith(('_gss_','_GSS_'))}
    explicit={
        'enabled_gss_kerberos_integration':gss,
        'enabled_zlib_compression':{'_deflate','_deflateEnd','_deflateInit_','_inflate','_inflateEnd','_inflateInit_'},
        'dynamic_loader_pkcs11_crypto_engine':{'_dlopen','_dlclose','_dlsym','_dlerror'},
        'account_resolver_libinfo':{'___res_9_state','_res_9_dn_expand','_res_9_init','_res_9_query',
            '_h_errno','_freeaddrinfo','_freeifaddrs','_gai_strerror','_getaddrinfo','_getifaddrs',
            '_getnameinfo','_getpwnam','_getpwuid','_getservbyname','_initgroups','_si_destination_compare'},
        'locale_multibyte_time':{'_clock_gettime','_localtime_r','_mbtowc','_nl_langinfo','_setlocale','_wcwidth',
            '_isalnum','_isalpha','_isblank','_iscntrl','_isdigit','_isgraph','_islower','_isprint','_ispunct','_isspace','_isupper','_isxdigit'},
        'socket_syscall_and_process':{'_accept','_bind','_connect','_listen','_getpeereid','_getpeername',
            '_getsockname','_getsockopt','_setsockopt','_shutdown','_socketpair','_recvmsg','_sendmsg','_pselect',
            '_daemon','_execl','_execlp','_execv','_waitpid','_raise','_system','_pclose','_popen'},
        'random_api':{'_arc4random','_arc4random_uniform'},
    }
    for n in missing:
        matched=[k for k,v in explicit.items() if n in v]
        if len(matched)>1:raise ValueError('Ambiguous provider classification')
        groups[matched[0] if matched else 'libc_text_files_logging'].add(n)
    return {k:sorted(v) for k,v in groups.items()}


def build():
    if sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen full-client audit changed')
    base=json.loads((BASE/'manifest.json').read_text());pins={str(BASE/'manifest.json'):BASE_SHA}
    for k in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for name,digest in base[k].items():
            if name in pins and pins[name]!=digest:raise ValueError('Conflicting pin')
            pins[name]=digest
    commit=subprocess.check_output(['git','-C',str(LIBC),'rev-parse','HEAD'],text=True).strip()
    if commit!=LIBC_COMMIT:raise ValueError('Wrong Apple source commit')
    for n in UNITS:
        source=LIBC/n
        if subprocess.check_output(['git','-C',str(LIBC),'show','HEAD:'+n])!=source.read_bytes():
            raise ValueError('Original Apple source modified')
        pins[str(source)]=sha(source)
    harness=ROOT/'tools/rpi5/tests/ssh_client_leaves_host.c'
    adornment=ROOT/'tools/rpi5/user/ssh_runtime_build.h'
    for p in (Path(__file__).resolve(),harness,adornment,*REUSED):
        if str(p) in pins and pins[str(p)]!=sha(p):raise ValueError('Reused source/object changed')
        pins[str(p)]=sha(p)
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input drift: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-client-leaves-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[];headers={};records={}
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=90)
        for k in ('stdout','stderr'):(out/(label+'.'+k)).write_text(getattr(r,k))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr)
        return r
    def deps(text):
        return {str(Path(p).resolve()):sha(Path(p).resolve()) for p in shlex.split(text.replace('\\\n',' ').partition(':')[2])}
    def compile(flags,source,label):
        before=deps(run(flags+['-M',source],label+'-scan').stdout)
        obj,dep=out/(label+'.o'),out/(label+'.d')
        run(flags+['-MD','-MF',dep,'-c',source,'-o',obj],label+'-compile')
        consumed=deps(dep.read_text())
        if consumed!=before:raise ValueError('Header closure differs')
        headers.update(before);records[label]=dict(scanned_sha256=before,consumed_sha256=consumed)
        return obj
    old=next(c['command'] for c in base['commands'] if c['stdout'].endswith('/000-ssh_api-compile.stdout'))
    target=old[:old.index('-MD')]+['-I',str(LIBC/'fbsdcompat'),'-I',str(LIBC/'darwin'),
        '-idirafter',str(LIBC/'include'),'-include',str(adornment)]
    native=[s for s in target if s not in ('-ffreestanding','-mcpu=cortex-a76')]
    i=native.index('-target');del native[i:i+2]
    native+=['-g','-O1','-fsanitize=address,undefined']+RENAMES
    objects=[compile(target,LIBC/n,'target-'+Path(n).stem) for n in UNITS]
    hosts=[compile(native,LIBC/n,'host-'+Path(n).stem) for n in UNITS]
    host=out/'original-leaves-host'
    run(native+[harness,*hosts,'-o',host],'host-link')
    result=run([host],'host-run')
    if result.stdout!=EXPECTED or result.stderr:raise ValueError('Original option/error oracle failed')
    archive=out/'libapple-ssh-client-leaves.a'
    run(['xcrun','ar','rcs',archive,*objects,*REUSED],'archive')
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    link.append(str(archive));r=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    added=set(missing)-set(base['target_missing_symbols'])
    if not r.returncode or duplicates or set(base['target_missing_symbols'])-set(missing)!=CLOSED or added!={'_strtoll'}:
        raise ValueError('Unexpected full-link closure change: '+r.stderr)
    run(['xcrun','nm','-g',archive],'archive-symbols')
    verify()
    for n,h in headers.items():
        if sha(n)!=h:raise ValueError('Consumed input drift')
    report=dict(profile='original-apple-full-ssh-option-leaves-v1',source_inputs_sha256=pins,
        headers_sha256=headers,dependency_records=records,commands=commands,current_libc_commit=commit,
        original_sources_unchanged=True,original_openssh_config_unchanged=True,
        host_stdout=result.stdout,host_services_not_target=True,native_asan_ubsan_pass=True,
        native_symbol_namespacing_only=RENAMES,target_archive=str(archive),reused_objects=list(map(str,REUSED)),
        previous_missing_count=len(base['target_missing_symbols']),closed_symbols=sorted(CLOSED),
        newly_reachable_dependencies=sorted(added),strtonum_transitive_service_closed=False,
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,target_link_complete=False,
        remaining_provider_groups=categories(missing),
        configuration_scope='GSS/Kerberos, zlib and PKCS11 remain enabled in unchanged config.h; no PAM/BSM server units linked; Apple xcconfig keychain/launchd/framework extras not enabled',
        real_original_full_client_link=True,all_original_client_units_compiled=base['all_original_client_units_compiled'],
        target_executed=False,live_keys=False,network_access=False,entropy_qualified=False,
        provider_stubs=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=sorted(CLOSED),remaining=len(missing)),indent=2))
    return out,report


if __name__=='__main__':build()
