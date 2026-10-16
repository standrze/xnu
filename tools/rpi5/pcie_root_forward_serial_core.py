# SPDX-License-Identifier: BSD-2-Clause
"""Full raw health plus exact root MEM/window and endpoint/GEM restoration."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_gem_identify_serial_core as prior
from tools.rpi5 import build_pcie_root_forward_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('ROOT_MEM','ROOT_MEM_COMMAND','ROOT_MEM_WINDOW','ROOT_MEM_CONFIG','ROOT_MEM_IO','ROOT_MEM_OUT0','ROOT_MEM_OUT1')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def fields(row,name,labels,decimal=()):
    expressions=[label.encode()+(rb'=(-?\d+)' if label in decimal else rb'=([0-9a-f]{'+(b'4' if name=='ROOT_MEM_COMMAND' else b'8')+rb'})') for label in labels]
    parsed=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(expressions),row)
    if not parsed:raise ValueError('Exact root-forward field record required: '+name)
    return dict(zip((x.lower() for x in labels),(int(v,10 if k in decimal else 16) for k,v in zip(labels,parsed.groups()))))


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original root-forward capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete original root-forward capture including after END')
    for name,expected in (('root_forward_contract',package_source.root_forward_contract()),('gem_contract',package_source.gem_contract()),
        ('decode_contract',package_source.decode_contract()),('owner_trace',package_source.owner_contract()),('trace_contract',package_source.trace_contract())):
        if not same(report.get(name),expected):raise ValueError('Exact root-forward report contract required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_ROOT_FORWARD_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique root-forward image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=42 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly42 ordered diagnostic records required')
    row=lambda name:lines[ORDER.index(name)]
    progress=fields(row('ROOT_MEM'),'ROOT_MEM',('CALL','RC','STAGE','READS','WRITES','PENDING'),('CALL','RC','STAGE','READS','WRITES','PENDING'))
    command=fields(row('ROOT_MEM_COMMAND'),'ROOT_MEM_COMMAND',('BEFORE','LIVE','AFTER'))
    window=fields(row('ROOT_MEM_WINDOW'),'ROOT_MEM_WINDOW',('BEFORE','WANTED','LIVE','AFTER'))
    config=fields(row('ROOT_MEM_CONFIG'),'ROOT_MEM_CONFIG',('ID','HDR','BUS'))
    access=fields(row('ROOT_MEM_IO'),'ROOT_MEM_IO',('OFFSET','WIDTH','WRITE','VALUE'),('WIDTH','WRITE'))
    outbound=[fields(row('ROOT_MEM_OUT'+str(i)),'ROOT_MEM_OUT'+str(i),('LO','HI','BASELIMIT','BASEHI','LIMITHI')) for i in range(2)]
    if (not 0<=progress['call']<=2 or not -5<=progress['rc']<=0 or not 0<=progress['stage']<=8 or
        not 0<=progress['reads']<=79 or not 0<=progress['writes']<=4 or progress['pending'] not in (0,1) or
        access['width'] not in (0,2,4) or access['write'] not in (0,1)):
        raise ValueError('Root-forward progress exceeds bounded state machine')
    normalized=data
    for r in lines[-8:-1]:
        raw=r+b'\r\n' if r+b'\r\n' in normalized else r+b'\n';normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(b'PCIE_ROOT_FORWARD_TRIAL',b'PCIE_GEM_IDENTIFY_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_ROOT_FORWARD_TRIAL','PCIE_GEM_IDENTIFY_TRIAL')
    adapted['boot_markers']=[v.replace('PCIE_ROOT_FORWARD_TRIAL','PCIE_GEM_IDENTIFY_TRIAL') for v in report['boot_markers']]
    for name,factory in (('gem_contract','gem_contract'),('decode_contract','decode_contract'),('owner_trace','owner_contract'),('trace_contract','trace_contract')):
        adapted[name]=getattr(prior.package_source,factory)()
    result=prior.inspect(normalized,adapted);passed=result['gem_identify_trial_pass']
    if passed:
        if tuple(progress.values())!=(2,0,7,79,4,0):raise ValueError('Success contradicts complete root-forward cycle')
        if command['before']&7 or command['live']!=command['before']|2 or command['after']!=command['before']:
            raise ValueError('Exact MEM-only root COMMAND restoration required')
        if config['id']!=0x271214e4 or config['hdr']&0xff0000!=0x10000 or config['bus']&0xffffff!=0x10100:
            raise ValueError('Exact same root identity/header/route required')
        bars=[b for b in result['bars'] if b['size']]
        low=min(b['plan'] for b in bars)&~0xfffff;high=(max(b['plan']+b['size'] for b in bars)-1)|0xfffff
        expected=((low>>16)&0xfff0)|(high&0xfff00000)
        if window['before']&0x000f000f or window['wanted']!=expected or window['live']!=expected or window['after']!=window['before']:
            raise ValueError('Minimal all-BAR 1MiB window and exact original restoration required')
        contract=report['root_forward_contract']
        for actual,values in zip(outbound,contract['outbound_required_values']):
            if [v&m for v,m in zip(actual.values(),contract['outbound_required_mask'])]!=values:
                raise ValueError('Exact outbound translation profile required')
        if access!=dict(offset=0x408c,width=4,write=0,value=outbound[1]['limithi']):
            raise ValueError('Final complete outbound readback required')
    result.update(root_forward_trial_pass=passed,root_forward_progress=progress,root_command=command,root_window=window,
        root_config=config,root_access=access,root_outbound=outbound,root_forward_contract=report['root_forward_contract'],
        root_memory_forwarding_attempted=bool(progress['writes']),root_memory_forwarding_restored=passed,
        root_memory_forwarding_enabled=False if passed else None,root_config_writes_attempted=progress['writes'],
        root_config_reads_attempted=progress['reads'],observed_field_rows=42,full_original_capture_health_scan=True,
        ethernet_proven=False,scope='Temporary root MEM/window plus unchanged repeated clock/MID reads and exact root/endpoint/maps/BAR restoration; no BME, DMA, IRQ, clock/reset/PHY writes or packet driver')
    return result
