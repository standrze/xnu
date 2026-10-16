# SPDX-License-Identifier: BSD-2-Clause
"""53-row zero-input C22 read trial; successful restoration is not networking."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_gem_capabilities_serial_core as prior
from tools.rpi5 import build_pcie_gem_mdio_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('MDIO','MDIO_IO','MDIO_NCR','MDIO_CFG','MDIO_PHY','MDIO_TIME')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original MDIO capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:
        raise ValueError('Fault in complete original MDIO capture including return tail')
    for name,factory in (('mdio_contract','mdio_contract'),('capabilities_contract','capabilities_contract'),
        ('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),
        ('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        if not same(report.get(name),getattr(package_source,factory)()):raise ValueError('Exact MDIO report required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_GEM_MDIO_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique MDIO marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=53 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly53 ordered diagnostic records required')
    row=lambda name:lines[ORDER.index(name)]
    def parse(name,labels,pattern,base=10):
        parsed=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(k.encode()+b'='+pattern for k in labels.split()),row(name))
        if not parsed:raise ValueError('Exact MDIO row required: '+name)
        return dict(zip(labels.lower().split(),(int(v,base) for v in parsed.groups())))
    progress=parse('MDIO','STATE STAGE RC PHY TRANSFERS',rb'(-?\d+)')
    io=parse('MDIO_IO','READS WRITES POLLS CLOCKS CLK_CHANGED',rb'(\d+)')
    ncr=parse('MDIO_NCR','BEFORE LIVE AFTER',rb'([0-9a-f]{8})',16)
    cfg=parse('MDIO_CFG','BEFORE LIVE AFTER',rb'([0-9a-f]{8})',16)
    phy=parse('MDIO_PHY','ID1 ID2 BMCR BMSR_FIRST BMSR_NOW',rb'([0-9a-f]{4})',16)
    timing=parse('MDIO_TIME','START_US LAST_US DEADLINE_US',rb'(\d+)')
    if (not 0<=progress['state']<=3 or not 0<=progress['stage']<=7 or not -6<=progress['rc']<=0 or
        not 0<=progress['phy']<=31 or not 0<=progress['transfers']<=5 or io['reads']>46 or io['writes']>9 or
        io['polls']>32 or io['clocks']>57 or io['clk_changed']>1 or any(v>2**64-1 for v in timing.values())):
        raise ValueError('MDIO diagnostic bounds exceeded')
    normalized=data
    for name in ADDITIONS:
        value=row(name);wire=value+b'\r\n' if value+b'\r\n' in normalized else value+b'\n'
        normalized=normalized.replace(wire,b'',1)
    normalized=normalized.replace(b'PCIE_GEM_MDIO_TRIAL',b'PCIE_GEM_CAPABILITIES_TRIAL')
    adapted=copy.deepcopy(report);adapted['marker']=marker.replace('PCIE_GEM_MDIO_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL')
    adapted['boot_markers']=[s.replace('PCIE_GEM_MDIO_TRIAL','PCIE_GEM_CAPABILITIES_TRIAL') for s in report['boot_markers']]
    for name,factory in (('root_forward_contract','root_forward_contract'),('gem_contract','gem_contract'),
        ('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        adapted[name]=getattr(prior.package_source,factory)()
    result=prior.inspect(normalized,adapted);passed=result['capabilities_trial_pass'];decoded=None
    if passed:
        if tuple(progress.values())!=(2,7,0,1,5):raise ValueError('Complete same-boot MDIO session required')
        changed=int(((cfg['before']>>18)&7)<5)
        wanted=(cfg['before']&~0x1c0000)|0x140000 if changed else cfg['before']
        if (cfg['before']==0xffffffff or cfg['live']!=wanted or cfg['after']!=cfg['before'] or
            io['clk_changed']!=changed or ncr['before']&~0x11180000 or ncr['live']!=ncr['before']|0x10 or ncr['after']!=ncr['before']):
            raise ValueError('Exact temporary management configuration and restoration required')
        if (not 12<=io['polls']<=32 or io['reads']!=io['polls']+13+changed or io['writes']!=7+2*changed or
            io['clocks']!=io['reads']+io['writes']+2 or result['gem_mid'][:2]!=[0x70109,0x70109]):
            raise ValueError('Exact bounded management operations and GEM identity required')
        if (timing['deadline_us']!=timing['start_us']+20000 or
            not timing['start_us']<timing['last_us']<timing['deadline_us']):raise ValueError('Unextended management deadline required')
        identity=(phy['id1']<<16)|phy['id2']
        if not identity or identity&0x1fffffff==0x1fffffff or any(phy[n]==0xffff for n in ('bmcr','bmsr_first','bmsr_now')):
            raise ValueError('Non-floating PHY responses required')
        decoded=dict(phy_id=identity,bmcr=phy['bmcr'],bmsr_latched=phy['bmsr_first'],bmsr_current=phy['bmsr_now'],
            link=(phy['bmsr_now']>>2)&1,autoneg_complete=(phy['bmsr_now']>>5)&1)
    result.update(mdio_trial_pass=passed,mdio_progress=progress,mdio_io=io,mdio_ncr=ncr,mdio_ncfgr=cfg,
        mdio_raw_phy=phy,mdio_timing=timing,phy_observation=decoded,management_config_restored=passed,
        observed_field_rows=53,endpoint_register_reads_attempted=result['endpoint_register_reads_attempted']+io['reads'],
        endpoint_register_reads_completed=48+io['reads'] if passed else None,
        endpoint_register_writes_attempted=io['writes'],endpoint_register_writes=bool(io['writes']),phy_register_writes=False,
        ethernet_proven=False,full_original_capture_health_scan=True,
        scope='Bounded C22 ID/control/basic-status reads with exact config/maps/BAR/root restoration; no packet driver')
    return result
