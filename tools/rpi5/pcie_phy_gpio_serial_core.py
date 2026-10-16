# SPDX-License-Identifier: BSD-2-Clause
"""53-row raw GPIO32 observer, never reset/PHY/network admission."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_gem_capabilities_serial_core as prior
from tools.rpi5 import build_pcie_phy_gpio_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('GPIO','GPIO_PROGRESS','GPIO0_CTRL','GPIO0_RIO','GPIO1_CTRL','GPIO1_RIO')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)
def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original GPIO capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:
        raise ValueError('Fault anywhere in complete original GPIO capture')
    for name,factory in (('gpio_contract','gpio_contract'),('capabilities_contract','capabilities_contract'),
        ('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),
        ('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract'),
        ('rp1_device_handoff','gpio_handoff_contract')):
        if not same(report.get(name),getattr(package_source,factory)()):raise ValueError('Exact GPIO report required: '+name)
    marker=report.get('marker','');device=package_source.DEVICE_MARKER
    if not marker.startswith('RPI5XNU:BL33:PCIE_PHY_GPIO_TRIAL TAG=') or data.count(marker.encode())!=1 or data.count(device.encode())!=1:
        raise ValueError('Unique exact GPIO image and nine-page Device marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=53 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly53 ordered GPIO diagnostic records required')
    row=lambda name:lines[ORDER.index(name)]
    m=re.fullmatch(PREFIX+rb'GPIO STATE=(\d+) RC=(-?\d+) READS=(\d+) MAPPED=([0-9a-f]+) UNMAPPED=([0-9a-f]+) INDEX=(\d+)',row('GPIO'))
    if not m:raise ValueError('Exact GPIO state row required')
    values=[int(v,16 if i in (3,4) else 10) for i,v in enumerate(m.groups())]
    progress=dict(zip(('state','rc','reads','mapped','unmapped','index'),values))
    m=re.fullmatch(PREFIX+rb'GPIO_PROGRESS PASS=(\d+) WORD=(\d+) PENDING=(\d+)',row('GPIO_PROGRESS'))
    if not m:raise ValueError('Exact GPIO progress row required')
    detail=dict(zip(('pass','word','pending'),map(int,m.groups())))
    if (progress['state']>3 or not -4<=progress['rc']<=0 or progress['reads']>12 or progress['mapped']>7 or
        progress['unmapped']>7 or progress['unmapped']&~progress['mapped'] or progress['index']>2 or
        detail['pass']>1 or detail['word']>5 or detail['pending']>3):raise ValueError('GPIO bounds exceeded')
    snapshots=[]
    for i in range(2):
        words=[]
        for suffix,labels in (('CTRL',('STATUS','CTRL','PAD')),('RIO',('OUT','OE','IN'))):
            name='GPIO'+str(i)+'_'+suffix
            m=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(k.encode()+rb'=([0-9a-f]{8})' for k in labels),row(name))
            if not m:raise ValueError('Exact raw GPIO words required')
            words.extend(int(v,16) for v in m.groups())
        snapshots.append(dict(zip(('status','ctrl','pad','out','oe','in'),words)))
    normalized=data
    for name in ADDITIONS:
        line=row(name);wire=line+b'\r\n' if line+b'\r\n' in normalized else line+b'\n';normalized=normalized.replace(wire,b'',1)
    normalized=normalized.replace(b'PCIE_PHY_GPIO_TRIAL',b'PCIE_GEM_CAPABILITIES_TRIAL')
    normalized=normalized.replace(device.encode(),prior.package_source.DEVICE_MARKER.encode())
    adapted=copy.deepcopy(report);adapted['marker']=marker.replace('PCIE_PHY_GPIO_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL')
    adapted['boot_markers']=[s.replace('PCIE_PHY_GPIO_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL').replace(device,prior.package_source.DEVICE_MARKER) for s in report['boot_markers']]
    for name,factory in (('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),
        ('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        adapted[name]=getattr(prior.package_source,factory)()
    result=prior.inspect(normalized,adapted);passed=result['capabilities_trial_pass']
    if passed and (tuple(progress.values())!=(2,0,12,7,7,0) or tuple(detail.values())!=(1,5,0)):
        raise ValueError('Success requires complete GPIO snapshot and reverse revocation')
    result.update(gpio_observer_trial_pass=passed,gpio_progress=progress,gpio_detail=detail,gpio_snapshots=snapshots,
        gpio_snapshots_committed=passed,gpio_mappings_revoked=passed,gpio_register_writes=False,phy_reset_performed=False,
        gpio_electrical_state_proven=False,phy_ready_proven=False,ethernet_proven=False,observed_field_rows=53,
        endpoint_register_reads_attempted=result['endpoint_register_reads_attempted']+progress['reads'],
        endpoint_register_reads_completed=60 if passed else None,full_original_capture_health_scan=True,
        scope='Raw inherited GPIO32 observations with fresh FDT and exact restoration; no GPIO/reset/PHY-readiness authority')
    return result
