#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Immutable 41-node follow-on: add only real pthreadprobe and new identity."""
import json
from pathlib import Path
import tempfile
try:
    from . import check_root96_command_package as prior_check
    from . import root_capacity_commands as old
except ImportError:
    import check_root96_command_package as prior_check
    import root_capacity_commands as old

ROOT=old.ROOT
BASE=prior_check.PACKAGE
PTHREAD=ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz'
PTHREAD_MANIFEST='4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a'
PTHREAD_SHA='bc882d7d3ca236d9f649292b9a64aebb6669a1b9f3ee0806c61d21c7f418ba15'
ENTRY='/usr/local/libexec/xnu/pthreadprobe'
IDENTITY=old.IDENTITY
sha=old.sha


def build():
    baseline=prior_check.inspect(BASE)
    prior=json.loads((BASE/'manifest.json').read_text())
    thread=old.receipt(PTHREAD/'manifest.json',PTHREAD_MANIFEST)
    if not thread['target_link_complete'] or thread['target_missing_symbols'] or thread['target_duplicate_symbols']:
        raise ValueError('Actual clean pthread link required')
    executable=Path(thread['target'])
    if sha(executable)!=PTHREAD_SHA:raise ValueError('Exact real pthread target required')
    original=old.profile.files_from((BASE/'ramdisk.bin').read_bytes())
    if len(original)!=29 or ENTRY in original:raise ValueError('Exact preserved 41-node root required')
    pins=dict(prior['inputs_sha256'])
    prior_check.merge(pins,prior['generated_sha256'])
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):prior_check.merge(pins,thread[key])
    for path in (BASE/'manifest.json',PTHREAD/'manifest.json',Path(__file__).resolve(),Path(prior_check.__file__).resolve()):
        prior_check.merge(pins,{str(path):sha(path)})
    old.verify(pins)
    output=Path(tempfile.mkdtemp(prefix='root96-pthread-batch-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(output),flush=True)
    expanded=dict(original);expanded[ENTRY]=(executable.read_bytes(),0o555)
    audit=prior_check.static_entry(expanded[ENTRY][0],'_darwin_static_start')
    _,layout=old.profile.build(expanded)
    rows=[]
    for entry in layout['entries']:
        path,isdir=entry['path'],entry['type']=='directory'
        rows.append(dict(path=path,mode=entry['mode']|(0o40000 if isdir else 0o100000),
            bytes=0 if isdir or path==IDENTITY else len(expanded[path][0]),
            sha256='' if isdir else None if path==IDENTITY else old.profile.sha(expanded[path][0])))
    (output/'rootidentity_catalog.h').write_text(old.identity.header(rows))
    compile_args=next(list(r['command']) for r in prior['commands'] if '-c' in r['command'] and
                      r['command'][-1]==str(BASE/'identity.d'))
    # Prior actual compiler invocation includes -MD/-MF added after -o object.
    position=compile_args.index('-MD');compile_args=compile_args[:position]
    old_object=compile_args[compile_args.index('-o')+1];obj=output/'rootidentity.o'
    compile_args[compile_args.index('-o')+1]=str(obj)
    compile_args=['-I'+str(output) if x=='-I'+str(BASE) else x for x in compile_args]
    if '-I'+str(output) not in compile_args:raise ValueError('Actual catalog include not rebound')
    commands=[]
    old.compile_actual(compile_args,output,'identity',commands,pins)
    source_link=next(list(r['command']) for r in prior['commands'] if '-o' in r['command'] and
                     r['command'][r['command'].index('-o')+1]==str(BASE/'socketprobe') and '-c' not in r['command'])
    link=[str(obj) if x==old_object else str(output/'socketprobe') if x==str(BASE/'socketprobe') else x for x in source_link]
    old.run(link,output,'identity-link',commands)
    if old.run(['xcrun','nm','-u',str(output/'socketprobe')],output,'identity-undefined',commands).strip():
        raise ValueError('Unresolved identity provider')
    expanded[IDENTITY]=((output/'socketprobe').read_bytes(),0o555)
    for row in rows:
        if row['path']==IDENTITY:row.update(bytes=len(expanded[IDENTITY][0]),sha256=old.profile.sha(expanded[IDENTITY][0]))
    raw,layout=old.profile.build(expanded)
    if len(layout['entries'])!=42 or len(expanded)!=30 or old.profile.files_from(raw)!=expanded:
        raise ValueError('Exact 42-node/30-file round trip required')
    if any(expanded[p]!=v for p,v in original.items() if p!=IDENTITY):raise ValueError('Unrelated baseline changed')
    (output/'ramdisk.bin').write_bytes(raw)
    old.verify(pins)
    report=dict(profile='rpi5-root96-genuine-pthread-batch-v1',node_capacity=96,
        baseline=str(BASE),baseline_manifest_sha256=prior_check.MANIFEST_SHA,input_root_sha256=prior_check.IMAGE_SHA,
        output_sha256=old.profile.sha(raw),output_bytes=len(raw),output_nodes=42,output_files=30,
        identity_catalog=rows,identity_self_digest_compared_externally=True,commands=commands,inputs_sha256=pins,
        added_files_sha256={ENTRY:PTHREAD_SHA},changed_files_sha256={IDENTITY:sha(output/'socketprobe')},
        unchanged_files_sha256={p:old.profile.sha(v[0]) for p,v in original.items() if p!=IDENTITY},
        canonical_path=old.CANONICAL_PATH,compatibility_regular_files=old.ALIASES,
        default_init_and_shell_unchanged=True,frozen_zsh_unchanged=True,
        pthread_manifest=str(PTHREAD/'manifest.json'),pthread_manifest_sha256=PTHREAD_MANIFEST,
        pthread_executable_audit=audit,
        required_trial_commands=['/bin/zsh -f /etc/zsh-smoke.zsh','/usr/local/libexec/xnu/sshbufferprobe',
            '/usr/local/libexec/xnu/sshcryptoprobe','/bin/pwd -P','/usr/bin/uname','/usr/bin/wc /etc/motd',
            '/usr/bin/hexdump /etc/motd','/usr/local/libexec/xnu/statprobe',ENTRY],
        limits=dict(pthread_not_run=True,host_tests_not_target_execution=True,entropy_not_qualified=True,
            allocator_default_zone_only=True,full_multizone_allocator_not_claimed=True,
            exact_single_constructor_not_general_dyld_init=True,xnu_stack_pointers_trusted=True,
            modern_full_libsystem_not_claimed=True,loader_kernel_package_not_created=True),
        installed=False,pi_executed=False,ssh_proven=False,networking_proven=False,sd_actions=0,serial_actions=0,reboots=0,
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(output),sha256=report['output_sha256'],nodes=42,files=30),indent=2))
    return output,report

if __name__=='__main__':build()
