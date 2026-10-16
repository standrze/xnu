# SPDX-License-Identifier: BSD-2-Clause
"""Exact receive-only elapsed-settling/link trace; never turns OK=0 into success."""
import re
try:
    from . import pcie_id_serial_core as original
    from . import build_pcie_link_elapsed_package as package_source
except ImportError:
    import pcie_id_serial_core as original
    import build_pcie_link_elapsed_package as package_source

PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT=(getattr(original,n) for n in ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT'))
PREPARED_PREFIX=PREFIX+b'PREPARED '
PREPARED=PREFIX+b'PREPARED OK=1 CPUS=1'
inventory=original.inventory
return_positions=original.return_positions
FIELDS=('ok','phase','last','life','flags','id','command','bar1','gen','lanes',
    'ubus_step','ubus_rc','ubus_cb','guard','bank','offset','direction','io_stage','value',
    'link_call','link_step','link_rc','link_cb','reset_start_us','reset_end_us','reset_us','poll_reads','poll_us')
END=re.compile(PREFIX+rb'END OK=([01]) PHASE=(\d+) LAST=(\d+) LIFE=(\d+) FLAGS=([0-9a-f]{2}) ID=([0-9a-f]{8}) '
    rb'COMMAND=([0-9a-f]{4}) BAR1=([0-9a-f]{8}) GEN=(\d+) LANES=(\d+) UBUS_STEP=(\d+) UBUS_RC=(-?\d+) '
    rb'UBUS_CB=(\d+) GUARD=(\d+) BANK=(\d+) OFFSET=([0-9a-f]{8}) DIR=(\d+) IO_STAGE=(\d+) VALUE=([0-9a-f]{8}) '
    rb'LINK_CALL=(\d+) LINK_STEP=(\d+) LINK_RC=(-?\d+) LINK_CB=(\d+) RESET_START_US=(\d+) RESET_END_US=(\d+) '
    rb'RESET_US=(\d+) POLL_READS=(\d+) POLL_US=(\d+)')
HEX={'flags','id','command','bar1','offset','value'}
WIDE={'reset_start_us','reset_end_us','reset_us','poll_us'}


def inspect(data,report):
    if not isinstance(data,bytes) or not 0<len(data)<=4*1024*1024:raise ValueError('Bounded nonempty serial stream required')
    contract=report.get('trace_contract',{})
    if (contract.get('end_format')!=package_source.TRACE_END or contract.get('extra_mmio') is not False or
        contract.get('changed_permissions') is not False or contract.get('changed_deadlines') is not False):
        raise ValueError('Actual link trace package contract required')
    if not any(v.startswith('RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG=') for v in report['boot_markers']):
        raise ValueError('Distinct immutable elapsed loader marker required')
    elapsed=report.get('link_elapsed',{})
    if (tuple(elapsed.get(k) for k in ('reset_min_us','reset_max_us','poll_max_us','delay_max_chunk_us','delay_max_chunks'))!=
            (100000,110000,100000,1000,100) or
        any(elapsed.get(k) is not True for k in ('delay_accounts_guard_time','prior_c1_axi_objects_unchanged','firmware_guards_unchanged','watchdogs_unchanged')) or
        any(elapsed.get(k) is not False for k in ('additional_mappings','endpoint_writes','dma_enabled','physical_cause_proven','physical_correction_verified'))):
        raise ValueError('Exact bounded elapsed correction contract required')
    lines=[line.rstrip(b'\r') for line in data.split(b'\n') if line.startswith(PREFIX)]
    if len(lines)!=3 or lines[0]!=BEGIN:raise ValueError('Exactly three ordered trace rows required')
    prepared=re.fullmatch(PREPARED_PREFIX+rb'OK=([01]) CPUS=1',lines[1]);matched=END.fullmatch(lines[2])
    if not prepared or not matched:raise ValueError('Malformed/partial elapsed diagnostic row')
    fields={k:int(v,16 if k in HEX else 10) for k,v in zip(FIELDS,matched.groups())}
    for key,value in fields.items():
        if key in ('ubus_rc','link_rc'):valid=-2**31<=value<2**31
        else:valid=0<=value<2**(64 if key in WIDE else 32)
        if not valid:raise ValueError('Telemetry integer outside actual C field width')
    if (fields['ubus_step']>5 or fields['guard']>9 or fields['io_stage']>4 or
        not -5<=fields['ubus_rc']<=0 or fields['ubus_cb']>23 or fields['bank']>2 or fields['direction']>1 or
        fields['link_call']>5 or fields['link_step']>14 or not -10<=fields['link_rc']<=0 or
        fields['link_cb']>121 or fields['poll_reads']>21):
        raise ValueError('Telemetry enumeration outside actual source contract')
    passed=fields['ok']==1
    if passed and (prepared.group(1)!=b'1' or
        tuple(fields[k] for k in ('phase','last','life','flags','id'))!=(5,5,3,31,0x00011de4) or
        fields['gen'] not in (1,2) or fields['lanes'] not in (1,2,4) or fields['bar1']&15 or
        fields['ubus_step']!=5 or fields['ubus_rc']!=0 or fields['ubus_cb'] not in (20,23) or fields['guard']!=0 or
        (fields['link_call'],fields['link_step'],fields['link_rc'])!=(5,14,0) or
        not 1<=fields['poll_reads']<=21 or fields['link_cb']!=41+4*(fields['poll_reads']-1) or
        not 100000<=fields['reset_us']<=110000 or fields['reset_end_us']-fields['reset_start_us']!=fields['reset_us'] or
        fields['poll_us']>100000):
        raise ValueError('Success row contradicts exact RP1-ID/link/elapsed conditions')
    prefix=data[:data.index(BEGIN)]
    if (prefix.count(b'Boot mode: SD (01)')!=1 or prefix.count(ENTRY)!=1 or prefix.count(TRANSFER)!=1 or
        re.findall(rb'Read probe\.bin bytes (\d+) hnd ',prefix)!=[str(report['image_bytes']).encode()]):
        raise ValueError('Exact fresh SD image/transfer required')
    ordered=[b'Boot mode: SD (01)',b'Read probe.bin bytes '+str(report['image_bytes']).encode()+b' hnd ',ENTRY,
        *[v.encode() for v in report['boot_markers']],TRANSFER,COMMIT,*lines]
    positions=[]
    for marker in ordered:
        if data.count(marker)!=1:raise ValueError('Missing or duplicate loader/kernel marker')
        positions.append(data.index(marker))
    if positions!=sorted(positions):raise ValueError('Loader/materialization/trace order differs')
    if any(marker in data[:data.index(lines[2])+len(lines[2])] for marker in
        (b'panic(cpu',b'RPI5XNU:BL33:STOP',b'RPI5XNU:BL33:EXCEPTION',b'REJECTED',b'RPI5XNU:SHELL:READY',b'RPI5XNU:SOAK:ARM')):
        raise ValueError('Faulted or unexpected userspace/soak trial')
    if return_positions(data) is None:raise ValueError('Complete bounded normal NVMe return not recorded')
    return dict(trace_capture_valid=True,diagnostic_outcome='passed' if passed else 'failed',rp1_id_trial_pass=passed,
        prepared_ok=prepared.group(1)==b'1',telemetry=fields,endpoint_config_writes=0,
        inbound_dma_windows_enabled=0,builtin_msi_bar_enabled=False,normal_nvme_serial_boot_observed=True,
        independent_linux_return_proven=False,full_production_lifecycle_proven=False,
        ethernet_proven=False,irq_delivery=False,dma=False,
        scope='Exact controller/link timing trace; OK=0 is a captured failure, never RP1-ID success. No endpoint writes, IRQ delivery, DMA or packets.')
