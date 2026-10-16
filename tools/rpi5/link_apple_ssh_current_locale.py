#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Select genuine current locale owners without legacy archive precedence."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
from tools.rpi5 import build_apple_ssh_locale_slice as base

ROOT,sha=base.ROOT,base.sha
PACKAGE=ROOT/'build/rpi5/apple-ssh-locale-slice-p7_8ertv'
PACKAGE_SHA='a6411a2990ba6abea004cd17363bb57a7d89559c4703a00d6d923d5facc43fc6'
REMOVE=tuple('locale-'+name+'.o' for name in
             ('table','tolower','toupper','none','nomacros','lconv','localeconv'))


def build():
    if sha(PACKAGE/'manifest.json')!=PACKAGE_SHA:raise ValueError('Locale group changed')
    source=json.loads((PACKAGE/'manifest.json').read_text())
    pins={str(PACKAGE/'manifest.json'):PACKAGE_SHA,str(Path(__file__).resolve()):sha(__file__)}
    for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):
        for n,h in source[key].items():
            if n in pins and pins[n]!=h:raise ValueError('Pin conflict')
            pins[n]=h
    def verify():
        for n,h in pins.items():
            if sha(n)!=h:raise ValueError('Input drift: '+n)
    verify()
    out=Path(tempfile.mkdtemp(prefix='apple-ssh-current-locale-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(out),flush=True);commands=[]
    def run(args,label,allowed=False,cwd=ROOT):
        args=list(map(str,args));p=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=90)
        for suffix in ('stdout','stderr'):(out/(label+'.'+suffix)).write_text(getattr(p,suffix))
        commands.append(dict(command=args,cwd=str(cwd),returncode=p.returncode,
            stdout=str(out/(label+'.stdout')),stderr=str(out/(label+'.stderr'))))
        if p.returncode and not allowed:raise ValueError(label+': '+p.stderr[-4000:])
        return p
    original=base.START/'private-apple-runtime.a'
    listed=run(['xcrun','ar','t',original],'original-members').stdout.splitlines()
    if listed.count('__.SYMDEF SORTED')!=1:raise ValueError('Unexpected BSD archive index')
    # The symbol-table metadata is necessarily rebuilt after member removal;
    # all actual object members, unlike this index, must remain byte-identical.
    members=[n for n in listed if n!='__.SYMDEF SORTED']
    if len(members)!=len(set(members)) or any(Path(n).name!=n for n in members):
        raise ValueError('Unsafe/ambiguous archive member names')
    if not set(REMOVE)<=set(members):raise ValueError('Expected legacy locale owners missing')
    directory=out/'runtime';directory.mkdir()
    run(['xcrun','ar','x',original],'extract',cwd=directory)
    before={n:sha(directory/n) for n in members}
    for n in members:
        raw=subprocess.check_output(['xcrun','ar','p',original,n])
        if hashlib.sha256(raw).hexdigest()!=before[n]:raise ValueError('Extraction mismatch')
    kept=[n for n in members if n not in REMOVE]
    archive=out/'private-apple-runtime-current-locale.a'
    run(['xcrun','ar','rcs',archive,*[directory/n for n in kept]],'archive')
    final_list=run(['xcrun','ar','t',archive],'current-members').stdout.splitlines()
    if final_list.count('__.SYMDEF SORTED')!=1 or [n for n in final_list if n!='__.SYMDEF SORTED']!=kept:
        raise ValueError('Exact archive member removal failed')
    for n in kept:
        raw=subprocess.check_output(['xcrun','ar','p',archive,n])
        if hashlib.sha256(raw).hexdigest()!=before[n]:raise ValueError('Unrelated runtime member changed')
    link=list(next(c['command'] for c in source['commands'] if c['stdout'].endswith('/target-link.stdout')))
    if link.count(str(original))!=1:raise ValueError('Ambiguous original runtime link owner')
    link[link.index(str(original))]=str(archive)
    link[link.index('-o')+1]=str(out/'NOT_RUN_ssh')
    link[link.index('-map')+1]=str(out/'target.map')
    result=run(link,'target-link',True)
    missing=sorted(set(re.findall(r'^\s+"([^"]+)", referenced from:',result.stderr,re.M)))
    duplicate=sorted(set(re.findall(r"duplicate symbol '([^']+)'",result.stderr)))
    if not result.returncode or duplicate:raise ValueError('Unexpected full link/duplicate owner')
    verify()
    report=dict(profile='original-apple-current-locale-explicit-runtime-owners-v1',
        source_inputs_sha256=pins,headers_sha256={},commands=commands,
        current_locale_package=str(PACKAGE),target_archive=source['target_archive'],
        startup_replacement_object=source['objects']['startup-locale'],
        runtime_archive=str(archive),original_runtime_archive=str(original),
        removed_legacy_locale_members=list(REMOVE),before_members_sha256=before,
        archive_index_regenerated=True,
        after_members_sha256={n:before[n] for n in kept},
        target_missing_symbols=missing,target_duplicate_symbols=duplicate,
        previous_group_missing_count=len(source['target_missing_symbols']),
        newly_reachable_dependencies=sorted(set(missing)-set(source['target_missing_symbols'])),
        target_link_complete=False,target_executed=False,network_access=False,
        accepted_runtime_modified=False,
        generated_sha256={str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    (out/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(out),remaining=len(missing),added=report['newly_reachable_dependencies']),indent=2))
    return out,report


if __name__=='__main__':build()
