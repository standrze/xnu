#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact root45 successor; frozen single-loader publication safeguards.

Intake is a completed typed original-pair restoration.
Only the loader changes; normal firmware/current rollback protections remain.
"""
import importlib
import inspect
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_root42_pthread_trial as base
import stage_root43_packet_trial as previous
import prepare_root42_pthread_trial_v3 as graph

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private,engine,GOOD=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private','engine','GOOD'))
CONTROLLER='root45-entropy-state-confirmed-single-loader-v1'
PACKAGE=ROOT/'build/rpi5/root45-entropy-mob0oyvx'
MANIFEST_SHA='8a3b8ab64840457e8647ce43482dd5ecb5762b3756136f1f091618570b9440c1'
IMAGE_SHA='90f24fea6ca7dd83345b3aedefdaf12c50334ba6d41272b17386517f7d555d75'


def baseline(directory,seal_sha,plan_sha):
    # The fixed pair validator revalidates the supplied canonical seal, plan,
    # result and original pair. Do not send this baseline to a loader reader.
    record=json.loads((local(directory)/'checkpoint.json').read_text())
    profile=record['payload']['media_plan']['profile']
    if profile==base.prior.engine.RESTORE:return base.prior.baseline(directory,seal_sha,plan_sha)
    raise ValueError('Completed typed original-pair restoration required')


prior=types.SimpleNamespace(**{**vars(base.prior),'package_graph':graph.package_graph,'baseline':baseline})


def transport():
    import serial_root45_entropy_trial
    import root45_entropy_command_evidence
    import root45_entropy_evidence
    import arm_root45_entropy_reboot
    importlib.import_module('check_root45_entropy_package')
    return root45_entropy_evidence


def source_pins():
    names=('stage_root45_entropy_trial.py','serial_root45_entropy_trial.py','root45_entropy_trial_core.py',
        'root45_entropy_command_evidence.py','root45_entropy_evidence.py','arm_root45_entropy_reboot.py',
        'tests/test_root45_entropy_transport.py','root_capacity_entropy.py','check_root45_entropy_root.py',
        'build_root45_entropy_package.py','check_root45_entropy_package.py','tests/test_root45_entropy_package.py',
        'tests/test_apple_entropy_probe.py','tests/entropy_api_contract.c','tests/test_kernel_entropy_rand_probe.py','tests/kernel_entropy_arc4random_contract.c')
    return previous.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


checker=types.SimpleNamespace(inspect=lambda path:importlib.import_module('check_root45_entropy_package').inspect(path))
scope={**vars(base),**{n:globals()[n] for n in ('CONTROLLER','PACKAGE','MANIFEST_SHA','IMAGE_SHA','prior','checker','transport','source_pins')},
    '__file__':__file__,'__doc__':__doc__}
source=inspect.getsource(base.prepare_install)
old="report['root_nodes']!=42 or report['root_files']!=30"
if source.count(old)!=1:raise ValueError('Frozen geometry admission boundary changed')
exec(compile(source.replace(old,"report['root_nodes']!=45 or report['root_files']!=33"),__file__,'exec'),scope)
_prepare_install=scope['prepare_install']
for name in ('sealed_operation','load_installation','prepare_restore','restoration','replay','dispatch','_dispatch','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]


def admit(checkpoint):
    import serial_root45_entropy_trial as recorder
    context={'installed':{'preflight':checkpoint['payload']['media_plan']['preflight']},'evidence':checkpoint['evidence_sha256']}
    recorder.core.validate_report(context['installed']['preflight'])
    packages=recorder.package_pins(context);sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_root45_entropy_trial.py':
        raise ValueError('Exact root45 recorder execution namespace required')
    return dict(actual_recorder_package_members=len(packages),actual_recorder_source_members=len(sources),
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,boot,package=PACKAGE):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,boot,package)
    metrics['recorder_admission']=admit(checkpoint)
    return checkpoint,pin,metrics
scope['prepare_install']=prepare_install


if __name__=='__main__':raise SystemExit(main())
