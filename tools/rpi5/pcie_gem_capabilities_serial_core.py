# SPDX-License-Identifier: BSD-2-Clause
"""47-row zero-input capability observation, not an Ethernet packet driver."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_gem_selected_serial_core as prior
from tools.rpi5 import build_pcie_gem_capabilities_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('CAPS','CAP_BEFORE0','CAP_BEFORE1','CAP_AFTER0','CAP_AFTER1')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def decode(raw):
    if len(raw)!=8 or any(type(v) is not int or not 0<=v<=0xffffffff for v in raw):raise ValueError('Eight uint32 design words required')
    identity=(raw[0]>>16)&0xfff
    if raw[0] in (0,0xffffffff) or not 2<=identity<0xfff:raise ValueError('Valid GEM identity required')
    code=(raw[1]>>25)&7;mask=(raw[4]&255)|1
    return dict(id=identity,revision=raw[0]&0xffff,bus_width_code=code,bus_width_bits={1:32,2:64,4:128}.get(code,0),
        queue_mask=mask,queue_count=mask.bit_count(),dma64=(raw[4]>>23)&1,isr_clear_on_read=(raw[1]>>23)&1,
        pcs=int(not raw[1]&1),rx_packet_buffer=(raw[2]>>20)&1,tx_packet_buffer=(raw[2]>>21)&1,
        rx_packet_address_bits=(raw[2]>>22)&15,tsu=(raw[3]>>8)&1,lso=(raw[4]>>27)&1,
        cutthrough=(raw[4]>>25)&1,high_speed=(raw[7]>>26)&1,type1_screeners=raw[5]>>24,
        type2_screeners=(raw[5]>>16)&255,type2_ethertypes=(raw[5]>>8)&255,type2_comparators=raw[5]&255,
        rx_descriptor_prefetch_code=(raw[6]>>8)&15,tx_descriptor_prefetch_code=(raw[6]>>12)&15)


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original capability capture required')
    if (health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed'] or
        b'RPI5XNU:FAULT' in data):
        raise ValueError('Fault in complete original capability capture including return tail')
    for name,factory in (('capabilities_contract','capabilities_contract'),('root_forward_contract','root_forward_contract'),
        ('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        if not same(report.get(name),getattr(package_source,factory)()):raise ValueError('Exact capability report required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_GEM_CAPABILITIES_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique capability marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=47 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly47 ordered diagnostic records required')
    row=lambda name:lines[ORDER.index(name)]
    match=re.fullmatch(PREFIX+rb'CAPS STATE=(\d+) RC=(-?\d+) READS=(\d+) PASS=(\d+) INDEX=(\d+) PENDING=(\d+)',row('CAPS'))
    if not match:raise ValueError('Exact capability progress row required')
    progress=dict(zip(('state','rc','reads','pass','index','pending'),map(int,match.groups())))
    if (progress['state']>3 or not -5<=progress['rc']<=0 or progress['reads']>16 or progress['pass']>1 or
        progress['index']>7 or progress['pending']>1):raise ValueError('Capability progress exceeds C bounds')
    snapshots=[]
    for side in ('BEFORE','AFTER'):
        words=[]
        for half,labels in enumerate(('MID DCFG1 DCFG2 DCFG5','DCFG6 DCFG8 DCFG10 DCFG12')):
            name='CAP_'+side+str(half)
            parsed=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(k.encode()+rb'=([0-9a-f]{8})' for k in labels.split()),row(name))
            if not parsed:raise ValueError('Exact capability snapshot row required')
            words.extend(int(v,16) for v in parsed.groups())
        snapshots.append(words)
    normalized=data
    for name in ADDITIONS:
        value=row(name);wire=value+b'\r\n' if value+b'\r\n' in normalized else value+b'\n'
        normalized=normalized.replace(wire,b'',1)
    normalized=normalized.replace(b'PCIE_GEM_CAPABILITIES_TRIAL',b'PCIE_GEM_SELECTED_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_GEM_SELECTED_TRIAL')
    adapted['boot_markers']=[s.replace('PCIE_GEM_CAPABILITIES_TRIAL','PCIE_GEM_SELECTED_TRIAL') for s in report['boot_markers']]
    for name,factory in (('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),
        ('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        adapted[name]=getattr(prior.package_source,factory)()
    result=prior.inspect(normalized,adapted);passed=result['selected_clock_trial_pass'];decoded=None
    if passed:
        if tuple(progress.values())!=(2,0,16,1,7,0):raise ValueError('Successful result requires complete capability session')
        if snapshots[0]!=snapshots[1] or snapshots[0][0]!=result['gem_mid'][0]:raise ValueError('Same-boot repeated design words and identity required')
        decoded=decode(snapshots[0])
    result.update(capabilities_trial_pass=passed,capabilities_progress=progress,capabilities_snapshots=snapshots,
        capabilities=decoded,capabilities_committed=passed,observed_field_rows=47,
        endpoint_register_reads_attempted=result['endpoint_register_reads_attempted']+progress['reads'],
        endpoint_register_reads_completed=48 if passed else None,
        dma_addressability_qualified=False,ethernet_proven=False,full_original_capture_health_scan=True,
        scope='Repeated immutable GEM design words inside exact held Device maps/root forwarding and original clock bracket; restoration required, no packet driver')
    return result
