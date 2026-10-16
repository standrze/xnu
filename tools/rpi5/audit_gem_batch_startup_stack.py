#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct explicit adapter for the frozen successful startup stack audit.

Only the admitted input profile changes. The genuine manifest is never edited
or substituted. All measured owners, actual code equality, stack calculations
and original16KiB limit are inherited from exact pinned audit source. This does
not cover the later sleepable controller/provider/ring path.
"""
import argparse
import ast
import json
from pathlib import Path
from tools.rpi5 import audit_reservation_kernel_stack as old
PIN='bdd597817deff5964761fc234d4dcda59d9b40597f35fa4be28ab29f51d7dc63'
PROFILE='bcm2712-gem-real-cpu-owned-batch-trial-v1'
OLD_PROFILE='bcm2712-gem-owned-rings-resolved-reservations-default-off-v1'
def derived_audit():
    path=Path(old.__file__).resolve()
    if old.sha(path)!=PIN:raise ValueError('Frozen startup audit changed')
    text=path.read_text();tree=ast.parse(text)
    functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='audit']
    if len(functions)!=1:raise ValueError('Exact audit function required')
    node=functions[0];source='\n'.join(text.splitlines()[node.lineno-1:node.end_lineno])+'\n'
    literal=repr(OLD_PROFILE)
    if source.count(literal)!=1:raise ValueError('Exact old profile predicate required')
    source=source.replace(literal,repr(PROFILE),1)
    namespace=dict(old.__dict__)
    exec(compile(source,str(path)+'[batch-profile-only]','exec'),namespace)
    return namespace['audit'],source
def audit(package,output):
    package=Path(package).resolve();m=json.loads((package/'manifest.json').read_bytes())
    if m.get('profile')!=PROFILE:raise ValueError('Exact real batch startup profile required')
    own=Path(__file__).resolve();test=old.ROOT/'tools/rpi5/tests/test_gem_batch_startup_stack.py'
    pins={str(p):old.sha(p) for p in (own,test)}
    function,_=derived_audit();r=function(package,output)
    r['profile']='pi5-gem-batch-successful-startup-stack-audit-v1'
    r['admitted_input_profile']=PROFILE;r['frozen_audit_source_sha256']=PIN
    r['manifest_substituted']=False;r['later_ring_stack_proven']=False
    r['inputs_sha256'].update(pins)
    for path,pin in pins.items():
        if old.sha(path)!=pin:raise ValueError('Adapter input drift')
    # The inherited audit.json itself is not a generated input; replace only
    # this new derived report, never the immutable parent audit or package.
    (Path(output)/'audit.json').write_text(json.dumps(r,sort_keys=True,indent=2)+'\n')
    return r
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(a.package,a.output)
    print(json.dumps(dict(audit_sha256=old.sha(a.output/'audit.json'),paths=r['paths_conservative_bytes'],remaining=r['minimum_remaining_bytes'])))
