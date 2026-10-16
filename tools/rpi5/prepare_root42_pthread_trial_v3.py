#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Root42 preparation retaining literal manifest aliases and resolved bytes.

The preceding complete audit is preserved. This distinct preparation requires
both names for every top-level consumed input and proves recorder admission.
"""
import argparse
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare_root42_pthread_trial_v2 as preceding
import serial_root42_pthread_trial as recorder
stage=preceding.stage


def retain_literal_pins(manifest,pins):
    result=dict(pins);record=json.loads(manifest.read_text())
    for key in ('inputs_sha256','headers_sha256','generated_sha256'):
        for name,expected in record[key].items():
            actual=result.get(name);resolved=str(Path(name).resolve())
            if actual is not None and actual!=expected:raise ValueError('Conflicting literal manifest input')
            if result.get(resolved)!=expected:raise ValueError('Manifest alias has no identically sealed resolved target')
            if stage.sha(name)!=expected:raise ValueError('Literal manifest input bytes differ')
            result[name]=expected
    return result


def package_graph(package,prior_pins):
    return retain_literal_pins(package/'manifest.json',preceding.package_graph(package,prior_pins))


def source_pins():
    files=(Path(__file__).resolve(),stage.ROOT/'tools/rpi5/tests/test_root42_prepare_aliases.py')
    return preceding.source_pins()|{str(p):stage.sha(p) for p in files}


def admit(checkpoint):
    context={'installed':{'preflight':checkpoint['payload']['media_plan']['preflight']},'evidence':checkpoint['evidence_sha256']}
    pins=recorder.package_pins(context);sources=recorder.bound_sources(context);recorder.bindings(context)
    return dict(actual_recorder_package_members=len(pins),actual_recorder_source_members=len(sources),
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,boot,package=stage.PACKAGE):
    prior=types.SimpleNamespace(**{**vars(stage.prior),'package_graph':package_graph})
    checkpoint,pin,metrics=stage.private(stage.prepare_install,prior=prior,source_pins=source_pins)(directory,prior_seal,prior_plan,boot,package)
    admit(checkpoint)
    return checkpoint,pin,metrics


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--prior-seal-sha256',required=True);p.add_argument('--prior-plan-sha256',required=True)
    p.add_argument('--linux-boot-id',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args(argv)
    checkpoint,pin,metrics=prepare_install(a.baseline,a.prior_seal_sha256,a.prior_plan_sha256,a.linux_boot_id)
    admission=admit(checkpoint);out=stage.local(a.output);out.mkdir(exist_ok=False)
    stage.seals.save_new(out/'checkpoint.json',checkpoint,pin);stage.save(out/'metrics.json',metrics);stage.save(out/'admission.json',admission)
    print(json.dumps(dict(status='prepared_only',checkpoint_sha256=pin,output=str(out),metrics=metrics,admission=admission),indent=2,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
