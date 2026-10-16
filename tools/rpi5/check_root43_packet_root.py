#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent exact namespace/catalog admission for the 43-node packet root."""
import argparse
import json
from pathlib import Path
import types
try:
    from . import root_capacity_packet as builder
except ImportError:
    import root_capacity_packet as builder

source=builder.derived('check_root42_pthread_root.py',(
 ('root_capacity_pthread as builder','root_capacity_packet as builder',2),
 ('root96-pthread-batch-go4g0fe7','root96-packet-batch-g9h6ugu5',1),
 ('69d562664e6477570edca65e973daed65f48b50393a446a1287d7d651ba641a0','e905e6a2519db490f131228b2149d737d014db2f8030b0903009567142b0c5fb',1),
 ('9ddbbd5701ca890e97f3f5aefd4c3c0c47434fb50a34bbce51d11e77141b94fd','2107c3b876f44d8c0b873e8d4e781bc594d3f7fdcc4aec0cdc28651884689d5d',1),
 ("m.get('profile')!='rpi5-root96-genuine-pthread-batch-v1'","m.get('profile')!='rpi5-root96-genuine-packet-batch-v1'",1),
 ("m.get('output_nodes')!=42 or m.get('output_files')!=30 or len(layout['entries'])!=42 or len(expected)!=30",
  "m.get('output_nodes')!=43 or m.get('output_files')!=31 or len(layout['entries'])!=43 or len(expected)!=31",1),
 ('root_nodes=42,root_files=30','root_nodes=43,root_files=31',1),
 ('Exact immutable 42-node root; not Pi pthread acceptance','Exact immutable 43-node root; not Pi packet acceptance',1),
 ('    args=next','    builder.extra_inputs(pins)\n    args=next',1),
))
source=source.replace('PTHREAD','PACKET').replace('pthread_manifest','packet_manifest').replace('pthread_executable_audit','packet_executable_audit')
_module=types.ModuleType('tools.rpi5._root43_packet_root_check')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
exec(compile(source,_module.__file__,'exec'),_module.__dict__)
for _name,_value in vars(_module).items():
    if not _name.startswith('_'):globals()[_name]=_value


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('package',type=Path)
    print(json.dumps(inspect(parser.parse_args().package),indent=2,sort_keys=True))
