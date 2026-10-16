#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact private 42→43 root derivation: genuine packet executable only."""
import hashlib
import json
from pathlib import Path
import sys
import types

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.rpi5 import check_root42_pthread_root as baseline

FROZEN={
 'root_capacity_pthread.py':'4bea5bee90227763c4703566ac0fadf4579296daec24b3822017be3ddad62d7a',
 'check_root42_pthread_root.py':'35b2088646c45998bdb0e9c552eb659a2a46190b8e7ab69ab42088dbc6f1ce1f',
}
PACKET_TESTS=('tests/test_ssh_packet_pthread_closure.py','tests/test_ssh_packet_pthread_contract.py',
 'tests/libressl_caps_contract.c','tests/libressl_pthread_abi_contract.c')


def derived(name,replacements):
    path=ROOT/'tools/rpi5'/name;source=path.read_text()
    if hashlib.sha256(source.encode()).hexdigest()!=FROZEN[name]:raise ValueError('Frozen root source changed')
    for old,new,count in replacements:
        if source.count(old)!=count:raise ValueError('Exact packet-root boundary changed: '+old)
        source=source.replace(old,new)
    return source


def extra_inputs(pins):
    for name,digest in FROZEN.items():
        _module.prior_check.merge(pins,{str(ROOT/'tools/rpi5'/name):digest})
    for name in PACKET_TESTS:
        path=ROOT/'tools/rpi5'/name
        _module.prior_check.merge(pins,{str(path):_module.sha(path)})


source=derived('root_capacity_pthread.py',(
 ('check_root96_command_package as prior_check','check_root42_pthread_root as prior_check',2),
 ('build/rpi5/apple-pthread-static-complete-gm82fjkz','build/rpi5/apple-ssh-packet-pthread-iabcb1gr',1),
 ('4a22b183000378e842d59c643ed1f8a80a520e1e77d62370880a7c095adfc35a','b1ca5bec6b327284fd8df985753ac5a10bcd324295ab981c946cc7ebb4d3cef3',1),
 ('bc882d7d3ca236d9f649292b9a64aebb6669a1b9f3ee0806c61d21c7f418ba15','7934dcd0b9882e1ad9a22834bc3f76af805283c8cdb264d26e885c0275879d1b',1),
 ("ENTRY='/usr/local/libexec/xnu/pthreadprobe'","ENTRY='/usr/local/libexec/xnu/sshpacketprobe'",1),
 ('len(original)!=29','len(original)!=30',1),
 ("prefix='root96-pthread-batch-'","prefix='root96-packet-batch-'",1),
 ('len(layout[\'entries\'])!=42 or len(expanded)!=30',"len(layout['entries'])!=43 or len(expanded)!=31",1),
 ("profile='rpi5-root96-genuine-pthread-batch-v1'","profile='rpi5-root96-genuine-packet-batch-v1'",1),
 ('output_nodes=42,output_files=30','output_nodes=43,output_files=31',1),
 ('nodes=42,files=30','nodes=43,files=31',1),
 ("'/usr/bin/hexdump /etc/motd','/usr/local/libexec/xnu/statprobe',ENTRY]",
  "'/usr/bin/hexdump /etc/motd','/usr/local/libexec/xnu/statprobe','/usr/local/libexec/xnu/pthreadprobe',ENTRY]",1),
 ('pthread_not_run=True','packet_not_run=True',1),
 ('exact_single_constructor_not_general_dyld_init=True','exact_two_constructors_not_general_dyld_init=True',1),
 ('    old.verify(pins)\n    output=', '    extra_inputs(pins)\n    old.verify(pins)\n    output=',1),
))
# Keep the prior implementation names internal; the public report names identify
# the packet executable and do not rewrite the original pthread artifact.
source=source.replace('PTHREAD','PACKET').replace('pthread_manifest','packet_manifest').replace('pthread_executable_audit','packet_executable_audit')
_module=types.ModuleType('tools.rpi5._root43_packet_root')
_module.__file__=str(Path(__file__).resolve());_module.__package__='tools.rpi5'
_module.extra_inputs=extra_inputs
exec(compile(source,_module.__file__,'exec'),_module.__dict__)
_module.prior_check=types.SimpleNamespace(**{**vars(baseline.prior_check),
    'inspect':baseline.inspect,'PACKAGE':baseline.PACKAGE,'MANIFEST_SHA':baseline.MANIFEST_SHA,
    'IMAGE_SHA':baseline.IMAGE_SHA,'__file__':baseline.__file__})
for _name,_value in vars(_module).items():
    if not _name.startswith('_'):globals()[_name]=_value


if __name__=='__main__':build()
