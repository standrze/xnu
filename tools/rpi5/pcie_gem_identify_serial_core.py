# SPDX-License-Identifier: BSD-2-Clause
"""Complete raw clock/MID diagnostic, with no packet/driver claim."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_decode_cycle_serial_core as prior
from tools.rpi5 import build_pcie_gem_identify_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('GEM','CLOCK_BEFORE0','CLOCK_BEFORE1','CLOCK_BEFORE2','CLOCK_BEFORE3',
    'CLOCK_AFTER0','CLOCK_AFTER1','CLOCK_AFTER2','CLOCK_AFTER3','GEM_MID')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def clock_profile(v):
    if len(v)!=15 or (v[3]&~0x8000003f) or (v[4]&~0x3f):return False
    if not v[0]&0x800 or v[0]&3!=2 or v[2]!=4 or not 0<v[1]<=0xffffff:return False
    if not v[3]&0x80000000 or v[3]&63!=1 or v[4]&0x29 or not v[4]&4 or v[5] not in (20,40) or v[6]:return False
    a,b=(v[7]>>16)&7,(v[7]>>12)&7
    if not a or not b or 50000000*v[5]!=200000000*a*b*v[1]:return False
    for n in (8,11):
        if not v[n]&0x800 or v[n]&0x3e0 or not 0<v[n+1]<=255 or not v[n+2] or v[n+2]&(v[n+2]-1):return False
    sec=(v[14]>>8)&31
    return not v[14]&0x10000 and 8<=sec<=18 and v[12]==1 and 50000000*v[5]==125000000*sec*v[9]


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original GEM capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete original GEM capture including after END')
    for name,expected in (('gem_contract',package_source.gem_contract()),('decode_contract',package_source.decode_contract()),
        ('owner_trace',package_source.owner_contract()),('trace_contract',package_source.trace_contract())):
        if not same(report.get(name),expected):raise ValueError('Exact GEM report contract required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_GEM_IDENTIFY_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique GEM image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=35 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly35 ordered diagnostic records required')
    match=re.fullmatch(PREFIX+rb'GEM CALL=(\d+) RC=(-?\d+) STAGE=(\d+) READS=(\d+) READY=(\d+) INDEX=(\d+) OFFSET=([0-9a-f]{8})',lines[-11])
    if not match:raise ValueError('Exact GEM progress record required')
    progress=dict(zip(('call','rc','stage','reads','ready','index','offset'),
        [int(v,16 if i==6 else 10) for i,v in enumerate(match.groups())]))
    if (progress['call']>2 or not -5<=progress['rc']<=0 or progress['stage']>6 or progress['reads']>32 or
        progress['ready']>1 or progress['index']>1):raise ValueError('GEM progress exceeds bounded C session')
    snapshots=[]
    for side in ('BEFORE','AFTER'):
        words=[]
        for group,labels in enumerate(('CTRL DIV SEL CS','PWR INT FRAC PRIM','ETH_CTRL ETH_DIV ETH_SEL TSU_CTRL','TSU_DIV TSU_SEL SEC')):
            row=lines[ORDER.index('CLOCK_'+side+str(group))]
            regex=PREFIX+('CLOCK_'+side+str(group)+' ').encode()+b' '.join(n.encode()+rb'=([0-9a-f]{8})' for n in labels.split())
            parsed=re.fullmatch(regex,row)
            if not parsed:raise ValueError('Exact clock snapshot record required')
            words.extend(int(v,16) for v in parsed.groups())
        snapshots.append(words)
    mid=re.fullmatch(PREFIX+rb'GEM_MID FIRST=([0-9a-f]{8}) SECOND=([0-9a-f]{8}) COMMITTED=([0-9a-f]{8}) HZ=(\d+)',lines[-2])
    if not mid:raise ValueError('Exact GEM MID record required')
    mids=[int(v,16 if i<3 else 10) for i,v in enumerate(mid.groups())]
    if mids[3]>0xffffffff:raise ValueError('GEM frequency exceeds C field width')
    normalized=data
    for row in lines[-11:-1]:
        raw=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(b'PCIE_GEM_IDENTIFY_TRIAL',b'PCIE_DECODE_CYCLE_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_GEM_IDENTIFY_TRIAL','PCIE_DECODE_CYCLE_TRIAL')
    adapted['boot_markers']=[v.replace('PCIE_GEM_IDENTIFY_TRIAL','PCIE_DECODE_CYCLE_TRIAL') for v in report['boot_markers']]
    for name, factory in (('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        adapted[name]=getattr(prior.package_source,factory)()
    result=prior.inspect(normalized,adapted);passed=result['decode_cycle_trial_pass']
    if passed:
        if tuple(progress.values())!=(2,0,5,32,1,1,0x8014):raise ValueError('GEM success contradicts complete bounded session')
        if snapshots[0]!=snapshots[1] or not clock_profile(snapshots[0]):raise ValueError('Stable known clock profile required')
        if (len(set(mids[:3]))!=1 or mids[0] in (0,0xffffffff) or not 2<=((mids[0]>>16)&0xfff)<0xfff or mids[3]!=200000000):
            raise ValueError('Repeated valid GEM MID and exact committed SYS rate required')
    elif mids[2] or mids[3]:raise ValueError('Failed caller cannot commit GEM observations')
    result.update(gem_identify_trial_pass=passed,gem_progress=progress,clock_snapshots=snapshots,gem_mid=mids,
        gem_identification_proven=passed,endpoint_register_access=passed,endpoint_register_writes=0,
        endpoint_register_reads_attempted=progress['reads'],endpoint_register_reads_completed=32 if passed else None,
        clock_reset_writes=False,observed_field_rows=35,
        full_original_capture_health_scan=True,gem_contract=report['gem_contract'],ethernet_proven=False,
        scope='Same-boot stable known clock registers and GEM MID only; exact map/COMMAND/BAR restore required; no packet driver, clock/reset/NCR/PHY writes, BME, DMA or IRQ')
    return result
