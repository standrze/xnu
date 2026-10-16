#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Read-only exact 42-node RAM-root admission; separate from its loader checker."""
import argparse
import json
from pathlib import Path
try:
    from . import root_capacity_pthread as builder
except ImportError:
    import root_capacity_pthread as builder

ROOT=builder.ROOT
PACKAGE=ROOT/'build/rpi5/root96-pthread-batch-go4g0fe7'
MANIFEST_SHA='69d562664e6477570edca65e973daed65f48b50393a446a1287d7d651ba641a0'
IMAGE_SHA='9ddbbd5701ca890e97f3f5aefd4c3c0c47434fb50a34bbce51d11e77141b94fd'
old=builder.old
prior_check=builder.prior_check
FILES={'rootidentity_catalog.h','rootidentity.o','identity.d','socketprobe','ramdisk.bin'}
LABELS=('identity-dependencies','identity','identity-link','identity-undefined')


def inspect_record(package,m):
    prior_check.inspect(builder.BASE)
    prior=json.loads((builder.BASE/'manifest.json').read_text())
    pthread=old.receipt(builder.PTHREAD/'manifest.json',builder.PTHREAD_MANIFEST)
    pins=dict(prior['inputs_sha256']);prior_check.merge(pins,prior['generated_sha256'])
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):prior_check.merge(pins,pthread[key])
    for path in (builder.BASE/'manifest.json',builder.PTHREAD/'manifest.json',Path(builder.__file__).resolve(),Path(prior_check.__file__).resolve()):
        prior_check.merge(pins,{str(path):builder.sha(path)})
    args=next(list(r['command']) for r in prior['commands'] if '-c' in r['command'] and r['command'][-1]==str(builder.BASE/'identity.d'))
    args=args[:args.index('-MD')];original_object=args[args.index('-o')+1]
    args[args.index('-o')+1]=str(package/'rootidentity.o')
    args=['-I'+str(package) if x=='-I'+str(builder.BASE) else x for x in args]
    deps=prior_check.dependencies((package/'identity-dependencies.stdout').read_text())
    if deps!=prior_check.dependencies((package/'identity.d').read_text()):raise ValueError('Actual identity headers changed')
    prior_check.merge(pins,deps)
    link=next(list(r['command']) for r in prior['commands'] if '-o' in r['command'] and
              r['command'][r['command'].index('-o')+1]==str(builder.BASE/'socketprobe') and '-c' not in r['command'])
    link=[str(package/'rootidentity.o') if x==original_object else str(package/'socketprobe') if x==str(builder.BASE/'socketprobe') else x for x in link]
    commands=[dict(command=c,returncode=0) for c in (old.dependency_command(args)+['-M'],
        args+['-MD','-MF',str(package/'identity.d')],link,['xcrun','nm','-u',str(package/'socketprobe')])]
    if m.get('commands')!=commands:raise ValueError('Exact 42-node compile/link commands differ')
    names=FILES|{label+suffix for label in LABELS for suffix in ('.stdout','.stderr')}
    if any(p.is_symlink() or not p.is_file() for p in package.iterdir()):raise ValueError('Regular package required')
    if {p.name for p in package.iterdir()}!=names|{'manifest.json'}:raise ValueError('Generated membership differs')
    generated={str(package/name):builder.sha(package/name) for name in names}
    if m.get('generated_sha256')!=generated:raise ValueError('Complete generated closure differs')
    if m.get('inputs_sha256')!=pins:raise ValueError('Complete independently reconstructed inputs differ')
    old.verify(pins)
    original=old.profile.files_from((builder.BASE/'ramdisk.bin').read_bytes())
    expected=dict(original);expected[builder.ENTRY]=(Path(pthread['target']).read_bytes(),0o555)
    if old.profile.sha(expected[builder.ENTRY][0])!=builder.PTHREAD_SHA:raise ValueError('Exact pthread executable changed')
    _,layout=old.profile.build(expected);rows=[]
    for entry in layout['entries']:
        path,isdir=entry['path'],entry['type']=='directory'
        rows.append(dict(path=path,mode=entry['mode']|(0o40000 if isdir else 0o100000),
            bytes=0 if isdir or path==builder.IDENTITY else len(expected[path][0]),
            sha256='' if isdir else None if path==builder.IDENTITY else old.profile.sha(expected[path][0])))
    if (package/'rootidentity_catalog.h').read_text()!=old.identity.header(rows):raise ValueError('Actual compiled complete catalog differs')
    expected[builder.IDENTITY]=((package/'socketprobe').read_bytes(),0o555)
    for row in rows:
        if row['path']==builder.IDENTITY:row.update(bytes=len(expected[builder.IDENTITY][0]),sha256=old.profile.sha(expected[builder.IDENTITY][0]))
    raw=(package/'ramdisk.bin').read_bytes();rebuilt,layout=old.profile.build(expected)
    if raw!=rebuilt or old.profile.sha(raw)!=IMAGE_SHA or old.profile.files_from(raw)!=expected:raise ValueError('Full root namespace/bytes differ')
    if (m.get('profile')!='rpi5-root96-genuine-pthread-batch-v1' or m.get('node_capacity')!=96 or
        m.get('output_nodes')!=42 or m.get('output_files')!=30 or len(layout['entries'])!=42 or len(expected)!=30 or
        m.get('output_bytes')!=len(raw) or m.get('output_sha256')!=IMAGE_SHA or m.get('identity_catalog')!=rows):
        raise ValueError('Exact 42-node root geometry/catalog required')
    if m.get('added_files_sha256')!={builder.ENTRY:builder.PTHREAD_SHA} or m.get('changed_files_sha256')!={builder.IDENTITY:builder.sha(package/'socketprobe')}:
        raise ValueError('Unexpected new/changed root member')
    if m.get('unchanged_files_sha256')!={p:old.profile.sha(v[0]) for p,v in original.items() if p!=builder.IDENTITY}:
        raise ValueError('Preserved 28-file baseline mismatch')
    for key in ('installed','pi_executed','ssh_proven','networking_proven'):
        if m.get(key) is not False:raise ValueError('Build is not runtime acceptance')
    entries={path:prior_check.static_entry(expected[path][0],entry) for path,entry in
        ((builder.ENTRY,'_darwin_static_start'),(builder.IDENTITY,'_user_start'),('/sbin/launchd','_user_start'))}
    if entries[builder.ENTRY]!=m.get('pthread_executable_audit'):raise ValueError('Actual pthread entry contract differs')
    return dict(preflight_pass=True,profile=m['profile'],root=str(package/'ramdisk.bin'),root_sha256=IMAGE_SHA,
        root_manifest=str(package/'manifest.json'),root_manifest_sha256=MANIFEST_SHA,root_nodes=42,root_files=30,
        root_bytes=len(raw),identity_catalog=rows,source_input_count=len(pins),generated_count=len(generated),
        actual_dependency_counts={'identity':len(deps)},reconstructed_command_count=len(commands),
        executable_entry_audits=entries,canonical_aliases_verified=True,identity_self_digest_compared_externally=True,
        required_future_trial_commands=m['required_trial_commands'],limits=m['limits'],
        installed=False,pi_executed=False,ssh_daemon=False,networking=False,
        checker_sha256=builder.sha(Path(__file__)),scope='Exact immutable 42-node root; not Pi pthread acceptance')


def inspect(package):
    package=package.resolve()
    if package!=PACKAGE or builder.sha(package/'manifest.json')!=MANIFEST_SHA:raise ValueError('Exact frozen pthread root required')
    return inspect_record(package,json.loads((package/'manifest.json').read_text()))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
