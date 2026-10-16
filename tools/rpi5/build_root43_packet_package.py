#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""New packet root/tag; unchanged state-confirmed kernel and retained FDT."""
import json
from pathlib import Path
import sys
import types
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.rpi5 import build_root42_ready_package as ready

FROZEN={
 'build_root42_ready_package.py':'60735d90b8ba2f7ee2cbbddcf9af1c0253cb39cc8c8d0521e8a4be183beed9de',
 'check_root42_ready_package.py':'769037e7e6f66b9a126d4d5bb6b0a353bab2a023ae71b883d7f5ae3654d385ef',
}
for name,digest in FROZEN.items():
    if ready.sha(ROOT/'tools/rpi5'/name)!=digest:raise ValueError('Frozen late-root source changed')
source=ready.source
for old,new,count in (
 ('check_root42_pthread_root as root_check','check_root43_packet_root as root_check',2),
 ("PROFILE='root42-mounted-ready-retained-fdt-v1'","PROFILE='root43-packet-mounted-ready-retained-fdt-v1'",1),
 ('check_root42_ready_package.py','check_root43_packet_package.py',1),
 ('tests/test_root42_ready_package.py','tests/test_root43_packet_package.py',1),
 ('ROOT42_READY_TRIAL TAG=','ROOT43_PACKET_TRIAL TAG=',1),
 ('CPUS=4 ROOT_NODES=42 WATCHDOG_READY_V2','CPUS=4 ROOT_NODES=43 WATCHDOG_READY_V2',1),
 ('RAMROOT:MOUNT NODES=42 BYTES=','RAMROOT:MOUNT NODES=43 BYTES=',1),
 ("prefix='root42-ready-'","prefix='root43-packet-'",1),
):
    if source.count(old)!=count:raise ValueError('Exact packet loader boundary changed: '+old)
    source=source.replace(old,new)
_module=types.ModuleType('tools.rpi5._root43_packet_loader')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
exec(compile(source,_module.__file__,'exec'),_module.__dict__)
_original_inputs,_original_build=_module.inputs,_module.build


def inputs():
    # Reuse the reviewed readiness/kernel semantic admission unchanged. Its
    # old root is retained as ancestry, not selected for the new payload.
    preceding_pins,_,_,_=ready.inputs()
    pins,old,root,kernel=_original_inputs()
    _module.merge(pins,preceding_pins)
    for name,digest in FROZEN.items():_module.merge(pins,{str(ROOT/'tools/rpi5'/name):digest})
    for name in ('tests/test_root43_packet_root.py',):
        path=ROOT/'tools/rpi5'/name;_module.merge(pins,{str(path):_module.sha(path)})
    if (root['root_nodes'],root['root_files'])!=(43,31):raise ValueError('Exact new packet root required')
    _module.base.verify(pins)
    return pins,old,root,kernel


def root_ready_contract():
    extent=(_module.ROOT_DIR/'ramdisk.bin').stat().st_size
    return dict(root_ready_marker=f'RPI5XNU:TERMINAL:ROOT_READY SECONDS=180 NODES=43 BYTES={extent} READONLY',
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
