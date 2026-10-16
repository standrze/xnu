#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Reset trial successor: admit the exact corrected XNU-display restoration.

The frozen reset image, publisher, receive loop and one-shot reboot algorithm
are unchanged. Only the typed baseline and private source namespaces differ.
"""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import phy_reset_trial_v1 as original
import stage_display_xnu_trial_v2 as display_xnu_v2

for _name,_value in vars(original).items():
    if not _name.startswith('__'):
        globals()[_name]=_value


def source_pins():
    names=('phy_reset_trial_v2.py','serial_phy_reset_trial_v2.py',
           'phy_reset_evidence_v2.py','tests/test_phy_reset_trial_v2.py')
    return original.source_pins()|display_xnu_v2.source_pins()|{
        str(ROOT/'tools/rpi5'/name):sha(ROOT/'tools/rpi5'/name) for name in names}


def baseline(directory,seal_sha,plan_sha):
    media=json.loads((local(directory)/'plan.json').read_text()).get('media',{})
    if media.get('controller')!=display_xnu_v2.CONTROLLER:
        return original.baseline(directory,seal_sha,plan_sha)
    if media.get('profile')!=display_xnu_v2.engine.RESTORE:
        raise ValueError('Corrected XNU display must be a completed typed restoration')
    context=display_xnu_v2.restoration(directory,seal_sha,plan_sha)
    files=context['result']['publication']['protected_files_sha256']
    if (files.get('config.txt')!=compact.engine.ORIGINAL_CONFIG_SHA or
            any(files.get(name)!=value[1] for name,value in GOOD.items())):
        raise ValueError('Exact original config/firmware/zsh restoration required')
    return context


def load_descriptor(reference):
    import serial_phy_reset_trial_v2
    import phy_reset_evidence_v2
    selected=get_descriptor(reference)
    protocol=selected['protocol']
    names=('inspect','inventory','return_positions','PREFIX','BEGIN','TRANSFER',
           'ENTRY','COMMIT','PREPARED','PREPARED_PREFIX')
    if (any(not hasattr(protocol,name) for name in names) or
            protocol.PREPARED_PREFIX!=protocol.PREFIX+b'PREPARED '):
        raise ValueError('Complete exact reset capture/replay API required')
    return selected


def admit(checkpoint):
    import serial_phy_reset_trial_v2 as recorder
    media=checkpoint['payload']['media_plan']
    selected=load_descriptor(media['descriptor']);report=media['preflight']
    valid_report(report,selected)
    context=dict(descriptor=selected,evidence=checkpoint['evidence_sha256'],installed=dict(
        directory=str(ROOT/'build/rpi5/prepublication-only-no-installation'),preflight=report))
    sources=recorder.bound_sources(context);bound=recorder.bindings(context)
    if (Path(bound.__globals__['__file__']).resolve()!=ROOT/'tools/rpi5/serial_phy_reset_trial_v2.py' or
            bound.__globals__['protocol'] is not selected['protocol'] or
            bound.__globals__['assert_modem_ready'] is not recorder.assert_modem_ready or
            Path(recorder.stage.__file__).resolve()!=ROOT/'tools/rpi5/phy_reset_trial_v2.py'):
        raise ValueError('Exact corrected reset namespace and modem gate required')
    return dict(actual_recorder_source_members=len(sources),actual_package_report_bound=True,
        recorder_namespace_bound_without_serial=True,modem_gate_bound_before_arm=True,hardware_executed=False)


def import_(name,*args,**kwargs):
    if name=='pcie_trial_evidence_v3':return builtins.__import__('phy_reset_evidence_v2',*args,**kwargs)
    if name=='serial_pcie_trial_v3':return builtins.__import__('serial_phy_reset_trial_v2',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)


scoped=dict(vars(builtins),__import__=import_)
_changes=dict(baseline=baseline,source_pins=source_pins,load_descriptor=load_descriptor,
              admit=admit,__builtins__=scoped,__doc__=__doc__,__file__=__file__)
_functions={name:private(getattr(original,name),**_changes) for name in
    ('_prepare_install','load_installation','completed_restore','prepare_install',
     'prepare_restore','launch','replay','main')}
for _name,_function in _functions.items():
    _function.__globals__.update(_functions)
    globals()[_name]=_function
# Replay's baseline is its own exact pair-restoration validator, not intake.
replay.__globals__['baseline']=completed_restore

if __name__=='__main__':main()
