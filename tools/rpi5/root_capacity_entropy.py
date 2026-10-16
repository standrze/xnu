#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct root43→45: two future API diagnostics, no random-quality claim."""
import json
from pathlib import Path
import tempfile
from tools.rpi5 import check_root43_packet_root as baseline
from tools.rpi5 import root_capacity_commands as old

ROOT,sha=old.ROOT,old.sha
BASE=baseline.PACKAGE
IDENTITY=old.IDENTITY
PROFILE='rpi5-root96-entropy-api-batch-v1'
PROBES={
 '/usr/local/libexec/xnu/entropyprobe':(
  ROOT/'build/rpi5/apple-entropy-api-x4zxvaug',
  'b488248ba8522edfd445d5b4d36bc0b260feef92171451d41d2af1dedc842c47',
  'a998573358dec3c362c0ec41a74f48e1e61ca4d770ac3495fd1790289298cd50'),
 '/usr/local/libexec/xnu/kernel_randprobe':(
  ROOT/'build/rpi5/kernel-entropy-rand-hfrb7y67',
  'f46bd17a8171c4272985875cfbb6a49d7305a49e26d2ee716facbe6aaac924f8',
  'fed221215a29d62909e169f44bc66abac15603967db3f252737f419f30dca14a'),
}
TESTS=('tests/test_apple_entropy_probe.py','tests/entropy_api_contract.c',
       'tests/test_kernel_entropy_rand_probe.py','tests/kernel_entropy_arc4random_contract.c')
LIMITS=dict(probes_not_run=True,host_tests_not_target_execution=True,entropy_not_qualified=True,
    firmware_not_attested=True,live_keys=False,raw_random_output=False,project_adapter_not_apple_corecrypto=True,
    health_startup_zero_is_observation_not_qualification=True,existing_packet_kats_unchanged=True,
    allocator_default_zone_only=True,modern_full_libsystem_not_claimed=True)
merge=baseline.prior_check.merge
static_entry=baseline.prior_check.static_entry
dependencies=baseline.prior_check.dependencies


def inputs():
    baseline.inspect(BASE)
    prior=json.loads((BASE/'manifest.json').read_text());pins=dict(prior['inputs_sha256'])
    merge(pins,prior['generated_sha256']);probes={}
    for entry,(directory,manifest_sha,target_sha) in PROBES.items():
        report=old.receipt(directory/'manifest.json',manifest_sha)
        if not report['target_link_complete'] or report['target_missing_symbols'] or sha(Path(report['target']))!=target_sha:
            raise ValueError('Exact clean diagnostic target required')
        if report['entropy_qualified'] is not False or report['pi_executed'] is not False:
            raise ValueError('Offline diagnostic limits changed')
        for key in ('source_inputs_sha256','headers_sha256','generated_sha256'):merge(pins,report[key])
        merge(pins,{str(directory/'manifest.json'):manifest_sha});probes[entry]=report
    for path in (BASE/'manifest.json',Path(__file__).resolve(),Path(baseline.__file__).resolve(),
                 *(ROOT/'tools/rpi5'/name for name in TESTS)):
        merge(pins,{str(path):sha(path)})
    old.verify(pins);return pins,prior,probes


def build():
    pins,prior,probes=inputs()
    original=old.profile.files_from((BASE/'ramdisk.bin').read_bytes())
    if len(original)!=31 or set(PROBES)&set(original):raise ValueError('Exact root43 baseline required')
    output=Path(tempfile.mkdtemp(prefix='root96-entropy-batch-',dir=ROOT/'build/rpi5'))
    print('OUTPUT='+str(output),flush=True)
    expanded=dict(original);audits={}
    for entry,report in probes.items():
        expanded[entry]=(Path(report['target']).read_bytes(),0o555)
        audits[entry]=static_entry(expanded[entry][0],'_darwin_static_start')
    _,layout=old.profile.build(expanded);rows=[]
    for entry in layout['entries']:
        path,isdir=entry['path'],entry['type']=='directory'
        rows.append(dict(path=path,mode=entry['mode']|(0o40000 if isdir else 0o100000),
            bytes=0 if isdir or path==IDENTITY else len(expanded[path][0]),
            sha256='' if isdir else None if path==IDENTITY else old.profile.sha(expanded[path][0])))
    (output/'rootidentity_catalog.h').write_text(old.identity.header(rows))
    compile_args=next(list(r['command']) for r in prior['commands'] if '-c' in r['command'] and r['command'][-1]==str(BASE/'identity.d'))
    compile_args=compile_args[:compile_args.index('-MD')];old_object=compile_args[compile_args.index('-o')+1]
    obj=output/'rootidentity.o';compile_args[compile_args.index('-o')+1]=str(obj)
    compile_args=['-I'+str(output) if x=='-I'+str(BASE) else x for x in compile_args]
    if '-I'+str(output) not in compile_args:raise ValueError('Catalog include not rebound')
    commands=[];old.compile_actual(compile_args,output,'identity',commands,pins)
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
    if len(layout['entries'])!=45 or len(expanded)!=33 or old.profile.files_from(raw)!=expanded:
        raise ValueError('Exact45-node/33-file round trip required')
    if any(expanded[p]!=v for p,v in original.items() if p!=IDENTITY):raise ValueError('Baseline file changed')
    (output/'ramdisk.bin').write_bytes(raw);old.verify(pins)
    report=dict(profile=PROFILE,node_capacity=96,baseline=str(BASE),baseline_manifest_sha256=baseline.MANIFEST_SHA,
        input_root_sha256=baseline.IMAGE_SHA,output_sha256=old.profile.sha(raw),output_bytes=len(raw),output_nodes=45,output_files=33,
        identity_catalog=rows,identity_self_digest_compared_externally=True,commands=commands,inputs_sha256=pins,
        added_files_sha256={p:row[2] for p,row in PROBES.items()},changed_files_sha256={IDENTITY:sha(output/'socketprobe')},
        unchanged_files_sha256={p:old.profile.sha(v[0]) for p,v in original.items() if p!=IDENTITY},
        canonical_path=old.CANONICAL_PATH,compatibility_regular_files=old.ALIASES,
        default_init_and_shell_unchanged=True,frozen_zsh_unchanged=True,probe_executable_audits=audits,
        probe_manifests={p:{'path':str(row[0]/'manifest.json'),'sha256':row[1]} for p,row in PROBES.items()},
        required_trial_commands=prior['required_trial_commands']+list(PROBES),limits=LIMITS,
        installed=False,pi_executed=False,ssh_proven=False,networking_proven=False,sd_actions=0,serial_actions=0,reboots=0,
        generated_sha256={str(p):sha(p) for p in output.iterdir() if p.is_file()})
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(dict(package=str(output),sha256=report['output_sha256'],nodes=45,files=33),indent=2))
    return output,report


if __name__=='__main__':build()
