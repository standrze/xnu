# SPDX-License-Identifier: BSD-2-Clause
"""Complete nineteen-row owner diagnostic capture, retaining post-END health."""
import copy
import hashlib
import json
import re
from tools.rpi5 import rp1_bars_root_serial_core as prior
from tools.rpi5 import build_pcie_owner_trace_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions=prior.inventory,prior.return_positions
ORDER=prior.ORDER[:-1]+('FW','RPC','PM','TIME','IRQ','END')


def same(a,b):return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def fields(line,label,fmt):
    words=line.decode('ascii').split(' ');shapes=fmt.split(' ')
    if words[0]!='RPI5XNU:PCIEID:'+label or len(words)!=len(shapes)+1:raise ValueError('Wrong owner row shape')
    result={}
    for actual,shape in zip(words[1:],shapes):
        key,kind=shape.split('=');pattern='[0-9a-f]{16}' if kind=='%016llx' else '[0-9a-f]{8}' if kind=='%08x' else '-?[0-9]+' if kind=='%d' else '[0-9]+'
        found=re.fullmatch(re.escape(key)+'=('+pattern+')',actual)
        if not found:raise ValueError('Wrong owner field order/width')
        value=int(found[1],16 if kind.endswith('x') else 10)
        if not ((-2**31<=value<2**31) if kind=='%d' else 0<=value<2**(64 if kind in ('%llu','%016llx') else 32)):
            raise ValueError('Owner scalar width exceeded')
        result[key.lower()]=value
    return result


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded full capture required')
    if not same(report.get('trace_contract'),package_source.trace_contract()) or not same(report.get('owner_trace'),package_source.owner_contract()):
        raise ValueError('Exact passive owner contract required')
    if not any(v.startswith('RPI5XNU:BL33:PCIE_OWNER_TRACE_TRIAL TAG=') for v in report['boot_markers']):raise ValueError('Exact owner marker required')
    if prior.health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete runtime capture, including after END')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=19 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly nineteen ordered records required')
    owner={label.lower():fields(lines[13+i],label,fmt) for i,(label,fmt,_) in enumerate(package_source.kernel.profile.ROWS)}
    fw,rpc,pm,timing,irq=(owner[k] for k in ('fw','rpc','pm','time','irq'))
    if (fw['available']>1 or fw['stage']>8 or fw['state']>4 or fw['seq']>65536 or not -1<=fw['rc']<=0 or
        rpc['stage']>9 or rpc['calls']>65538 or rpc['fid'] not in (0,0xc2007f10,0xc2007f11,0xc2007f12) or
        pm['stage']>7 or pm['state']>4 or pm['checks']>65536 or pm['callbacks']>262156 or not -1<=pm['rc']<=0 or
        pm['first']>0xfffff or pm['count']>0xfffff or irq['stage']>9 or irq['state']>4 or irq['callbacks']>109 or not -1<=irq['rc']<=0):
        raise ValueError('Owner state outside actual finite bounds')
    if not fw['available'] and any(any(row.values()) for row in owner.values()):
        raise ValueError('Unavailable snapshot must retain zeroed output')
    normalized=data
    for row in lines[13:18]:
        raw=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(b'PCIE_OWNER_TRACE_TRIAL',b'RP1_BARS_ROOT_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['boot_markers']=[v.replace('PCIE_OWNER_TRACE_TRIAL','RP1_BARS_ROOT_TRIAL') for v in report['boot_markers']]
    adapted['trace_contract']=prior.package_source.trace_contract()
    result=prior.inspect(normalized,adapted)
    if result['bars_trial_pass']:
        if (fw['available']!=1 or (fw['stage'],fw['rc'],fw['state'])!=(8,0,3) or
            (rpc['stage'],rpc['fid'],rpc['x0'],rpc['x3'])!=(9,0xc2007f12,0,31) or
            (pm['stage'],pm['rc'],pm['state'])!=(7,0,3) or (irq['stage'],irq['rc'],irq['state'])!=(9,0,3) or
            rpc['calls']!=fw['seq']+1 or rpc['x1']!=fw['seq'] or rpc['x2']!=fw['last'] or
            not 1000000<=fw['freq']<=1000000000 or fw['last']>=fw['deadline'] or timing['last']>=timing['deadline']):
            raise ValueError('Success contradicts actual owner state')
    result.update(owner_telemetry=owner,observed_field_rows=19,owner_trace_memory_only=True,physical_failure_cause_proven=False)
    return result
