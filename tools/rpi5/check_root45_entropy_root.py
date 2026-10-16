#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact45-node/33-file namespace, real dependency and unchanged-file check."""
import argparse
import json
from pathlib import Path
from tools.rpi5 import root_capacity_entropy as builder

ROOT,old=builder.ROOT,builder.old
PACKAGE=ROOT/'build/rpi5/root96-entropy-batch-2an5xdf5'
MANIFEST_SHA='54cb80046cec00ffef59c47dd541bdf1f6e238ec0c0a69585cc491535fccf3f7'
IMAGE_SHA='759ecec262d180d4b82d549e87af9b241a1f4d8b64a7e7578edb9ba573b9c773'
FILES={'rootidentity_catalog.h','rootidentity.o','identity.d','socketprobe','ramdisk.bin'}
LABELS=('identity-dependencies','identity','identity-link','identity-undefined')
merge=builder.merge
dependencies=builder.dependencies
static_entry=builder.static_entry


def inspect_record(package,m):
    pins,prior,probes=builder.inputs()
    args=next(list(r['command']) for r in prior['commands'] if '-c' in r['command'] and r['command'][-1]==str(builder.BASE/'identity.d'))
    args=args[:args.index('-MD')];original_object=args[args.index('-o')+1]
    args[args.index('-o')+1]=str(package/'rootidentity.o')
    args=['-I'+str(package) if x=='-I'+str(builder.BASE) else x for x in args]
    deps=dependencies((package/'identity-dependencies.stdout').read_text())
    if deps!=dependencies((package/'identity.d').read_text()):raise ValueError('Consumed identity headers differ')
    merge(pins,deps)
    link=next(list(r['command']) for r in prior['commands'] if '-o' in r['command'] and
        r['command'][r['command'].index('-o')+1]==str(builder.BASE/'socketprobe') and '-c' not in r['command'])
    link=[str(package/'rootidentity.o') if x==original_object else str(package/'socketprobe') if x==str(builder.BASE/'socketprobe') else x for x in link]
    commands=[dict(command=c,returncode=0) for c in (old.dependency_command(args)+['-M'],args+['-MD','-MF',str(package/'identity.d')],
        link,['xcrun','nm','-u',str(package/'socketprobe')])]
    if m.get('commands')!=commands:raise ValueError('Exact identity compile/link commands differ')
    names=FILES|{label+suffix for label in LABELS for suffix in ('.stdout','.stderr')}
    if any(p.is_symlink() or not p.is_file() for p in package.iterdir()):raise ValueError('Regular package required')
    if {p.name for p in package.iterdir()}!=names|{'manifest.json'}:raise ValueError('Generated membership differs')
    generated={str(package/name):builder.sha(package/name) for name in names}
    if m.get('generated_sha256')!=generated:raise ValueError('Complete generated closure differs')
    if m.get('inputs_sha256')!=pins:raise ValueError('Complete actual input closure differs')
    old.verify(pins)
    original=old.profile.files_from((builder.BASE/'ramdisk.bin').read_bytes());expected=dict(original)
    for entry,report in probes.items():expected[entry]=(Path(report['target']).read_bytes(),0o555)
    _,layout=old.profile.build(expected);rows=[]
    for entry in layout['entries']:
        path,isdir=entry['path'],entry['type']=='directory'
        rows.append(dict(path=path,mode=entry['mode']|(0o40000 if isdir else 0o100000),
            bytes=0 if isdir or path==builder.IDENTITY else len(expected[path][0]),
            sha256='' if isdir else None if path==builder.IDENTITY else old.profile.sha(expected[path][0])))
    if (package/'rootidentity_catalog.h').read_text()!=old.identity.header(rows):raise ValueError('Actual compiled catalog differs')
    expected[builder.IDENTITY]=((package/'socketprobe').read_bytes(),0o555)
    for row in rows:
        if row['path']==builder.IDENTITY:row.update(bytes=len(expected[builder.IDENTITY][0]),sha256=old.profile.sha(expected[builder.IDENTITY][0]))
    raw=(package/'ramdisk.bin').read_bytes();rebuilt,layout=old.profile.build(expected)
    if raw!=rebuilt or old.profile.sha(raw)!=IMAGE_SHA or old.profile.files_from(raw)!=expected:raise ValueError('Full root namespace/bytes differ')
    if (m.get('profile')!=builder.PROFILE or m.get('node_capacity')!=96 or m.get('output_nodes')!=45 or
        m.get('output_files')!=33 or len(layout['entries'])!=45 or len(expected)!=33 or
        m.get('output_bytes')!=len(raw) or m.get('output_sha256')!=IMAGE_SHA or m.get('identity_catalog')!=rows):
        raise ValueError('Exact45-node root geometry/catalog required')
    if m.get('added_files_sha256')!={p:row[2] for p,row in builder.PROBES.items()} or m.get('changed_files_sha256')!={builder.IDENTITY:builder.sha(package/'socketprobe')}:
        raise ValueError('Unexpected new/changed root member')
    if m.get('unchanged_files_sha256')!={p:old.profile.sha(v[0]) for p,v in original.items() if p!=builder.IDENTITY}:
        raise ValueError('Preserved30-file baseline mismatch')
    required=prior['required_trial_commands']+list(builder.PROBES)
    if m.get('required_trial_commands')!=required or m.get('limits')!=builder.LIMITS:
        raise ValueError('Exact12-command diagnostic scope required')
    if any(type(m['limits'][k]) is not type(v) for k,v in builder.LIMITS.items()):
        raise ValueError('Typed diagnostic scope required')
    if m.get('probe_manifests')!={p:{'path':str(row[0]/'manifest.json'),'sha256':row[1]} for p,row in builder.PROBES.items()}:
        raise ValueError('Exact probe provenance required')
    if (m.get('baseline')!=str(builder.BASE) or m.get('baseline_manifest_sha256')!=builder.baseline.MANIFEST_SHA or
        m.get('input_root_sha256')!=builder.baseline.IMAGE_SHA or m.get('canonical_path')!=old.CANONICAL_PATH or
        m.get('compatibility_regular_files')!=old.ALIASES or m.get('default_init_and_shell_unchanged') is not True or
        m.get('frozen_zsh_unchanged') is not True):
        raise ValueError('Exact preserved baseline and Darwin paths required')
    for key in ('installed','pi_executed','ssh_proven','networking_proven'):
        if m.get(key) is not False:raise ValueError('Offline build is not execution acceptance')
    audits={p:static_entry(expected[p][0],'_darwin_static_start') for p in builder.PROBES}
    if m.get('probe_executable_audits')!=audits:raise ValueError('Actual executable entry differs')
    audits[builder.IDENTITY]=static_entry(expected[builder.IDENTITY][0],'_user_start')
    audits['/sbin/launchd']=static_entry(expected['/sbin/launchd'][0],'_user_start')
    return dict(preflight_pass=True,profile=builder.PROFILE,root=str(package/'ramdisk.bin'),root_sha256=IMAGE_SHA,
        root_manifest=str(package/'manifest.json'),root_manifest_sha256=MANIFEST_SHA,root_nodes=45,root_files=33,
        root_bytes=len(raw),identity_catalog=rows,source_input_count=len(pins),generated_count=len(generated),
        actual_dependency_counts={'identity':len(deps)},reconstructed_command_count=len(commands),executable_entry_audits=audits,
        canonical_aliases_verified=True,identity_self_digest_compared_externally=True,
        required_future_trial_commands=required,limits=m['limits'],installed=False,pi_executed=False,ssh_daemon=False,networking=False,
        checker_sha256=builder.sha(Path(__file__)),scope='Exact immutable45-node root; neither Pi API nor entropy qualification')


def inspect(package):
    package=package.resolve()
    if package!=PACKAGE or builder.sha(package/'manifest.json')!=MANIFEST_SHA:raise ValueError('Exact frozen entropy root required')
    return inspect_record(package,json.loads((package/'manifest.json').read_text()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
