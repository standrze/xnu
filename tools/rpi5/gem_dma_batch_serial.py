# SPDX-License-Identifier: BSD-2-Clause
"""52-row CPU-owned ring trial; failed storage remains retained, never DMA proof."""
import copy
import hashlib
from pathlib import Path
import re
import types
from tools.rpi5 import pcie_gem_capabilities_serial_core as prior
from tools.rpi5 import gem_dma_batch_contract as contracts
from tools.rpi5 import gem_dma_batch_trial_profile as profile
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('DMA_OWNER','DMA_RECORD','DMA_ROUTE','DMA_STAGE','DMA_RINGS')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)

def private(module,label,changes=()):
    path=Path(module.__file__).resolve();text=path.read_text()
    for old,new in changes:
        if text.count(old)!=1:raise ValueError('Exact inherited parser anchor differs')
        text=text.replace(old,new)
    result=types.ModuleType(label);result.__file__=str(path);result.__package__='tools.rpi5'
    exec(compile(text,str(path),'exec'),result.__dict__)
    return result

def parser():
    # The real callback now propagates -7 through root/GEM/decode. Preserve the
    # original raw error; do not rewrite it to fit the frozen predecessor.
    cap=private(prior,'_batch_cap');selected=private(prior.prior,'_batch_selected')
    admission="not (-5<=progress['rc']<=0 or progress['rc']==-7)"
    root=private(selected.prior,'_batch_root',[("not -5<=progress['rc']<=0",admission)])
    gem=private(root.prior,'_batch_gem',[("not -5<=progress['rc']<=0",admission)])
    decode=private(gem.prior,'_batch_decode',[("not -5<=progress['rc']<=0",admission)])
    gem.prior=decode;gem.clock_profile=selected.clock_profile;root.prior=gem
    root.package_source=selected.package_source;selected.configured_parser=lambda:root;cap.prior=selected
    return cap

def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original ring capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:
        raise ValueError('Fault in full original capture including post-END return')
    if not same(report.get('cpu_ring_contract'),contracts.contract()) or not same(report.get('inherited_capability_contracts'),contracts.inherited()):
        raise ValueError('Exact CPU-only and scoped inherited contracts required')
    tag=report.get('tag','');marker=report.get('marker','')
    if not re.fullmatch('[0-9a-f]{32}',tag) or marker!=profile.marker(tag) or data.count(marker.encode())!=1:
        raise ValueError('Exact unique CPU-ring image required')
    expected=[marker,contracts.HOST,contracts.DEVICE,contracts.FDT,report['root_copy_marker'],report['kernel_copy_marker']]
    if not same(report.get('boot_markers'),expected):raise ValueError('Exact actual loader marker order required')
    lines=[r.rstrip(b'\r') for r in data.split(b'\n') if r.startswith(PREFIX)]
    if len(lines)!=52 or tuple(r.split(b' ',1)[0][len(PREFIX):].decode('ascii') for r in lines)!=ORDER:
        raise ValueError('Exactly52 ordered records required')
    def fields(name,names):
        row=lines[ORDER.index(name)]
        match=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(n.encode()+rb'=(-?\d+)' for n in names.split()),row)
        if not match:raise ValueError('Exact CPU-ring fields required: '+name)
        return dict(zip(names.lower().split(),map(int,match.groups())))
    owner=fields('DMA_OWNER','PREPARE STATE ATTEMPTED ACTIVE REVOKED DISABLED RECORD')
    record=fields('DMA_RECORD','FIXED DYNAMIC MANAGED_START MANAGED_END')
    route=fields('DMA_ROUTE','PHYSICAL PCI RP1 BYTES')
    stage=fields('DMA_STAGE','STATE ERROR ATTEMPTED WRITTEN READ CALLS CHECKS')
    rings=fields('DMA_RINGS','RX TX GENERATION BYTES DESC SLOTS TAIL OWNED')
    for label,value in (("owner",owner),("record",record),("route",route),("stage",stage),("rings",rings)):
        for key,n in value.items():
            if not ((-6<=n<=0) if label=='stage' and key=='error' else 0<=n<2**64):raise ValueError('C field bounds exceeded')
    if (owner['prepare']>3 or owner['state']>10 or any(owner[k]>1 for k in ('attempted','active','revoked','disabled','record')) or
        record['fixed']>32 or record['dynamic']>8 or stage['state']>3 or stage['attempted']>640 or
        stage['written']>stage['attempted'] or stage['read']>640 or stage['calls']>81 or stage['checks']>164 or
        any(stage[k]%16 for k in ('attempted','written','read'))):raise ValueError('Bounded CPU-owned state exceeded')
    normalized=data
    for name in ADDITIONS:
        row=lines[ORDER.index(name)];wire=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(wire,b'',1)
    oldmarker='RPI5XNU:BL33:PCIE_GEM_CAPABILITIES_TRIAL TAG='+tag
    normalized=normalized.replace(marker.encode(),oldmarker.encode())
    adapted=copy.deepcopy(report);adapted.update(contracts.inherited())
    adapted['marker']=oldmarker;adapted['boot_markers']=[v.replace(marker,oldmarker) for v in expected]
    result=parser().inspect(normalized,adapted);passed=result['capabilities_trial_pass']
    if passed:
        if owner!=dict(prepare=2,state=10,attempted=1,active=0,revoked=0,disabled=1,record=1):raise ValueError('Complete retained owner required')
        if not 1<=record['fixed']<=32 or not 1<=record['dynamic']<=8 or (record['managed_start'],record['managed_end'])!=(0x6000000,0x10000000):
            raise ValueError('Actual same-boot immutable managed record required')
        if (route['bytes']!=0x48000 or route['physical']%0x4000 or
            not 0x6000000<=route['physical']<route['physical']+route['bytes']<=0x10000000 or
            route['pci']!=route['physical']+0x1000000000 or route['rp1']!=route['pci']):
            raise ValueError('Exact candidate-only address composition required')
        if stage!=dict(state=2,error=0,attempted=640,written=640,read=640,calls=81,checks=164):raise ValueError('Complete fixed RAM operation counts required')
        if (not rings['generation'] or rings['rx']!=route['rp1'] or rings['tx']!=route['rp1']+0x4000 or
            tuple(rings[k] for k in ('bytes','desc','slots','tail','owned'))!=(1280,16,64,256,160)):
            raise ValueError('Complete CPU-owned ring geometry required')
        c=result['capabilities']
        if (c['bus_width_bits'],c['queue_mask'],c['dma64'],c['rx_descriptor_prefetch_code'],c['tx_descriptor_prefetch_code'])!=(128,1,1,4,4):
            raise ValueError('Actual admitted same-boot GEM profile required')
    elif any(rings.values()) and stage['state']!=2:
        raise ValueError('Incomplete RAM stage cannot publish ring geometry')
    propagated=[result['root_forward_progress']['rc'],result['gem_progress']['rc'],result['decode_telemetry']['rc']]
    if any(v==-7 for v in propagated) and (passed or propagated!=[-7,-7,-7]):
        raise ValueError('CPU callback error must propagate unchanged')
    result.update(cpu_ring_trial_pass=passed,cpu_ring_owner=owner,reservation_record_summary=record,
        dma_candidate_route=route,cpu_ring_stage=stage,cpu_ring_geometry=rings,observed_field_rows=52,
        cpu_ring_initialization_proven=passed,retained_memory_release_proven=False,
        candidate_address_not_active_route=True,dma_addressability_qualified=False,dma=False,irq_delivery=False,
        queue_publication=False,ethernet_proven=False,full_original_capture_health_scan=True,
        scope='Real retained Apple allocation and CPU-owned ring stores/readbacks; inbound routes remain disabled, no DMA/IRQ/packets')
    return result
