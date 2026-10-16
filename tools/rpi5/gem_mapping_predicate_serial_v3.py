# SPDX-License-Identifier: BSD-2-Clause
"""Strict zero-TX mapping-predicate capture with automatic NVMe return."""
import copy
import hashlib
import re

from tools.rpi5 import gem_cpu_ring_retry_serial as retry
from tools.rpi5 import gem_mapping_predicate_check_v3 as checker

PREFIX=retry.PREFIX;TRANSFER=retry.TRANSFER;ENTRY=retry.ENTRY;COMMIT=retry.COMMIT
BEGIN=retry.BEGIN
old=retry.old
ADDITIONS=(retry.ADDITIONS[0],'DMA_MAP')+retry.ADDITIONS[1:]
ORDER=retry.old.ORDER[:-6]+ADDITIONS+('END',)
health=retry.health;return_positions=retry.return_positions
inventory=retry.old.inventory
PREPARED=retry.old.PREPARED;PREPARED_PREFIX=retry.old.PREPARED_PREFIX

def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:
        raise ValueError('Bounded original mapping capture required')
    scan=health.inspect(data,hashlib.sha256(data).hexdigest())
    if scan['runtime_fault_signature_observed'] or b'RPI5XNU:FAULT' in data:
        raise ValueError('Fault in complete mapping capture including return tail')
    if return_positions(data) is None:raise ValueError('Automatic watchdog NVMe return not recorded')
    tag=report.get('tag','');marker=report.get('marker','')
    expected=checker.b.retry.trial.marker(tag)
    if not re.fullmatch('[0-9a-f]{32}',tag) or marker!=expected or data.count(marker.encode())!=1:
        raise ValueError('Exact mapping diagnostic image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=54 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode() for row in lines)!=ORDER:
        raise ValueError('Exactly 54 ordered records with one DMA_MAP required')
    def fields(name,names):
        row=lines[ORDER.index(name)]
        match=re.fullmatch(PREFIX+name.encode()+b' '+b' '.join(n.encode()+rb'=(-?\d+)' for n in names.split()),row)
        if not match:raise ValueError('Exact mapping fields required: '+name)
        return dict(zip(names.lower().split(),map(int,match.groups())))
    mapping=fields('DMA_MAP','REASON PAGE ATTR VA PA PAR_R PAR_W')
    prep=fields('DMA_PREP','STEP ERROR BYTES PACKETS')
    owner=fields('DMA_OWNER','PREPARE STATE ATTEMPTED ACTIVE REVOKED DISABLED RECORD')
    record=fields('DMA_RECORD','FIXED DYNAMIC MANAGED_START MANAGED_END')
    route=fields('DMA_ROUTE','PHYSICAL PCI RP1 BYTES')
    stage=fields('DMA_STAGE','STATE ERROR ATTEMPTED WRITTEN READ CALLS CHECKS')
    rings=fields('DMA_RINGS','RX TX GENERATION BYTES DESC SLOTS TAIL OWNED')
    # REASON=41 is the success sentinel and cannot coexist with the exact
    # step-14/-13 rejection captured by this diagnostic transport.
    if not (1<=mapping['reason']<=40 and 0<=mapping['page']<=2 and
            0<=mapping['attr']<=0xffffffff and 0<=mapping['va']<=2 and
            all(0<=mapping[k]<2**64 for k in ('pa','par_r','par_w'))):
        raise ValueError('Bounded mapping diagnostic exceeded')
    if prep!=dict(step=14,error=-13,bytes=32768,packets=0):
        raise ValueError('Mapping-only preparation stop differs')
    if owner!=dict(prepare=3,state=5,attempted=0,active=0,revoked=0,disabled=0,record=1):
        raise ValueError('Mapping rejection owner state differs')
    if not 1<=record['fixed']<=32 or not 1<=record['dynamic']<=8 or (record['managed_start'],record['managed_end'])!=(0x6000000,0x10000000):
        raise ValueError('Same-boot reservation record differs')
    if any(route.values()) or any(stage.values()) or any(rings.values()):
        raise ValueError('Mapping diagnostic activated route, rings, queues or packets')
    normalized=data
    for name in ('DMA_MAP','DMA_PREP'):
        row=lines[ORDER.index(name)];wire=row+(b'\r\n' if row+b'\r\n' in normalized else b'\n')
        normalized=normalized.replace(wire,b'',1)
    normalized=normalized.replace(BEGIN,retry.old.BEGIN,1)
    adapted=copy.deepcopy(report)
    result=retry.old.inspect(normalized,adapted)
    if result['cpu_ring_trial_pass'] or result.get('dma') or result.get('irq_delivery') or result.get('queue_publication'):
        raise ValueError('Mapping diagnostic must remain a pre-activation rejection')
    result.update(mapping_predicate_diagnostic_pass=True,mapping_predicate=mapping,
        preparation=prep,cpu_ring_owner=owner,reservation_record_summary=record,
        dma_candidate_route=route,cpu_ring_stage=stage,cpu_ring_geometry=rings,
        observed_field_rows=54,packet_spans=0,packet_mapping=False,bme=False,dma=False,
        irq_delivery=False,queue_publication=False,ethernet_proven=False,
        preferred_ram_route_only=True,full_original_capture_health_scan=True,
        capture_health=scan,normal_nvme_serial_boot_observed=True,
        automatic_watchdog_return_observed=True,
        scope='One bounded Apple mapping predicate row; no route, rings, BME, DMA, IRQ, queues or packets')
    return result
