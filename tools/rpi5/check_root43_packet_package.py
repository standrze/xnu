#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact packet root, new tag, and unchanged real kernel/FDT admission."""
import argparse
import json
from pathlib import Path
import types
try:
    from . import build_root43_packet_package as builder
    from . import check_root42_ready_package as ready
except ImportError:
    import build_root43_packet_package as builder
    import check_root42_ready_package as ready

source=ready.source
for old,new,count in (
 ('build_root42_ready_package as builder','build_root43_packet_package as builder',2),
 ("package.name.startswith('root42-ready-')","package.name.startswith('root43-packet-')",1),
 ('Distinct root42-ready package required','Distinct root43-packet package required',1),
 ('root_nodes=42,root_files=30','root_nodes=43,root_files=31',1),
):
    if source.count(old)!=count:raise ValueError('Exact packet checker boundary changed')
    source=source.replace(old,new)
_module=types.ModuleType('tools.rpi5._root43_packet_loader_check')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
exec(compile(source,_module.__file__,'exec'),_module.__dict__)


def inspect_record(package,record):
    contract=builder.root_ready_contract()
    if any(record.get(k)!=v or type(record.get(k)) is not type(v) for k,v in contract.items()):
        raise ValueError('Exact packet mounted-root readiness contract required')
    result=_module.inspect_record(package,record);result.update(contract)
    return result


def inspect(package):
    package=package.resolve();return inspect_record(package,json.loads((package/'manifest.json').read_text()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
