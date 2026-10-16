#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Compose genuine provider groups into the unchanged full original SSH client.

This is a full executable link attempt, not ssh -V execution or a proxy workload.
Locale takes explicit startup/archive ownership; no optional features are removed.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_client_leaves as leaves

ROOT,sha=leaves.ROOT,leaves.sha
RECEIPTS={
    'base':('apple-ssh-path-memory-p6awfv2m','14798734ab0c6af05342b41e7557676eb3dffe41fc1aead96fed0acc4ceea38c'),
    'zlib':('ssh-zlib-runtime-jl5uvvmb','01e691fec55406c122053f48a398f37cd625ae95b6c87b73890acba21d3de2b5'),
    'random':('kernel-entropy-word-z34ff8bs','e9467381132ecd13d800696361422234c55ee0156d59e184a213a220940eb2c6'),
    'locale':('apple-ssh-locale-slice-p7_8ertv','a6411a2990ba6abea004cd17363bb57a7d89559c4703a00d6d923d5facc43fc6'),
    'ownership':('apple-ssh-current-locale-ebd652yw','4c722fcbab48d012865d2071953cf3994d27e1220a8eacddac7adf23c0fd0395'),
    'locale_contract':('apple-ssh-current-locale-contract-ni1pfpjw','c45e4a7c3f672003dfa1b6afdb97b6c370153902a487ac0230457251b5da5c6b'),
}


def replace_once(command,old,new):
    if command.count(old)!=1:raise ValueError('Ambiguous runtime owner replacement: '+old)
    command[command.index(old)]=new


def build():
    pins={str(Path(__file__).resolve()):sha(__file__)};reports={};receipt_pins={}
    for label,(directory,digest) in RECEIPTS.items():
        path=ROOT/'build/rpi5'/directory/'manifest.json'
        if sha(path)!=digest:raise ValueError('Frozen group receipt changed: '+label)
        reports[label]=json.loads(path.read_text());pins[str(path)]=digest;receipt_pins[str(path)]=digest
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
            for n,h in reports[label].get(key,{}).items():
                if n in pins and pins[n]!=h:raise ValueError('Conflicting real provider pins: '+n)
                pins[n]=h
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Actual provider bytes changed: '+n)
    verify();out=Path(tempfile.mkdtemp(prefix='apple-ssh-runtime-groups-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[]
    def run(args,label,allowed=False):
        args=list(map(str,args));r=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,timeout=90)
        for key in ('stdout','stderr'):(out/(label+'.'+key)).write_text(getattr(r,key))
        commands.append(dict(command=args,cwd=str(ROOT),returncode=r.returncode,stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if r.returncode and not allowed:raise ValueError(label+': '+r.stderr[-6000:])
        return r
    base=reports['base'];owner=reports['ownership']
    link=list(next(c['command'] for c in base['commands'] if c['stdout'].endswith('/target-link.stdout')))
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh');link[link.index('-map')+1]=str(out/'target.map')
    replacements={str(ROOT/'build/rpi5/apple-pthread-static-complete-gm82fjkz/startup.o'):owner['startup_replacement_object'],
                  owner['original_runtime_archive']:owner['runtime_archive']}
    for old,new in replacements.items():replace_once(link,old,new)
    # These were archive-closure forcing only, never client feature changes. The
    # original locale's real call graph now determines whether the I/O is linked.
    removed=[]
    for symbol in ('_open$NOCANCEL','_openat$NOCANCEL','_read$NOCANCEL'):
        if link.count(symbol)!=1 or link[link.index(symbol)-1]!='-u':raise ValueError('Expected diagnostic-only force absent')
        i=link.index(symbol);del link[i-1:i+1];removed.append(symbol)
    appended=[]
    for label in ('zlib','random','locale'):
        archive=reports[label]['target_archive']
        if archive in link:raise ValueError('Duplicate provider archive')
        if archive not in pins:raise ValueError('Actual provider archive not pinned')
        link.append(archive);appended.append(archive)
    r=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',r.stderr,re.M)))
    duplicates=sorted(set(re.findall(r"duplicate symbol '([^']+)'",r.stderr)))
    if r.returncode and not missing and not duplicates:raise ValueError('Unclassified linker failure')
    verify()
    report=dict(profile='full-original-apple-ssh-genuine-runtime-groups-v1',source_inputs_sha256=pins,
        group_receipts_sha256=receipt_pins,commands=commands,runtime_replacements=replacements,
        appended_provider_archives=appended,removed_diagnostic_only_forced_symbols=removed,
        actual_original_translation_units=176,original_openssh_config_unchanged=True,
        original_client_main=True,client_version='OpenSSH_10.0p2',
        removed_legacy_locale_members=owner['removed_legacy_locale_members'],
        target_missing_symbols=missing,target_duplicate_symbols=duplicates,target_link_complete=not r.returncode,
        previous_missing_count=len(base['target_missing_symbols']),
        closed_symbols=sorted(set(base['target_missing_symbols'])-set(missing)),
        newly_reachable_symbols=sorted(set(missing)-set(base['target_missing_symbols'])),
        remaining_provider_groups=leaves.categories(missing),
        target_executed=False,ssh_version_executed=False,live_keys=False,network_access=False,
        entropy_qualified=False,provider_stubs=False,optional_features_removed=False,accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.iterdir() if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),closed=len(report['closed_symbols']),new=report['newly_reachable_symbols'],
                          remaining=len(missing),duplicates=duplicates),indent=2))
    return out,report


if __name__=='__main__':build()
