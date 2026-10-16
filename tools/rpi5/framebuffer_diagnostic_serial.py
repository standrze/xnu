# SPDX-License-Identifier: BSD-2-Clause
"""Exact early precheck trace plus the unchanged bounded FDT record oracle.

A complete rejection is a failed precheck, never evidence of framebuffer
absence or successful observation. This parser does not qualify physical RX.
"""
import re
from . import framebuffer_observation_serial as prior
PREFIX=prior.PREFIX
STAGES=('fdt_structure','phandles','mmio_binding','uart_clock_binding','watchdog_binding',
    'cpu_topology','psci_binding','memory','reservations','live_ranges','reserved_live_overlap',
    'primary_affinity','affinity_feature','secondary_1_off','secondary_2_off','secondary_3_off',
    'uart_exact_configuration','el1_state','active_watchdog_arm')
PROFILE='pi5-framebuffer-fdt-precheck-diagnostic-v1'
def inspect(data,report):
    if not isinstance(data,bytes) or len(data)>4*1024*1024:raise ValueError('Bounded raw capture required')
    tag=report.get('tag','')
    if report.get('profile')!=PROFILE or not re.fullmatch('[a-f0-9]{32}',tag):raise ValueError('Checked diagnostic package required')
    normalized=data.replace(b'\r\n',b'\n')
    wire=[r for r in normalized.split(b'\n') if PREFIX.encode() in r]
    try:rows=[r.decode('ascii') for r in wire]
    except UnicodeDecodeError as e:raise ValueError('Non-ASCII diagnostic') from e
    if len(rows)<4 or sum(len(r)+2 for r in rows)>32768:raise ValueError('Missing/oversized precheck trace')
    entry=PREFIX+f'ENTRY TAG={tag} EL2 PRECHECK NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT'
    if rows[0]!=entry:raise ValueError('Exact early diagnostic entry required')
    start=normalized.find(wire[0]);end=normalized.find(wire[-1],start)+len(wire[-1])
    if normalized[start:end]!=b'\n'.join(wire):raise ValueError('Interleaved or repeated diagnostic bytes')
    if re.search(rb'(?i)(panic\(|panic:|Debugger message:|RPI5XNU:[^\r\n]*(?:FAULT|EXCEPTION))',normalized[start:end]):
        raise ValueError('Fault in diagnostic interval')
    uart=prior.fields(rows[1],'UART',['CR','FR','IBRD','FBRD','LCRH'],' FIRMWARE_PRESERVED_CLOCK_UNVERIFIED')
    if any(v>0xffffffff for v in uart.values()) or uart['CR']&0x101!=0x101:
        raise ValueError('Actual enabled firmware UART snapshot required')
    at=2;checked=[]
    while at<len(rows) and rows[at].startswith(PREFIX+'CHECK '):
        value=prior.fields(rows[at],'CHECK',['STAGE'])['STAGE']
        if value!=len(checked)+1 or value>len(STAGES):raise ValueError('Exact sequential precheck stages required')
        checked.append(value);at+=1
    if not checked:raise ValueError('Missing precheck stage')
    if at<len(rows) and rows[at].startswith(PREFIX+'REJECT '):
        rejected=prior.fields(rows[at],'REJECT',['STAGE','RC'],' NO_RELOAD OBSERVATION_INCOMPLETE')
        if at!=len(rows)-1 or rejected['STAGE']!=checked[-1] or prior.signed(rejected['RC'])!=-1:
            raise ValueError('Exact terminal rejection required')
        return dict(diagnostic_pass=False,precheck_failed=True,complete_observation=False,
            failed_stage=rejected['STAGE'],failed_check=STAGES[rejected['STAGE']-1],result_rc=-1,
            uart=uart,checked_stages=checked,watchdog_arm_confirmed=False,
            framebuffer_absence_inferred=False,ownership_proven=False,scanout_cache_contract_proven=False,
            receiver_path_qualified=False,framebuffer_access=False,mailbox_requests=False,drawing=False,mirror_enabled=False)
    if checked!=list(range(1,len(STAGES)+1)):raise ValueError('Complete precheck sequence required')
    # Only the already-validated extra diagnostics are removed. The unchanged
    # original body parser still validates every actual inventory byte, extent,
    # result and STOP; the compatibility entry below is never a capture claim.
    old_entry=PREFIX+f'ENTRY TAG={tag} EL2 NO_XNU NO_CPU_ON ZERO_SERIAL_INPUT'
    old_data=('\r\n'.join([old_entry,*rows[at:]])+'\r\n').encode()
    result=prior.inspect(old_data,report)
    return result|dict(precheck_failed=False,complete_observation=result['diagnostic_pass'],
        checked_stages=checked,uart=uart,watchdog_arm_confirmed=True,
        framebuffer_absence_inferred=False,receiver_path_qualified=False,
        observation_bytes=sum(len(r)+2 for r in rows))
