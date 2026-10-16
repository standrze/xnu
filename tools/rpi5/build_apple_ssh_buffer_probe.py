#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Actual static ARM64 link with real preserved adapters; never run/install Pi code."""
import argparse
import difflib
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
try:
    from . import build_apple_ssh_buffer_reset as reset
except ImportError:
    import build_apple_ssh_buffer_reset as reset
previous=reset.previous
ROOT=reset.ROOT
BASE=ROOT/'build/rpi5/apple-ssh-reset-7j7hbjqx'
BASE_SHA='9cb33eed73cb696a2f3904d86c86dfd3568417a2e8008602fc9f065851461cd9'
ABI=ROOT/'experiments/darwin-container/userland/build/darwin-abi-diagnostic-2/libdarwin-static-abi.a'
ABI_SHA='3fb14dc9e03b5335b73eb0525f61fae65669da2ba46d740715b93add74130c3d'
SOURCE=ROOT/'tools/rpi5/user/sshbufferprobe.c'
USERLAND=ROOT/'experiments/darwin-container/userland'
LOCK=USERLAND/'apple-runtime.sources.lock.json'
ADORNMENTS=ROOT/'tools/rpi5/user/ssh_runtime_build.h'
CALLS=ROOT/'tools/rpi5/user/ssh_runtime_calls.S'
ENTRY=USERLAND/'runtime/network_command_start.c'
APPLE_UNITS=(('Libc-167','gen.subproj/raise.c'),('Libc-167','gen.subproj/syslog.c'),
    ('Libc-167','compat43.subproj/send.c'),('Libc-391','string/FreeBSD/strsignal.c'),
    ('Libc-391','gen/FreeBSD/siglist.c'),('Libc-1752.120.2','string/NetBSD/memset_s.c'))


def apple_sources():
    lock=json.loads(LOCK.read_text());records={r['tag']:r for r in lock['sources']}
    result=[];pins={str(LOCK):previous.sha(LOCK)};provenance=[]
    for tag,name in APPLE_UNITS:
        r=records[tag];archive=USERLAND/'upstream'/(tag+'.tar.gz');source=USERLAND/r['localPath']/name
        if previous.sha(archive)!=r['archiveSHA256']:raise ValueError('Pinned original Apple archive changed: '+tag)
        with tarfile.open(archive,'r:*') as tar:
            member=tar.getmember('Libc-'+tag+'/'+name)
            if not member.isfile() or not 0<member.size<=1024*1024:raise ValueError('Expected bounded original source member')
            data=tar.extractfile(member).read()
        if source.read_bytes()!=data:raise ValueError('Selected Apple source differs from pinned archive: '+str(source))
        result.append(source);pins[str(source)]=previous.sha(source);pins[str(archive)]=r['archiveSHA256']
        provenance.append(dict(tag=tag,commit=r['commit'],archive_url=r['archiveURL'],source=str(source),sha256=pins[str(source)]))
    return result,pins,provenance


def prepare_legacy_source(source,out):
    """Apply narrow SDK syntax corrections to a generated copy, never upstream."""
    original=source.read_text()
    if source.name=='syslog.c':
        old='''\
\tif (LogFile != -1 && !connected)
\t\tif (connect(LogFile, &SyslogAddr, sizeof(SyslogAddr)) == -1) {
\t\t\t(void)close(LogFile);
\t\t\tLogFile = -1;
\t\t} else
\t\t\tconnected = 1;
}'''
        new='''\
\tif (LogFile != -1 && !connected) {
\t\tif (connect(LogFile, (const struct sockaddr *)&SyslogAddr, sizeof(SyslogAddr)) == -1) {
\t\t\t(void)close(LogFile);
\t\t\tLogFile = -1;
\t\t} else
\t\t\tconnected = 1;
\t}
}'''
        generated_name='generated-Libc-167-syslog.c'
        reason='C type cast and explicit braces required by current SDK diagnostics; behavior unchanged'
    elif source.name=='strsignal.c':
        old='\tif (signum < sys_nsig)\n'
        new='\tif (signum < (unsigned int)sys_nsig)\n'
        generated_name='generated-Libc-391-strsignal.c'
        reason='Explicit unsigned comparison required by current compiler diagnostics; behavior unchanged for nonnegative table size'
    else:
        return source,None
    if original.count(old)!=1:
        raise ValueError('Expected exactly one pinned legacy compatibility block in '+str(source))
    generated=original.replace(old,new)
    copy=out/generated_name;copy.write_text(generated)
    diff=''.join(difflib.unified_diff(original.splitlines(True),generated.splitlines(True),
        fromfile=str(source),tofile=str(copy)))
    (out/(generated_name+'.diff')).write_text(diff)
    metadata=dict(original=str(source),original_sha256=previous.sha(source),generated=str(copy),
        generated_sha256=previous.sha(copy),reason=reason)
    return copy,metadata


def build():
    if previous.sha(BASE/'manifest.json')!=BASE_SHA or previous.sha(ABI)!=ABI_SHA:
        raise ValueError('Preserved corrected SSH archive or real ABI archive changed')
    base=json.loads((BASE/'manifest.json').read_text())
    pins=base['source_inputs_sha256']|base['headers_sha256']|base['generated_sha256']
    pins.update({str(BASE/'manifest.json'):BASE_SHA,str(ABI):ABI_SHA,str(SOURCE):previous.sha(SOURCE),
        str(Path(__file__).resolve()):previous.sha(Path(__file__))})
    selected,apple_pins,provenance=apple_sources();pins.update(apple_pins)
    for p in (ADORNMENTS,CALLS,ENTRY,ROOT/'libsyscall/custom/SYS.h'):
        pins[str(p)]=previous.sha(p)
    for n,pin in pins.items():
        if previous.sha(Path(n))!=pin:raise ValueError('Static probe input changed: '+n)
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-probe-',dir=ROOT/'build/rpi5'));commands=[]
    def execute(args,label):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=60)
        (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
        commands.append(dict(command=args,returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        return r
    ref=base['commands'][1]['command']
    common=ref[:ref.index('-target')]
    obj=out/'sshbufferprobe.o'
    target=common+['-target','arm64-apple-darwin','-mcpu=cortex-a76','-ffreestanding','-O2']
    r=execute(target+['-Dmain=darwin_network_command_main','-c',SOURCE,'-o',obj],'compile')
    if r.returncode:raise ValueError('Actual buffer diagnostic compile failed: '+str(out/'compile.stderr'))
    helpers=[];compatibility=[]
    for index,path in enumerate(selected):
        compile_path,correction=prepare_legacy_source(path,out)
        if correction is not None:compatibility.append(correction)
        helper=out/(str(index)+'-'+path.stem+'.o')
        flags=['-std=gnu89','-Wno-implicit-int','-Wno-deprecated-non-prototype','-Wno-deprecated-declarations',
            '-include',ADORNMENTS]
        r=execute(target+flags+['-c',compile_path,'-o',helper],'helper-'+str(index))
        if r.returncode:raise ValueError('Original Apple provider compile failed: '+str(out/('helper-'+str(index)+'.stderr')))
        helpers.append(helper)
    vis=out/'openssh-vis.o'
    r=execute(target+['-DBROKEN_STRNVIS=1','-c',previous.SOURCE/'openbsd-compat/vis.c','-o',vis],'vis')
    if r.returncode:raise ValueError('Original OpenSSH missing-vis provider failed: '+str(out/'vis.stderr'))
    helpers.append(vis)
    entry=out/'argv-entry.o';r=execute(target+['-c',ENTRY,'-o',entry],'argv-entry')
    if r.returncode:raise ValueError('Real argv adapter compile failed: '+str(out/'argv-entry.stderr'))
    helpers.append(entry)
    sysroot=ref[ref.index('-isysroot')+1]
    assembler=[ref[0],'-isysroot',sysroot,'-target','arm64-apple-darwin','-mcpu=cortex-a76']
    asm=out/'syscalls.s'
    r=execute(assembler+['-I',ROOT/'libsyscall/custom','-E','-P','-x','assembler-with-cpp',CALLS],'syscalls-preprocess')
    if r.returncode:raise ValueError('Apple SYS.h preprocess failed')
    asm.write_text(r.stdout.replace('%%','\n'))
    calls=out/'syscalls.o';r=execute(assembler+['-x','assembler','-c',asm,'-o',calls],'syscalls-compile')
    if r.returncode:raise ValueError('Apple syscall emitter compile failed')
    helpers.append(calls)
    program=out/'sshbufferprobe';linkmap=out/'link.map'
    r=execute(['xcrun','ld','-arch','arm64','-platform_version','macos','26.0','27.0','-static','-e','_start',
        '-dead_strip','-no_adhoc_codesign','-no_uuid',
        '-alias','_fopen','_fopen$DARWIN_EXTSN','-map',linkmap,'-o',program,
        obj,*helpers,base['archive'],ABI,*previous.ARCHIVES],'link')
    missing=re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.MULTILINE)
    for n,pin in pins.items():
        if previous.sha(Path(n))!=pin:raise ValueError('Static probe input drift: '+n)
    report=dict(profile='apple-openssh-buffer-static-probe-v1',source_inputs_sha256=pins,commands=commands,
        corrected_archive=str(BASE),real_startup_syscall_adapter_archive=str(ABI),link_returncode=r.returncode,
        original_apple_provider_sources=provenance,original_openssh_vis_fallback=True,
        generated_sdk_compatibility_corrections=compatibility,
        per_unit_vis_selection='BROKEN_STRNVIS selects original missing-provider body; global original config unchanged',
        linker_missing_symbols=missing,static_link_complete=r.returncode==0,
        actual_static_executable=str(program) if r.returncode==0 else None,
        generated_sha256={str(p):previous.sha(p) for p in out.iterdir() if p.is_file()},
        native_host_executed=False,pi_executed=False,installed=False,root_or_kernel_changed=False,
        crypto_runtime_linked=False,ssh_transport_or_server_built=False,
        scope='Actual target reachability/static link evidence with real original runtime adapters; not program execution or SSH')
    with (out/'manifest.json').open('x') as f:json.dump(report,f,indent=2,sort_keys=True);f.write('\n')
    return report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();r=build()
    print(json.dumps({k:r[k] for k in ('actual_static_executable','link_returncode','linker_missing_symbols','static_link_complete')},indent=2))
