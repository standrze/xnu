# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only framed BAR diagnostics; reject faults even after terminal END."""
import copy
import hashlib
import json
import re
import types
try:
    from . import pcie_root_route_serial_core as prior
    from . import build_rp1_bars_root_package as package_source
    from . import pcie_capture_health_v1 as health
except ImportError:
    import pcie_root_route_serial_core as prior
    import build_rp1_bars_root_package as package_source
    import pcie_capture_health_v1 as health

PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED,PREPARED_PREFIX=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED','PREPARED_PREFIX'))
inventory,return_positions=prior.inventory,prior.return_positions
END=re.compile(prior.prior.prior.END.pattern.split(b' UBUS_STEP=')[0])
ORDER=('BEGIN','PREPARED','UBUS','LINK','RP1','ROOT','BARS',*(f'BAR{i}' for i in range(6)),'END')


def _bar_fields(line,fmt):
    parts=fmt.rstrip('\n').split(' ');values=line.decode('ascii').split(' ')
    if len(parts)!=len(values) or parts[0]!=values[0]:raise ValueError('Malformed bounded BAR record')
    result={}
    for shape,actual in zip(parts[1:],values[1:]):
        key,kind=shape.split('=');pattern='[0-9a-f]{8}' if kind=='%08x' else '[0-9a-f]{2}' if kind=='%02x' else '-?\\d+' if kind=='%d' else '\\d+'
        match=re.fullmatch(re.escape(key)+'=('+pattern+')',actual)
        if not match:raise ValueError('Wrong BAR record field/order/width')
        value=int(match[1],16 if kind.endswith('x') else 10)
        if not ((-2**31<=value<2**31) if kind=='%d' else (0<=value<2**(64 if kind=='%llu' else 32))):
            raise ValueError('BAR C scalar width exceeded')
        result[key.lower()]=value
    return result


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded full capture required')
    def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)
    if (canonical(report.get('trace_contract'))!=canonical(package_source.trace_contract()) or
        canonical(report.get('bars_contract'))!=canonical(package_source.bars_contract()) or
        report.get('prior_component_contracts_are_scoped_not_whole_trial') is not True):
        raise ValueError('Exact framed-logging and contained BAR contract required')
    if not any(v.startswith('RPI5XNU:BL33:RP1_BARS_ROOT_TRIAL TAG=') for v in report['boot_markers']):
        raise ValueError('Distinct immutable BAR loader marker required')
    fault=health.inspect(data,hashlib.sha256(data).hexdigest())
    if fault['runtime_fault_signature_observed']:raise ValueError('Fault in complete runtime capture, including after END')
    lines=[row.rstrip(b'\r') for row in data.split(b'\n') if row.startswith(PREFIX)]
    if len(lines)!=14 or tuple(row.split(b' ',1)[0][len(PREFIX):].decode('ascii') for row in lines)!=ORDER:
        raise ValueError('Exactly fourteen ordered framed records required')
    bars=_bar_fields(lines[6],package_source.formats()[4])
    slots=[_bar_fields(lines[7+i],package_source.formats()[5+i]) for i in range(6)]
    if (bars['bars_call']>5 or not -6<=bars['bars_rc']<=0 or bars['bars_state']>6 or bars['bars_slot']>5 or
        bars['bars_txns']>49 or bars['bars_writes']>12 or bars['bars_present']>63):raise ValueError('BAR diagnostic state outside actual bounds')
    # Reuse unchanged root/link/snapshot predicates on a private normalized
    # view only. Every raw framed row is checked above; no raw receipt rewritten.
    end=lines[-1]+b' '+b' '.join(row.split(b' ',1)[1] for row in lines[2:6])
    normalized=data
    for row in lines[2:-1]:
        raw=row+b'\r\n' if row+b'\r\n' in normalized else row+b'\n'
        normalized=normalized.replace(raw,b'',1)
    normalized=normalized.replace(lines[-1],end,1).replace(b'RP1_BARS_ROOT_TRIAL',b'PCIE_ROOT_ROUTE_TRIAL')
    adapted=copy.deepcopy(report)
    adapted['boot_markers']=[v.replace('RP1_BARS_ROOT_TRIAL','PCIE_ROOT_ROUTE_TRIAL') for v in report['boot_markers']]
    adapted['trace_contract']=dict(end_format=prior.package_source.TRACE_END,extra_mmio=False,changed_permissions=False,changed_deadlines=False)
    result=prior.inspect(normalized,adapted)
    if result['rp1_id_trial_pass']:
        if (tuple(bars[k] for k in ('bars_call','bars_rc','bars_state','bars_slot','bars_txns','bars_writes'))!=(5,0,5,5,49,12) or
            not bars['bars_present']&2 or result['telemetry']['command']&7):raise ValueError('Success contradicts six-BAR completion')
        for i,row in enumerate(slots):
            present=bool(bars['bars_present']&(1<<i));size=row['size']
            if not present:
                if any(row.values()):raise ValueError('Absent BAR has committed resources')
            elif (size<16 or size&(size-1) or row['mask']!=((-size)&0xffffffff) or
                row['mask']&15 or row['original']&(size-1) or row['plan']&(size-1) or
                row['plan']+size>2**32 or row['cpu_start']!=0x1f00000000+row['plan'] or
                row['cpu_end']!=row['cpu_start']+size):raise ValueError('Committed BAR size/alignment/span differs')
        if slots[0]['original']!=result['telemetry']['rp1_bar0'] or slots[1]['original']!=result['telemetry']['bar1'] or slots[1]['plan']:
            raise ValueError('Committed BAR originals/snapshot or RP1 zero-base plan differ')
        pending=[i for i in range(6) if bars['bars_present']&(1<<i)]
        order=[1]+sorted((i for i in pending if i!=1),key=lambda i:(-slots[i]['size'],i));cursor=0
        for i in order:
            size=slots[i]['size'];wanted=(cursor+size-1)&~(size-1)
            if slots[i]['plan']!=wanted:raise ValueError('Pure allocation plan order differs')
            cursor=wanted+size
    elif bars['bars_present'] or any(any(row.values()) for row in slots):
        raise ValueError('Failed caller cannot commit partial BAR output')
    result.update(bars_trial_pass=result['rp1_id_trial_pass'],bars_telemetry=bars,bars=slots,
        endpoint_config_writes=bars['bars_writes'],bar_assignment_performed=False,
        original_bars_restored=result['rp1_id_trial_pass'],clean_runtime_signature_scan=True,
        full_capture_fault_rejection=True,observed_field_rows=14,
        scope='Guarded six-BAR size/restore and pure plan only. Failure may leave a posted probe value; no forced cleanup, assignment, COMMAND write, device MMIO, IRQ, DMA or packets.')
    return result
