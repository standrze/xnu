#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact late-root successor over the frozen single-loader publisher.

Only this distinct package/controller/protocol is selected. No publisher,
archive, current-board guard, retry or restoration policy is changed.
"""
import importlib
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_root42_pthread_trial as base
import prepare_root42_pthread_trial_v3 as graph

ROOT,HOST,SSH,sha,local,seals,lease,save,save_bytes,private,engine,GOOD=(getattr(base,k) for k in
    ('ROOT','HOST','SSH','sha','local','seals','lease','save','save_bytes','private','engine','GOOD'))
CONTROLLER='root42-state-confirmed-single-loader-v1'
PACKAGE=ROOT/'build/rpi5/root42-ready-4h4evl7f'
MANIFEST_SHA='2726e1c4c66c79d47c9899354c63564c5652311b6f2e06133fff39982f1952b3'
IMAGE_SHA='6a8bcf69863ecba29f4375ed9df89806ff7de5a37f9c51d2fd1465fbdca5f793'
# This trial starts from the completed BAR pair restoration; retain the exact
# existing typed pair-restoration intake, not the earlier loader-only intake.
prior=types.SimpleNamespace(**{**vars(base.prior),'package_graph':graph.package_graph})


def transport():
    import serial_root42_ready_trial
    import root42_ready_command_evidence
    import root42_ready_evidence
    import arm_root42_ready_reboot
    importlib.import_module('check_root42_ready_package')
    return root42_ready_evidence


def source_pins():
    names=('stage_root42_ready_trial.py','serial_root42_ready_trial.py','root42_ready_trial_core.py',
        'root42_ready_command_evidence.py','root42_ready_evidence.py','arm_root42_ready_reboot.py',
        'tests/test_root42_ready_transport.py','build_root42_ready_package.py','check_root42_ready_package.py',
        'tests/test_root42_ready_package.py','tests/test_root42_confirmation_service.py')
    return graph.source_pins()|{str(ROOT/'tools/rpi5'/n):sha(ROOT/'tools/rpi5'/n) for n in names}


checker=types.SimpleNamespace(inspect=lambda path:importlib.import_module('check_root42_ready_package').inspect(path))
scope={**vars(base),**{n:globals()[n] for n in ('CONTROLLER','PACKAGE','MANIFEST_SHA','IMAGE_SHA','prior','checker','transport','source_pins')},
    '__file__':__file__,'__doc__':__doc__}
# All private functions share one complete namespace, including later entries.
for name in ('prepare_install','sealed_operation','load_installation','prepare_restore','restoration','replay','dispatch','_dispatch','main'):
    fn=getattr(base,name);defaults=(PACKAGE,) if name=='prepare_install' else fn.__defaults__
    scope[name]=types.FunctionType(fn.__code__,scope,argdefs=defaults)
    globals()[name]=scope[name]


def admit(checkpoint):
    import serial_root42_ready_trial as recorder
    context={'installed':{'preflight':checkpoint['payload']['media_plan']['preflight']},
        'evidence':checkpoint['evidence_sha256']}
    report=context['installed']['preflight'];recorder.core.contract(report)
    packages=recorder.package_pins(context);sources=recorder.bound_sources(context)
    bound=recorder.bindings(context)
    if Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_root42_ready_trial.py':
        raise ValueError('Exact new recorder execution namespace required')
    return dict(actual_recorder_package_members=len(packages),actual_recorder_source_members=len(sources),
        recorder_namespace_bound_without_serial=True,hardware_executed=False)


_prepare_install=prepare_install
def prepare_install(directory,prior_seal,prior_plan,boot,package=PACKAGE):
    checkpoint,pin,metrics=_prepare_install(directory,prior_seal,prior_plan,boot,package)
    metrics['recorder_admission']=admit(checkpoint)
    return checkpoint,pin,metrics
scope['prepare_install']=prepare_install


if __name__=='__main__':raise SystemExit(main())
