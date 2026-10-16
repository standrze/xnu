#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compile original Apple-distributed OpenSSH dependency units, never install.

Apple config.h stays byte-identical, including WITH_OPENSSL/PAM/sandbox.
Public OpenSSL headers are compile inputs only, not a crypto implementation.
The archive/provider inventory is NOT a closed Pi ssh/sshd runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
UPSTREAM=ROOT/'build/rpi5/apple-openssh-candidate-20261013'
COMMIT='f386b2e948280f6ecac875329c0b56020821d558'
SOURCE=UPSTREAM/'openssh'
OPENSSL=Path('/opt/homebrew/opt/openssl@3/include').resolve()
UNITS=('sshbuf.c','sshbuf-getput-basic.c','ssherr.c','openbsd-compat/explicit_bzero.c',
    'openbsd-compat/freezero.c','openbsd-compat/recallocarray.c','misc.c','log.c','xmalloc.c',
    'match.c','fatal.c','cleanup.c')
CAPSULE=ROOT/'experiments/darwin-container/userland/build/zsh-working-2026-10-12/archives'
ARCHIVES={
    CAPSULE/'apple-runtime/libapple-runtime.a':'bdde2c3a6ac9d32a42122196fc8c96f7a947c22379487ed820b948d77c82d6d5',
    CAPSULE/'apple-posix/libapple-posix.a':'ea3c839783d4e9f20b3a2104885524f8d09dc036a8d4cfd4513feb45a1db58ea',
    CAPSULE/'apple-libc-leaf/libapple-libc-leaf.a':'3a4be64367ef9db5471acbcf8555958e0c8c0ca8f24eed158170cac34c685546'}


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def read(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30).strip()


def symbols(path,defined):
    args=['xcrun','nm','-gjU' if defined else '-gju',str(path)]
    return {row.strip() for row in read(args).splitlines() if row.startswith('_') and not any(c.isspace() for c in row)}


def source_pins():
    if read(['git','-C',UPSTREAM,'rev-parse','HEAD'])!=COMMIT or read(['git','-C',UPSTREAM,'status','--porcelain','--untracked-files=all']):
        raise ValueError('Pinned pristine Apple OpenSSH checkout required')
    paths=[UPSTREAM/name for name in read(['git','-C',UPSTREAM,'ls-files']).splitlines()]
    paths.extend((Path(__file__).resolve(),ROOT/'tools/rpi5/tests/apple_ssh_buffers_host.c',
        ROOT/'tools/rpi5/tests/test_apple_ssh_buffers.py',*ARCHIVES))
    for p,pin in ARCHIVES.items():
        if sha(p)!=pin:raise ValueError('Preserved static runtime archive changed: '+str(p))
    return {str(p):sha(p) for p in paths}


def build():
    captured=source_pins();out=Path(tempfile.mkdtemp(prefix='apple-ssh-buffers-',dir=ROOT/'build/rpi5'))
    clang=Path(read(['xcrun','--find','clang']));sdk=Path(read(['xcrun','--sdk','macosx','--show-sdk-path']))
    tools={n:dict(path=read(['xcrun','--find',n])) for n in ('clang','ar','nm')}
    for row in tools.values():row['sha256']=sha(Path(row['path']))
    common=[str(clang),'-isysroot',str(sdk),'-I',str(OPENSSL),'-I',str(SOURCE),
        '-D_FORTIFY_SOURCE=0','-fno-builtin','-fno-stack-protector','-Wall','-Wextra',
        '-Wno-unused-parameter','-Werror']
    commands=[];objects=[];headers={}
    def execute(args,label,expected=(0,)):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=60)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        commands.append(dict(command=args,returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode not in expected:raise ValueError('SSH dependency build failed: '+str(out/(label+'.stderr')))
        return r.stdout
    for index,name in enumerate(UNITS):
        source=SOURCE/name;obj=out/(str(index)+'-'+source.stem+'.o');dep=out/(str(index)+'.d')
        execute(common+['-target','arm64-apple-darwin','-mcpu=cortex-a76','-ffreestanding','-O2',
            '-MD','-MF',dep,'-c',source,'-o',obj],str(index)+'-target')
        data=obj.read_bytes()
        if data[:4]!=b'\xcf\xfa\xed\xfe' or int.from_bytes(data[4:8],'little')!=0x100000c or int.from_bytes(data[12:16],'little')!=1:
            raise ValueError('Expected real thin ARM64 Mach-O dependency object')
        objects.append(obj)
        for value in shlex.split(dep.read_text().replace('\\\n',' ').partition(':')[2]):
            p=Path(value).resolve();headers[str(p)]=sha(p)
    archive=out/'libapple-openssh-buffers.a'
    execute(['xcrun','ar','rcs',archive,*objects],'archive')
    definitions=set().union(*(symbols(p,True) for p in objects))
    references=set().union(*(symbols(p,False) for p in objects))
    external=references-definitions
    providers={str(p):sorted(symbols(p,True)) for p in ARCHIVES}
    available=set().union(*(set(v) for v in providers.values()))
    # A name in an archive is only a possible provider; not its transitive
    # closure, calling-convention/service correctness or actual linked code.
    inventory=dict(external_symbols=sorted(external),potential_runtime_providers=sorted(external&available),
        absent_from_selected_runtime_archives=sorted(external-available),
        provider_scope='Name inventory only, not transitive static linkage or Pi ABI/service proof')
    native=[]
    for index,name in enumerate(UNITS):
        obj=out/(str(index)+'-native.o')
        execute(common+['-O1','-g','-fsanitize=address,undefined','-c',SOURCE/name,'-o',obj],str(index)+'-native')
        native.append(obj)
    harness=ROOT/'tools/rpi5/tests/apple_ssh_buffers_host.c';program=out/'ssh-buffer-host-test'
    execute(common+['-O1','-g','-fsanitize=address,undefined',harness,*native,'-Wl,-dead_strip','-o',program],'native-link')
    result=execute([program],'native-run').strip()
    if result!='APPLE_OPENSSH_BUFFERS_HOST_PASS ORIGINAL_SIGNAL_LOG_ALLOC_COMPAT_LINKED=1 NO_NETWORK=1':
        raise ValueError('Original SSH buffer host checks did not pass')
    execute([program,'--low-max-reset'],'native-low-max-reset',expected=(-11,))
    edge_return=commands[-1]['returncode']
    if source_pins()!=captured or any(sha(Path(n))!=v for n,v in headers.items()):raise ValueError('SSH build inputs changed')
    generated={str(p):sha(p) for p in out.iterdir() if p.is_file()}
    report=dict(profile='apple-openssh-buffer-dependencies-v1',upstream_url='https://github.com/apple-oss-distributions/OpenSSH',
        upstream_commit=COMMIT,version_header=(SOURCE/'version.h').read_text(),apple_config_unchanged=True,
        openssl_policy_unchanged=True,pam_and_sandbox_policy_unchanged=True,source_units=list(UNITS),
        apple_xcode_extra_integration_macros_enabled=False,
        tool_identity=tools,sdk=str(sdk),public_openssl_headers=str(OPENSSL),
        warning_policy='Wall/Wextra/Werror with the original configure.ac unused-parameter exception; no source patch',
        openssl_headers_not_crypto_implementation=True,source_inputs_sha256=captured,headers_sha256=headers,
        generated_sha256=generated,commands=commands,archive=str(archive),archive_sha256=sha(archive),
        target_cpu='cortex-a76',actual_arm64_objects=True,host_test_stdout=result,
        host_test_uses_native_libsystem_and_sanitizers=True,stub_functions_added=False,
        fatal_corruption_paths_exercised=True,
        known_original_low_max_reset_failure=dict(returncode=edge_return,signal='SIGSEGV',fixed=False,
            sequence='sshbuf_new -> set_max_size(16) -> reset -> len; reset grows alloc to initial size above retained max',
            scope='Local original-code API/invariant failure; not a remote exploitability or security-severity claim'),
        selected_archive_dependency_inventory=inventory,providers=providers,
        full_ssh_or_sshd_built=False,pi_static_runtime_closed=False,crypto_runtime_linked=False,
        pi_executed=False,installed=False,ethernet_or_ssh_proven=False,
        vm_sources_or_artifacts_modified=False,root_or_kernel_changed=False,
        scope='Original dependency archive and explicit native host buffer tests; not SSH transport/crypto/server, target static closure or Pi execution')
    with (out/'manifest.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();r=build()
    print(json.dumps({k:r[k] for k in ('archive','archive_sha256','upstream_commit','host_test_stdout','selected_archive_dependency_inventory')},indent=2))
