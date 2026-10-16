# SPDX-License-Identifier: BSD-2-Clause
"""Exact config32/console-record loader pair; normal firmware is protected."""
import hashlib
from pathlib import Path
import types
try:
    from . import display_restart_late_media_v1 as parent
except ImportError:
    import display_restart_late_media_v1 as parent

PARENT=Path(parent.__file__).resolve()
PARENT_SHA='b7c9bd68043306153e64c2de0c2749f188253997101239afeeb9b76296d253fd'
if hashlib.sha256(PARENT.read_bytes()).hexdigest()!=PARENT_SHA:raise ValueError('Frozen config/loader engine required')
TRIAL='display-console-records-config-loader-trial-v1'
RESTORE='display-console-records-config-loader-restore-v1'
FORMAT='rpi5-display-console-records-config-loader-plan-v1'
RESULT='rpi5-display-console-records-config-loader-result-v1'
IMAGE_SHA='735f901b07895e1cbf6460c0657d46268e77871683d1f90d882efccf2d19316b'
IMAGE_BYTES=20187584
for _name in ('SOURCE','SOURCE_SHA','HELPERS','GOOD_FW_SHA','GOOD_FW_BYTES','ORIGINAL_CONFIG',
        'ORIGINAL_CONFIG_SHA','TRIAL_CONFIG','TRIAL_CONFIG_SHA','catalog','select_baseline','same'):
    globals()[_name]=getattr(parent,_name)
for _name in ('copy','json','os','re','original','seals'):
    globals()[_name]=getattr(parent,_name)

def _bind(name):return types.FunctionType(getattr(parent,name).__code__,globals(),name,
    getattr(parent,name).__defaults__,getattr(parent,name).__closure__)
for _name in ('bound_core','plan_from_seal','validate_plan','validate_result','execute'):
    globals()[_name]=_bind(_name)

def source_pins():
    pins=parent.source_pins();pins[str(PARENT)]=PARENT_SHA;pins[str(Path(__file__).resolve())]=parent.seals.sha(Path(__file__).resolve())
    parent.seals.check_pins(pins);return pins

def remote_source(checkpoint,checkpoint_sha,plan,expected_plan_sha):
    payload=checkpoint['payload'];fresh,fresh_sha=plan_from_seal(checkpoint,checkpoint_sha,
        plan['media']['profile'],plan['tag'],plan['media']['run'],payload['media_plan'])
    if not same(plan,fresh) or expected_plan_sha!=fresh_sha:raise ValueError('Remote dispatch differs from byte-sealed plan')
    names=('capture','helper','snapshots','reference','guarded')
    modules=[(name,SOURCE.parent/file) for name,file in zip(names,HELPERS)]
    modules += [('pcie_trace_pair_core',SOURCE),('trial_checkpoint_v2',Path(parent.seals.__file__).resolve())]
    code='import types,sys,json\n'
    for name,path in modules:
        text=path.read_text()
        if hashlib.sha256(text.encode()).hexdigest()!=checkpoint['evidence_sha256'].get(str(path)):
            raise ValueError('Dispatched engine source differs from sealed closure')
        code+=f'{name}=types.ModuleType({name!r})\nsys.modules[{name!r}]={name}\n'
        code+=f'{name}.__file__={str(path)!r}\n{name}.__package__=""\n{name}._active_window_source={text!r}\n'
        code+=f'exec({text!r},{name}.__dict__)\n'
    text=PARENT.read_text()+f'\nTRIAL={TRIAL!r}\nRESTORE={RESTORE!r}\nFORMAT={FORMAT!r}\nRESULT={RESULT!r}\nIMAGE_SHA={IMAGE_SHA!r}\nIMAGE_BYTES={IMAGE_BYTES!r}\n'
    code+='display_console_records_media_v1=types.ModuleType("display_console_records_media_v1")\n'
    code+='display_console_records_media_v1.__file__='+repr(str(Path(__file__).resolve()))+'\n'
    code+='display_console_records_media_v1.__package__=""\nexec('+repr(text)+',display_console_records_media_v1.__dict__)\n'
    code+='PLAN=json.loads('+repr(__import__('json').dumps(plan))+')\n'
    code+='print(json.dumps(display_console_records_media_v1.execute(PLAN,'+repr(expected_plan_sha)+',capture,helper,snapshots,reference,guarded)))\n'
    compile(code,'<console-records-config-loader-remote>','exec');return code
