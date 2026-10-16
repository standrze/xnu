#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent target-stack receipts for the complete retry package."""
import argparse
import inspect as pyinspect
import json
from pathlib import Path
import re
from tools.rpi5 import build_gem_cpu_ring_retry_trial as b
from tools.rpi5 import audit_gem_batch_startup_stack as startup
from tools.rpi5 import audit_gem_batch_stack as live
from tools.rpi5 import audit_gem_rp1_loader_stack as rp1

PROFILE='gem-ring-only-retry-target-stack-qualification-v1'
MEASUREMENTS=b.ROOT/'build/rpi5/gem-batch-stack-measurements-20261014-v6/measurements.json'
MEASUREMENTS_SHA='c46e9603261c74841a9fe55278f77e253c82a452f217cf3b0ff9b4d3547e11fe'
def read(path,pin):
    path=Path(path).resolve()
    if not re.fullmatch('[0-9a-f]{64}',pin) or b.sha(path)!=pin:raise ValueError('Exact evidence pin differs')
    return json.loads(path.read_bytes())
def configure():
    b.configure();startup.PROFILE=b.PROFILE
def owned_bounds(package,measurements,early):
    source=pyinspect.getsource(live.owned_bounds)
    changes=(("'bcm2712-gem-real-cpu-owned-batch-trial-v1'",repr(b.PROFILE),1),
        ("'kernel-rpi5_gem_ring_batch'","'kernel-rpi5_gem_ring_only_batch'",5),
        ("'rpi5_gem_ring_batch'","'rpi5_gem_ring_only_batch'",2),
        ("p('8disabledEP')","p('12preferredRAMEP')",1))
    for old,new,count in changes:
        if source.count(old)!=count:raise ValueError('Exact stack adapter anchor differs: '+old)
        source=source.replace(old,new)
    namespace=dict(live.__dict__);exec(compile(source,str(Path(live.__file__))+'[retry-profile-only]','exec'),namespace)
    return namespace['owned_bounds'](package,measurements,early)
def inspect(package,manifest_sha,qualification,qualification_sha):
    configure();package=Path(package).resolve();m=read(package/'manifest.json',manifest_sha);q=read(qualification,qualification_sha)
    if q.get('profile')!=PROFILE or q.get('package')!=str(package) or q.get('package_manifest_sha256')!=manifest_sha:raise ValueError('Exact retry qualification required')
    if (q.get('measurements'),q.get('measurements_sha256'))!=(str(MEASUREMENTS),MEASUREMENTS_SHA):raise ValueError('Exact owner measurements required')
    e=read(q['early_audit'],q['early_audit_sha256'])
    if (e.get('admitted_input_profile')!=b.PROFILE or e.get('manifest_substituted') is not False or e.get('stack_bytes')!=16384 or
        type(e.get('maximum_conservative_bytes')) is not int or e['maximum_conservative_bytes']+512>=16384):raise ValueError('Early stack proof differs')
    for group in ('inputs_sha256','generated_sha256'):
        for path,pin in e[group].items():
            if b.sha(path)!=pin:raise ValueError('Early receipt drift')
    read(MEASUREMENTS,MEASUREMENTS_SHA);actual=owned_bounds(package,MEASUREMENTS,q['early_audit'])
    if json.dumps(actual,sort_keys=True)!=json.dumps(q['owned_paths'],sort_keys=True) or actual['maximum_owned_path_bytes']+512>=16384:raise ValueError('Owned path proof differs')
    read(q['rp1_measurements'],q['rp1_measurements_sha256']);loader=rp1.inspect(package,q['rp1_measurements'])
    if json.dumps(loader,sort_keys=True)!=json.dumps(q['rp1_path'],sort_keys=True):raise ValueError('RP1 loader proof differs')
    if m['reservation_stack_budget']['conservative_bytes']+512>=32768:raise ValueError('Loader stack exceeds bound')
    for path,pin in q['source_sha256'].items():
        if b.sha(path)!=pin or m['inputs_sha256'].get(path)!=pin:raise ValueError('Qualification source not package-bound')
    expected=set(map(str,map(Path,[__file__,startup.__file__,live.__file__,rp1.__file__])))
    if set(q['source_sha256'])!={str(Path(p).resolve()) for p in expected}:raise ValueError('Qualification source set differs')
    return dict(profile=PROFILE,qualification_sha256=qualification_sha,early_kernel_maximum=e['maximum_conservative_bytes'],
        live_owned_maximum=actual['maximum_owned_path_bytes'],rp1_loader_maximum=loader['maximum_conservative_bytes'],
        loader_finalization_maximum=m['reservation_stack_budget']['conservative_bytes'],target_stack_receipts_bound=True,
        whole_kernel_stack_proven=False,compiler_replayed=False,hardware_executed=False)
def make(package,manifest_sha,output):
    configure();package=Path(package).resolve();read(package/'manifest.json',manifest_sha);output=Path(output).resolve()
    if output.parent!=b.ROOT/'build/rpi5' or output.exists():raise ValueError('Distinct qualification output required')
    early=output.with_name(output.name+'-early');device=output.with_name(output.name+'-rp1')
    if early.exists() or device.exists():raise ValueError('Qualification phase exists')
    output.mkdir();startup.audit(package,early);rp1.measure(package,device);read(MEASUREMENTS,MEASUREMENTS_SHA)
    q=dict(profile=PROFILE,package=str(package),package_manifest_sha256=manifest_sha,measurements=str(MEASUREMENTS),measurements_sha256=MEASUREMENTS_SHA,
        early_audit=str(early/'audit.json'),early_audit_sha256=b.sha(early/'audit.json'),rp1_measurements=str(device/'measurements.json'),
        rp1_measurements_sha256=b.sha(device/'measurements.json'),owned_paths=owned_bounds(package,MEASUREMENTS,early/'audit.json'),
        rp1_path=rp1.inspect(package,device/'measurements.json'),source_sha256={str(Path(p).resolve()):b.sha(p) for p in (__file__,startup.__file__,live.__file__,rp1.__file__)})
    target=output/'qualification.json';target.write_text(json.dumps(q,sort_keys=True,indent=2)+'\n')
    return target,inspect(package,manifest_sha,target,b.sha(target))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);p.add_argument('--manifest-sha256',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();path,result=make(a.package,a.manifest_sha256,a.output);print(json.dumps(dict(qualification=str(path),qualification_sha256=b.sha(path),result=result),sort_keys=True))
