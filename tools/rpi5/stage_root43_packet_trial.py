#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact root43 successor; frozen single-loader publication safeguards.

Intake is a completed typed state-confirmed loader or original-pair restoration.
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
import stage_root42_ready_trial as previous
import prepare_root42_pthread_trial_v3 as graph

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private,engine,GOOD=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private','engine','GOOD'))
CONTROLLER='root43-packet-state-confirmed-single-loader-v1'
PACKAGE=ROOT/'build/rpi5/root43-packet-vqgxaczi'
MANIFEST_SHA='e9a093d1006ebcab38ffdfb93bf776db43e73e35c2f879d61fb0bcba6572aaf6'
IMAGE_SHA='d5d3c29905ed191aa848867416bfc0444ce93f43b30ad6843dc0236d9a8c8340'


def baseline(directory,seal_sha,plan_sha):
    # Untrusted type chooses only one of two fixed reviewed validators. Both
    # independently revalidate the supplied canonical seal/plan/result/current
    # original pair; this dispatch does not trust counts, names or filenames.
    record=json.loads((local(directory)/'checkpoint.json').read_text())
    profile=record['payload']['media_plan']['profile']
    if profile==engine.RESTORE:return previous.restoration(directory,seal_sha,plan_sha)
    if profile==base.prior.engine.RESTORE:return base.prior.baseline(directory,seal_sha,plan_sha)
    raise ValueError('Completed typed loader or pair restoration required')


prior=types.SimpleNamespace(**{**vars(base.prior),'package_graph':graph.package_graph,'baseline':baseline})


def transport():
    import serial_root43_packet_trial
    import root43_packet_command_evidence
    import root43_packet_evidence
    import arm_root43_packet_reboot
    importlib.import_module('check_root43_packet_package')
    return root43_packet_evidence


def source_pins():
    names=('stage_root43_packet_trial.py','serial_root43_packet_trial.py','root43_packet_trial_core.py',
        'root43_packet_command_evidence.py','root43_packet_evidence.py','arm_root43_packet_reboot.py',
        'tests/test_root43_packet_transport.py','root_capacity_packet.py','check_root43_packet_root.py',
        'build_root43_packet_package.py','check_root43_packet_package.py','tests/test_root43_packet_package.py',
        'tests/test_ssh_packet_pthread_contract.py','tests/libressl_caps_contract.c','tests/libressl_pthread_abi_contract.c')
    return previous.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


checker=types.SimpleNamespace(inspect=lambda path:importlib.import_module('check_root43_packet_package').inspect(path))
scope={**vars(base),**{n:globals()[n] for n in ('CONTROLLER','PACKAGE','MANIFEST_SHA','IMAGE_SHA','prior','checker','transport','source_pins')},
    '__file__':__file__,'__doc__':__doc__}
source=inspect.getsource(base.prepare_install)
old="report['root_nodes']!=42 or report['root_files']!=30"
if source.count(old)!=1:raise ValueError('Frozen geometry admission boundary changed')
exec(compile(source.replace(old,"report['root_nodes']!=43 or report['root_files']!=31"),__file__,'exec'),scope)
_prepare_install=scope['prepare_install']
for name in ('sealed_operation','load_installation','prepare_restore','restoration','replay','dispatch','_dispatch','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]


def admit(checkpoint):
    import serial_root43_packet_trial as recorder
    context={'installed':{'preflight':checkpoint['payload']['media_plan']['preflight']},'evidence':checkpoint['evidence_sha256']}
    recorder.core.validate_report(context['installed']['preflight'])
    packages=recorder.package_pins(context);sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_root43_packet_trial.py':
        raise ValueError('Exact root43 recorder execution namespace required')
    return dict(actual_recorder_package_members=len(packages),actual_recorder_source_members=len(sources),
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


def prepare_install(directory,prior_seal,prior_plan,boot,package=PACKAGE):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,boot,package)
    metrics['recorder_admission']=admit(checkpoint)
    return checkpoint,pin,metrics
scope['prepare_install']=prepare_install


if __name__=='__main__':raise SystemExit(main())
