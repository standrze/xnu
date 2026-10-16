#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact diagnostic root/tag and unchanged real kernel/FDT admission."""
import argparse
import json
from pathlib import Path
import types
from tools.rpi5 import build_root45_entropy_package as builder
from tools.rpi5 import check_root43_packet_package as prior

source=prior.source
for old,new,count in (
 ('build_root43_packet_package as builder','build_root45_entropy_package as builder',2),
 ("package.name.startswith('root43-packet-')","package.name.startswith('root45-entropy-')",1),
 ('Distinct root43-packet package required','Distinct root45-entropy package required',1),
 ('root_nodes=43,root_files=31','root_nodes=45,root_files=33',1),
):
    if source.count(old)!=count:raise ValueError('Exact entropy checker boundary changed')
    source=source.replace(old,new)
_module=types.ModuleType('tools.rpi5._root45_entropy_loader_check')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
exec(compile(source,_module.__file__,'exec'),_module.__dict__)


def inspect_record(package,record):
    contract=builder.root_ready_contract()
    if any(record.get(k)!=v or type(record.get(k)) is not type(v) for k,v in contract.items()):
        raise ValueError('Exact entropy mounted-root readiness contract required')
    result=_module.inspect_record(package,record);result.update(contract)
    return result


def inspect(package):
    package=package.resolve();return inspect_record(package,json.loads((package/'manifest.json').read_text()))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path)
    print(json.dumps(inspect(p.parse_args().package),indent=2,sort_keys=True))
