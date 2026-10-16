# SPDX-License-Identifier: BSD-2-Clause
"""Full raw health scan and exact assignment/restoration before read-only return."""
import copy
import hashlib
from tools.rpi5 import pcie_guard_composition_serial_core as prior
from tools.rpi5 import pcie_capture_health_v1 as health
from tools.rpi5 import build_pcie_bars_assignment_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions=prior.inventory,prior.return_positions
ADDITIONS=('ASSIGN','ASSIGNED_BARS','RESTORED_BARS','MAPPING')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)
same=prior.prior.same


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded whole assignment capture required')
    # Scan ORIGINAL raw bytes, before any private projection of framed rows.
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete original runtime capture, including after END')
    for name,expected in (('assignment_contract',package_source.assignment_contract()),('guard_composition',package_source.guard_contract()),
        ('owner_trace',package_source.owner_contract()),('trace_contract',package_source.trace_contract())):
        if not same(report.get(name),expected):raise ValueError('Exact assignment report contract required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_BARS_ASSIGNMENT_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique assignment image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=23 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly twenty-three ordered records required')
    formats=report['trace_contract']['record_formats'][-5:-1]
    rows=[prior.prior.prior._bar_fields(row,fmt) for row,fmt in zip(lines[-5:-1],formats)]
    progress,assigned,restored,mapping=rows
    if (progress['call']>6 or not -5<=progress['rc']<=0 or progress['state']>7 or progress['slot']>5 or
        progress['txns']>76 or progress['writes']>12 or progress['assigned']>63 or progress['restored']>63):
        raise ValueError('Assignment progress exceeds actual bounded state machine')
    normalized=data
    for row in lines[-5:-1]:
        raw=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(b'PCIE_BARS_ASSIGNMENT_TRIAL',b'PCIE_GUARD_COMPOSITION_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_BARS_ASSIGNMENT_TRIAL','PCIE_GUARD_COMPOSITION_TRIAL')
    adapted['boot_markers']=[v.replace('PCIE_BARS_ASSIGNMENT_TRIAL','PCIE_GUARD_COMPOSITION_TRIAL') for v in report['boot_markers']]
    adapted['owner_trace']=prior.package_source.owner_contract();adapted['trace_contract']=prior.package_source.trace_contract()
    result=prior.inspect(normalized,adapted);passed=result['bars_trial_pass']
    if passed:
        if (tuple(progress[k] for k in ('call','rc','state','slot','txns','writes','assigned','restored'))!=(6,0,6,2,58,6,7,7) or
            result['bars_telemetry']['bars_present']!=7 or result['telemetry']['command']!=0):
            raise ValueError('Success contradicts exact Pi assignment/restoration profile')
        for i,bar in enumerate(result['bars']):
            if assigned['bar'+str(i)]!=bar['plan'] or restored['bar'+str(i)]!=bar['original']:
                raise ValueError('Assignment/restoration differs from all-slot live observations')
        expected=dict(bar1_start=0x1f00000000,bar1_end=0x1f00400000,gem_start=0x1f00100000,
            gem_end=0x1f00104000,clock_start=0x1f00018000,clock_end=0x1f0002c000)
        if mapping!=expected:raise ValueError('Exact unmapped Device candidate differs')
    elif any(any(row.values()) for row in rows[1:]):
        raise ValueError('Failed caller cannot commit partial assignment observations')
    result.update(assignment_trial_pass=passed,assignment_telemetry=progress,assigned_bars=assigned,restored_bars=restored,
        mapping_candidate=mapping,mapping_performed=False,memory_decode_enabled=False,
        assignment_attempted=bool(progress['writes']),bar_assignment_performed=passed,
        exact_assignment_and_restore_proven=passed,original_bars_restored=passed,
        endpoint_config_writes=result['endpoint_config_writes']+progress['writes'],observed_field_rows=23,
        full_original_capture_health_scan=True,assignment_contract=report['assignment_contract'],
        scope='Bounded same-boot all-slot sizing, assignment and original restoration, with pure unmapped Device geometry; no decode, device accesses, IRQ delivery, DMA or Ethernet')
    return result
