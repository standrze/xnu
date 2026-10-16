# SPDX-License-Identifier: BSD-2-Clause
"""Whole raw health and exact MEM-only map/revoke/restore diagnostic records."""
import copy
import hashlib
import re
from tools.rpi5 import pcie_bars_assignment_serial_core as prior
from tools.rpi5 import build_pcie_decode_cycle_package as package_source
PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions,health,same=prior.inventory,prior.return_positions,prior.health,prior.same
ADDITIONS=('DECODE','DECODE_COMMAND')
ORDER=prior.ORDER[:-1]+ADDITIONS+('END',)


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded original decode capture required')
    if health.inspect(data,hashlib.sha256(data).hexdigest())['runtime_fault_signature_observed']:
        raise ValueError('Fault in complete original decode capture including after END')
    for name,expected in (('decode_contract',package_source.decode_contract()),('assignment_contract',package_source.assignment_contract()),
        ('guard_composition',package_source.guard_contract()),('owner_trace',package_source.owner_contract()),('trace_contract',package_source.trace_contract())):
        if not same(report.get(name),expected):raise ValueError('Exact decode report contract required: '+name)
    marker=report.get('marker','')
    if not marker.startswith('RPI5XNU:BL33:PCIE_DECODE_CYCLE_TRIAL TAG=') or data.count(marker.encode())!=1:
        raise ValueError('Exact unique decode image marker required')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=25 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly25 ordered records required')
    progress=prior.prior.prior.prior._bar_fields(lines[-3],report['trace_contract']['record_formats'][-3])
    parsed=re.fullmatch(PREFIX+rb'DECODE_COMMAND BEFORE=([0-9a-f]{4}) ENABLED=([0-9a-f]{4}) AFTER=([0-9a-f]{4})',lines[-2])
    if not parsed:raise ValueError('Exact three halfword COMMAND observations required')
    command=dict(zip(('before','enabled','after'),(int(v,16) for v in parsed.groups())))
    if (progress['call']>3 or not -5<=progress['rc']<=0 or progress['state']>9 or progress['txns']>34 or
        progress['writes']>2 or progress['mapped']>3 or progress['unmapped']>3):
        raise ValueError('Decode progress exceeds finite state machine')
    normalized=data
    for row in lines[-3:-1]:
        raw=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(b'PCIE_DECODE_CYCLE_TRIAL',b'PCIE_BARS_ASSIGNMENT_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['marker']=marker.replace('PCIE_DECODE_CYCLE_TRIAL','PCIE_BARS_ASSIGNMENT_TRIAL')
    adapted['boot_markers']=[v.replace('PCIE_DECODE_CYCLE_TRIAL','PCIE_BARS_ASSIGNMENT_TRIAL') for v in report['boot_markers']]
    adapted['owner_trace']=prior.package_source.owner_contract();adapted['trace_contract']=prior.package_source.trace_contract()
    result=prior.inspect(normalized,adapted);passed=result['assignment_trial_pass']
    if passed:
        if tuple(progress[k] for k in ('call','rc','state','txns','writes','mapped','unmapped'))!=(3,0,8,34,2,3,3):
            raise ValueError('Success contradicts complete exact map/revoke cycle')
        if command!=dict(before=0,enabled=2,after=0):raise ValueError('Exact MEM-only original COMMAND restoration required')
    elif any(command.values()):raise ValueError('Failed caller cannot commit partial decode observations')
    result.update(decode_cycle_trial_pass=passed,decode_telemetry=progress,decode_command=command,
        mapping_performed=passed,mappings_revoked=passed,memory_decode_performed=passed,
        memory_decode_enabled=False if passed else None,original_command_restored=passed,
        memory_decode_attempted=bool(progress['writes']),endpoint_register_access=False,
        endpoint_config_writes=result['endpoint_config_writes']+progress['writes'],observed_field_rows=25,
        full_original_capture_health_scan=True,decode_contract=report['decode_contract'],
        scope='Same-boot exact BAR assign; MEM-only command, two host-only Device maps, reverse revoke, original COMMAND and BAR restoration; no device register access, BME, DMA, IRQ or Ethernet')
    return result
