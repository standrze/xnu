# SPDX-License-Identifier: BSD-2-Clause
"""Strict 53-row ring-only retry capture with automatic watchdog return."""
import copy
import hashlib
import re
from tools.rpi5 import gem_dma_batch_serial as old
from tools.rpi5 import gem_cpu_ring_retry_profile as profile

PREFIX=old.PREFIX;TRANSFER=old.TRANSFER;ENTRY=old.ENTRY;COMMIT=old.COMMIT
BEGIN=PREFIX+b'BEGIN PREFERRED_RAM_ONLY NO_BME'
ADDITIONS=('DMA_PREP','DMA_OWNER','DMA_RECORD','DMA_ROUTE','DMA_STAGE','DMA_RINGS')
ORDER=old.ORDER[:-6]+ADDITIONS+('END',)
health=old.health;return_positions=old.return_positions

def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original retry capture required')
    scan=health.inspect(data,hashlib.sha256(data).hexdigest())
    if scan['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:raise ValueError('Fault in complete capture including return tail')
    if return_positions(data) is None:raise ValueError('Automatic watchdog NVMe return not recorded')
    tag=report.get('tag','');marker=report.get('marker','')
    if not re.fullmatch('[0-9a-f]{32}',tag) or marker!=profile.trial.marker(tag) or data.count(marker.encode())!=1:raise ValueError('Exact retry image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=53 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode() for row in lines)!=ORDER:raise ValueError('Exactly 53 ordered records required')
    if lines[0]!=BEGIN:raise ValueError('Preferred-RAM-only route marker required')
    def fields(name,names):
        row=lines[ORDER.index(name)];match=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(n.encode()+rb'=(-?\d+)' for n in names.split()),row)
        if not match:raise ValueError('Exact retry fields required: '+name)
        return dict(zip(names.lower().split(),map(int,match.groups())))
    prep=fields('DMA_PREP','STEP ERROR BYTES PACKETS')
    owner=fields('DMA_OWNER','PREPARE STATE ATTEMPTED ACTIVE REVOKED DISABLED RECORD')
    record=fields('DMA_RECORD','FIXED DYNAMIC MANAGED_START MANAGED_END')
    route=fields('DMA_ROUTE','PHYSICAL PCI RP1 BYTES')
    stage=fields('DMA_STAGE','STATE ERROR ATTEMPTED WRITTEN READ CALLS CHECKS')
    rings=fields('DMA_RINGS','RX TX GENERATION BYTES DESC SLOTS TAIL OWNED')
    if prep!=dict(step=17,error=0,bytes=32768,packets=0):raise ValueError('All 17 preparation boundaries not completed')
    if owner!=dict(prepare=2,state=10,attempted=1,active=0,revoked=0,disabled=0,record=1):raise ValueError('Exact successful preferred-RAM owner required')
    if not 1<=record['fixed']<=32 or not 1<=record['dynamic']<=8 or (record['managed_start'],record['managed_end'])!=(0x6000000,0x10000000):raise ValueError('Same-boot immutable reservation record required')
    if (route['bytes']!=32768 or route['physical']%0x4000 or not record['managed_start']<=route['physical']<route['physical']+32768<=record['managed_end'] or
        route['pci']!=route['physical']+0x1000000000 or route['rp1']!=route['pci']):raise ValueError('Exact preferred-RAM route required')
    if stage!=dict(state=2,error=0,attempted=640,written=640,read=640,calls=81,checks=164):raise ValueError('Exact 640/640 CPU descriptor proof required')
    if (not rings['generation'] or rings['rx']!=route['rp1'] or rings['tx']!=route['rp1']+0x4000 or
        tuple(rings[k] for k in ('bytes','desc','slots','tail','owned'))!=(1280,16,64,256,160)):raise ValueError('Exact two-page ring geometry required')
    # Reuse the already-strict 52-row protocol stack after independently
    # validating every changed semantic.  The substitutions are compatibility
    # adapters only; the returned new fields below always come from raw bytes.
    normalized=data
    prep_row=lines[ORDER.index('DMA_PREP')];wire=prep_row+(b'\r\n' if prep_row+b'\r\n' in normalized else b'\n');normalized=normalized.replace(wire,b'',1)
    normalized=normalized.replace(BEGIN,old.BEGIN,1)
    owner_row=lines[ORDER.index('DMA_OWNER')];normalized=normalized.replace(owner_row,owner_row.replace(b'DISABLED=0',b'DISABLED=1'),1)
    route_row=lines[ORDER.index('DMA_ROUTE')];normalized=normalized.replace(route_row,route_row.replace(b'BYTES=32768',b'BYTES=294912'),1)
    adapted=copy.deepcopy(report);oldmarker=profile.trial.marker(tag)
    # The image marker did not change from v8; only its unique tag and complete
    # package digest identify this successor.
    adapted['marker']=oldmarker
    result=old.inspect(normalized,adapted)
    if not result['cpu_ring_trial_pass']:raise ValueError('Inherited controller/capability trial failed')
    result.update(cpu_ring_retry_trial_pass=True,preparation=prep,cpu_ring_owner=owner,
        reservation_record_summary=record,dma_candidate_route=route,cpu_ring_stage=stage,cpu_ring_geometry=rings,
        observed_field_rows=53,ordered_preparation_steps_completed=17,descriptor_writes=640,descriptor_readbacks=640,
        packet_spans=0,packet_mapping=False,bme=False,dma=False,irq_delivery=False,queue_publication=False,
        ethernet_proven=False,preferred_ram_route_only=True,full_original_capture_health_scan=True,
        capture_health=scan,normal_nvme_serial_boot_observed=True,automatic_watchdog_return_observed=True,
        scope='Two Apple descriptor pages, 640 CPU stores/readbacks, no packet spans, BME, DMA, IRQ, queues or packets')
    return result
