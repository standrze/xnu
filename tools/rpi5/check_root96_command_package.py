#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only, fixed-candidate admission audit for the 41-node command RAM-root.

No linker/compiler is executed and no target program is run. This reconstructs
the recorded commands and complete artifact/dependency sets; it does not invent
missing build-time tool identities or historical source snapshots.
"""
import argparse
import difflib
import json
from pathlib import Path
import shlex
import struct
try:
    from . import root_capacity_commands as builder
except ImportError:
    import root_capacity_commands as builder

ROOT=builder.ROOT
PACKAGE=ROOT/'build/rpi5/root96-command-batch-uc8f3v5l'
MANIFEST_SHA='9467ce7c30e9409be402bab3ed43c4e8b7bdb9cde052ea8116a4a1531974c817'
IMAGE_SHA='4bd824425b0509b7a163649e07ded06ae7eeae6397a90d0e7b2eb75e50955708'
LABELS=('baseline-relink','init-dependencies','init','shell-dependencies','shell',
        'recovery-link','recovery-undefined','identity-dependencies','identity','identity-link','identity-undefined')
FILES=('recovery-baseline','recovery','socketprobe','ramdisk.bin','init.c','shell.c',
       'init.o','shell.o','rootidentity.o','rootidentity_catalog.h','init.c.diff','shell.c.diff',
       'init.d','shell.d','identity.d')


def same(a,b):return json.dumps(a,sort_keys=True)==json.dumps(b,sort_keys=True)


def merge(pins,other):
    for name,digest in other.items():
        if name in pins and pins[name]!=digest:raise ValueError('Conflicting independently reconstructed input')
        pins[name]=digest


def dependencies(text):
    if ':' not in text:raise ValueError('Missing compiler dependency target')
    paths=shlex.split(text.replace('\\\n',' ').partition(':')[2])
    if not paths:raise ValueError('Empty compiler dependency closure')
    return {str(Path(p).resolve()):builder.sha(Path(p).resolve()) for p in paths}


def expected_build(package):
    prior=builder.receipt(builder.BASE/'manifest.json',builder.BASE_MANIFEST)
    pwd=builder.receipt(builder.PWD/'manifest.json',builder.PWD_MANIFEST)
    crypto=builder.receipt(builder.CRYPTO/'manifest.json',builder.CRYPTO_MANIFEST)
    recovery=builder.receipt(builder.RECOVERY/'manifest.json',builder.RECOVERY_MANIFEST)
    pins=dict(prior['inputs_sha256'])
    for record in (pwd,crypto):
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):merge(pins,record[key])
    for directory in (builder.BASE,builder.PWD,builder.CRYPTO,builder.RECOVERY):
        path=directory/'manifest.json';merge(pins,{str(path):builder.sha(path)})
    for path in (builder.BASE/'ramdisk.bin',Path(builder.__file__).resolve(),Path(builder.profile.__file__).resolve(),
                 Path(builder.identity.__file__).resolve(),Path(builder.identity.old.__file__).resolve(),
                 Path(builder.inspect_macho.__code__.co_filename),builder.profile.PACKER):
        merge(pins,{str(path):builder.sha(path)})
    for name in ('init.c','shell.c','runtime.h','parser.h'):
        path=builder.SOURCE/name
        if builder.sha(path)!=recovery['source_inputs_sha256'][str(path)]:raise ValueError('Accepted rebuilt recovery source differs')
        merge(pins,{str(path):builder.sha(path)})
    old_link=recovery['commands'][-1]
    for token in old_link:
        if token.endswith('.o'):merge(pins,{token:builder.sha(Path(token))})
    commands=[];closures={}
    def record(args):commands.append(dict(command=args,returncode=0))
    def compiled(args,label):
        record(builder.dependency_command(args)+['-M'])
        record(args+['-MD','-MF',str(package/(label+'.d'))])
        before=dependencies((package/(label+'-dependencies.stdout')).read_text())
        after=dependencies((package/(label+'.d')).read_text())
        if before!=after:raise ValueError('Pre-scan and actual compiler dependency closure differ')
        merge(pins,after);closures[label]=after
    record([str(package/'recovery-baseline') if x==str(builder.RECOVERY/'userland') else x for x in old_link])
    replacements={str(builder.RECOVERY/'userland'):str(package/'recovery')}
    for name in ('init.c','shell.c'):
        args=next(list(row) for row in recovery['commands'] if str(builder.SOURCE/name) in row)
        replacements[args[-1]]=str(package/(Path(name).stem+'.o'))
        args[args.index(str(builder.SOURCE/name))]=str(package/name)
        args[-1]=replacements[args[-1]]
        args[1:1]=['-iquote',str(builder.SOURCE),'-mcpu=cortex-a76']
        compiled(args,Path(name).stem)
    record([replacements.get(x,x) for x in old_link]);record(['xcrun','nm','-u',str(package/'recovery')])
    args=list(prior['commands'][0]);old_object=args[-1]
    args=['-I'+str(package) if x=='-I'+str(builder.BASE) else x for x in args]
    if '-I'+str(package) not in args:raise ValueError('Identity catalog include binding absent')
    args[-1]=str(package/'rootidentity.o');compiled(args,'identity')
    old_identity_link=prior['commands'][-1]
    for token in old_identity_link:
        if token.endswith('.o'):merge(pins,{token:builder.sha(Path(token))})
    record([str(package/'rootidentity.o') if x==old_object else str(package/'socketprobe')
            if x==str(builder.BASE/'socketprobe') else x for x in old_identity_link])
    record(['xcrun','nm','-u',str(package/'socketprobe')])
    return pins,commands,closures,prior,crypto,recovery


def static_entry(raw,entry_target):
    audit=builder.inspect_macho(raw);symbols={};segments=[];offset=32
    for _ in range(struct.unpack_from('<I',raw,16)[0]):
        cmd,size=struct.unpack_from('<II',raw,offset)
        if cmd==0x19:
            vm,size_vm,fileoff,size_file=struct.unpack_from('<4Q',raw,offset+24)
            prot=struct.unpack_from('<I',raw,offset+60)[0]
            segments.append((vm,size_vm,fileoff,size_file,prot))
        elif cmd==2:
            symoff,count,stroff,strsize=struct.unpack_from('<4I',raw,offset+8)
            for i in range(count):
                index,kind,section,desc,value=struct.unpack_from('<IBBHQ',raw,symoff+i*16)
                end=raw.find(b'\0',stroff+index,stroff+strsize)
                if end<0:raise ValueError('Unterminated linked symbol')
                name=raw[stroff+index:end].decode('ascii')
                if name in ('_start',entry_target):
                    if name in symbols or kind&0xe!=0xe:raise ValueError('Invalid/duplicate executable entry symbol')
                    symbols[name]=value
        offset+=size
    if symbols.get('_start')!=audit['entry_pc'] or entry_target not in symbols:raise ValueError('LC_UNIXTHREAD/linked entry mismatch')
    mappings=[fileoff+symbols['_start']-vm for vm,_,fileoff,size_file,prot in segments
              if prot&4 and vm<=symbols['_start'] and symbols['_start']+24<=vm+size_file]
    if len(mappings)!=1:raise ValueError('Entry has no unique executable file mapping')
    words=struct.unpack_from('<6I',raw,mappings[0]);calls=[]
    for i,word in enumerate(words):
        if word&0xfc000000==0x94000000:
            delta=word&0x3ffffff
            if delta&0x2000000:delta-=0x4000000
            calls.append(symbols['_start']+i*4+delta*4)
    if words[0]!=0x910003e0 or words[2]!=0x927ced29 or symbols[entry_target] not in calls:
        raise ValueError('Actual process-stack/real startup call contract differs')
    return dict(audit,entry_symbol='_start',entry_target=entry_target,entry_target_address=symbols[entry_target])


def inspect_record(package,m):
    """Independent structure checks; public admission also pins immutable manifest."""
    package=package.resolve()
    pins,commands,closures,prior,crypto,recovery=expected_build(package)
    generated_names=set(FILES)|{label+suffix for label in LABELS for suffix in ('.stdout','.stderr')}
    entries=list(package.iterdir())
    if any(p.is_symlink() or not p.is_file() for p in entries):raise ValueError('Package artifacts must be regular non-symlink files')
    actual_names={p.name for p in entries if p.name!='manifest.json'}
    if actual_names!=generated_names:raise ValueError('Unexpected/missing generated artifact set')
    generated={str(package/name):builder.sha(package/name) for name in generated_names}
    if not same(m.get('inputs_sha256'),pins):raise ValueError('Incomplete/changed reconstructed input closure')
    if not same(m.get('generated_sha256'),generated):raise ValueError('Incomplete/changed generated closure')
    builder.verify(pins)
    if not same(m.get('commands'),commands):raise ValueError('Exact reconstructed compiler/link commands differ')
    original_raw=(builder.BASE/'ramdisk.bin').read_bytes()
    if builder.profile.sha(original_raw)!=builder.BASE_IMAGE:raise ValueError('Accepted root changed')
    original=builder.profile.files_from(original_raw)
    if (original['/bin/sh']!=original['/sbin/launchd'] or
        not builder.replay_equal((package/'recovery-baseline').read_bytes(),original['/sbin/launchd'][0])):
        raise ValueError('Actual accepted recovery object replay differs')
    for name in ('init.c','shell.c'):
        before,after=builder.derive_recovery(name)
        diff=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='accepted/'+name,tofile=name))
        if (package/name).read_text()!=after or (package/(name+'.diff')).read_text()!=diff:
            raise ValueError('Derived recovery source/diff differs')
    recovery_raw=(package/'recovery').read_bytes()
    if ('PATH='+builder.CANONICAL_PATH).encode()+b'\0' not in recovery_raw:raise ValueError('Child PATH absent from actual executable')
    files=dict(original)
    for canonical,alias in builder.ALIASES.items():files[canonical]=original[alias]
    files['/bin/pwd']=((builder.PWD/'pwd').read_bytes(),0o555)
    files['/usr/local/libexec/xnu/sshcryptoprobe']=((builder.CRYPTO/'sshcryptoprobe').read_bytes(),0o555)
    files['/etc/paths']=(('\n'.join(builder.CANONICAL_PATH.split(':'))+'\n').encode(),0o444)
    files['/bin/sh']=files['/sbin/launchd']=(recovery_raw,0o555)
    _,layout=builder.profile.build(files);rows=[]
    for entry in layout['entries']:
        path,isdir=entry['path'],entry['type']=='directory'
        rows.append(dict(path=path,mode=entry['mode']|(0o40000 if isdir else 0o100000),
            bytes=0 if isdir or path==builder.IDENTITY else len(files[path][0]),
            sha256='' if isdir else None if path==builder.IDENTITY else builder.profile.sha(files[path][0])))
    if (package/'rootidentity_catalog.h').read_text()!=builder.identity.header(rows):raise ValueError('Actual compiled complete identity catalog differs')
    files[builder.IDENTITY]=((package/'socketprobe').read_bytes(),0o555)
    expected_raw,layout=builder.profile.build(files);raw=(package/'ramdisk.bin').read_bytes()
    if raw!=expected_raw or builder.profile.files_from(raw)!=files:raise ValueError('Actual full root namespace/bytes differ')
    for row in rows:
        if row['path']==builder.IDENTITY:row.update(bytes=len(files[builder.IDENTITY][0]),sha256=builder.profile.sha(files[builder.IDENTITY][0]))
    changed={builder.IDENTITY,'/bin/sh','/sbin/launchd'}
    required=dict(profile='rpi5-root96-current-command-batch-v1',node_capacity=96,baseline=str(builder.BASE),
        input_root_sha256=builder.BASE_IMAGE,output_sha256=IMAGE_SHA,output_bytes=len(raw),output_nodes=41,
        identity_catalog=rows,identity_self_digest_compared_externally=True,canonical_path=builder.CANONICAL_PATH,
        compatibility_regular_files=builder.ALIASES,
        added_files_sha256={p:builder.profile.sha(v[0]) for p,v in files.items() if p not in original},
        changed_files_sha256={p:builder.profile.sha(files[p][0]) for p in changed},
        unchanged_files_sha256={p:builder.profile.sha(v[0]) for p,v in original.items() if p not in changed},
        kernel=prior['kernel'],kernel_sha256=prior['kernel_sha256'],kernel_manifest=prior['kernel_manifest'],
        kernel_manifest_sha256=prior['kernel_manifest_sha256'],apple_pwd_manifest_sha256=builder.PWD_MANIFEST,
        crypto_manifest_sha256=builder.CRYPTO_MANIFEST,crypto_vectors=crypto['vectors'],crypto_transport=False,
        date_included=False,source_baseline_recovery_replay_except_uuid=True,frozen_zsh_unchanged=True,
        default_init_and_shell_unchanged=False,recovery_change='Only canonical PATH and bounded command lookup',
        installed=False,pi_executed=False,ssh_proven=False,networking_proven=False,sd_actions=0,serial_actions=0,reboots=0)
    if set(m)!=set(required)|{'inputs_sha256','generated_sha256','commands'}:raise ValueError('Unexpected manifest field set')
    if any(not same(m.get(k),v) for k,v in required.items()):raise ValueError('Exact namespace/catalog/provenance metadata differs')
    if builder.profile.sha(raw)!=IMAGE_SHA or len(layout['entries'])!=41 or len(files)!=29:raise ValueError('Exact final image geometry/hash differs')
    entries={path:static_entry(files[path][0],target) for path,target in (
        ('/bin/sh','_user_start'),(builder.IDENTITY,'_user_start'),('/bin/pwd','_darwin_static_start'),
        ('/usr/local/libexec/xnu/sshcryptoprobe','_darwin_static_start'))}
    drift=[name for name,digest in recovery['source_inputs_sha256'].items() if builder.sha(Path(name))!=digest]
    return dict(preflight_pass=True,profile=m['profile'],root=str(package/'ramdisk.bin'),root_sha256=IMAGE_SHA,
        root_manifest=str(package/'manifest.json'),root_manifest_sha256=MANIFEST_SHA,root_nodes=41,root_files=29,
        root_bytes=len(raw),source_input_count=len(pins),generated_count=len(generated),
        actual_dependency_counts={name:len(values) for name,values in closures.items()},reconstructed_command_count=len(commands),
        executable_entry_audits=entries,canonical_aliases_verified=True,identity_self_digest_compared_externally=True,
        required_future_trial_commands=['/bin/pwd -P','/usr/bin/uname','/usr/bin/wc /etc/motd',
            '/usr/bin/hexdump /etc/motd','/usr/local/libexec/xnu/statprobe',
            '/usr/local/libexec/xnu/sshcryptoprobe'],
        limits=dict(build_time_tool_identity_pinned=False,legacy_recovery_object_byte_replay=True,
            legacy_recovery_full_source_reproducible=False,legacy_source_drift=drift,
            empty_usr_sbin_directory_present=False,recovery_all_enotdir_exit=126,
            plain_pwd_is_builtin=True,host_path_tests_execute_host_commands=True,
            canonical_uname_wc_hexdump_are_recovery_multicall=True),
        installed=False,pi_executed=False,ssh_daemon=False,networking=False,
        checker_sha256=builder.sha(Path(__file__)),
        scope='Exact immutable 41-node package/source/object/namespace validation; not Pi execution or shell/SSH/network acceptance')


def inspect(package):
    package=package.resolve()
    if package!=PACKAGE or builder.sha(package/'manifest.json')!=MANIFEST_SHA:
        raise ValueError('Exact immutable reviewed command package required')
    return inspect_record(package,json.loads((package/'manifest.json').read_text()))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
