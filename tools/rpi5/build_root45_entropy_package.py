#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct45-node diagnostic loader; unchanged accepted kernel and firmware."""
import json
from pathlib import Path
import types
from tools.rpi5 import build_root43_packet_package as prior

ROOT=prior.ROOT
ready=prior.ready
FROZEN={
 'build_root43_packet_package.py':'2f3e77614263f37df6a48ab54bebd9dcb916a2be2a75e3cb41aa3d9b0ce89ad7',
 'check_root43_packet_package.py':'825e81e9230c075ae3584f6308f9608b6084c75ca3cc1498c854a333c171d915',
}
for name,digest in FROZEN.items():
    if prior.sha(ROOT/'tools/rpi5'/name)!=digest:raise ValueError('Frozen packet package source changed')
source=prior.source
for old,new,count in (
 ('check_root43_packet_root as root_check','check_root45_entropy_root as root_check',2),
 ("PROFILE='root43-packet-mounted-ready-retained-fdt-v1'","PROFILE='root45-entropy-mounted-ready-retained-fdt-v1'",1),
 ('check_root43_packet_package.py','check_root45_entropy_package.py',1),
 ('tests/test_root43_packet_package.py','tests/test_root45_entropy_package.py',1),
 ('ROOT43_PACKET_TRIAL TAG=','ROOT45_ENTROPY_TRIAL TAG=',1),
 ('CPUS=4 ROOT_NODES=43 WATCHDOG_READY_V2','CPUS=4 ROOT_NODES=45 WATCHDOG_READY_V2',1),
 ('RAMROOT:MOUNT NODES=43 BYTES=','RAMROOT:MOUNT NODES=45 BYTES=',1),
 ("prefix='root43-packet-'","prefix='root45-entropy-'",1),
):
    if source.count(old)!=count:raise ValueError('Exact entropy loader boundary changed: '+old)
    source=source.replace(old,new)
_module=types.ModuleType('tools.rpi5._root45_entropy_loader')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
exec(compile(source,_module.__file__,'exec'),_module.__dict__)
_original_inputs,_original_build=_module.inputs,_module.build


def inputs():
    inherited_pins,_,_,_=prior.inputs()
    pins,old,root,kernel=_original_inputs();_module.merge(pins,inherited_pins)
    for name,digest in FROZEN.items():_module.merge(pins,{str(ROOT/'tools/rpi5'/name):digest})
    test=ROOT/'tools/rpi5/tests/test_root45_entropy_root.py'
    _module.merge(pins,{str(test):_module.sha(test)})
    if (root['root_nodes'],root['root_files'])!=(45,33):raise ValueError('Exact new diagnostic root required')
    _module.base.verify(pins);return pins,old,root,kernel


def root_ready_contract():
    size=(_module.ROOT_DIR/'ramdisk.bin').stat().st_size
    return dict(root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=45 BYTES={size} READONLY',
        root_ready_max_reports=3,root_ready_requires_mounted_readonly=True,root_ready_requires_successful_reload=True)


_module.inputs=inputs
for _name,_value in vars(_module).items():
    if not _name.startswith('_'):globals()[_name]=_value


def build():
    package,record=_original_build();record.update(root_ready_contract())
    (package/'manifest.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    return package,record


if __name__=='__main__':
    p,r=build();print(json.dumps({k:r[k] for k in ('image','image_sha256','image_bytes','trial_marker','geometry')},indent=2))
