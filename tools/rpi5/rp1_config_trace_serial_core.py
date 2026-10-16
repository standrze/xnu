# SPDX-License-Identifier: BSD-2-Clause
"""Read-only RP1 config telemetry admission on the exact passive wire contract."""
from pathlib import Path
import re
import types
try:
    from . import pcie_link_elapsed_serial_core as prior
    from . import build_rp1_config_trace_package as package_source
except ImportError:
    import pcie_link_elapsed_serial_core as prior
    import build_rp1_config_trace_package as package_source

PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED'))
inventory=prior.inventory
return_positions=prior.return_positions
NEW_FIELDS=('rp1_call','rp1_rc','rp1_step','rp1_pass','rp1_index','rp1_xfer_rc','rp1_reads',
    'rp1_prev','rp1_value','rp1_id','rp1_hdr','rp1_bar0','rp1_bar1','rp1_selector','rp1_status')
FIELDS=prior.FIELDS+NEW_FIELDS
SUFFIX=(rb' RP1_CALL=(\d+) RP1_RC=(-?\d+) RP1_STEP=(\d+) RP1_PASS=(\d+) RP1_INDEX=(\d+) '
    rb'RP1_XFER_RC=(-?\d+) RP1_READS=(\d+) RP1_PREV=([0-9a-f]{8}) RP1_VALUE=([0-9a-f]{8}) '
    rb'RP1_ID=([0-9a-f]{8}) RP1_HDR=([0-9a-f]{8}) RP1_BAR0=([0-9a-f]{8}) RP1_BAR1=([0-9a-f]{8}) '
    rb'RP1_SELECTOR=([0-9a-f]{8}) RP1_STATUS=([0-9a-f]{8})')
END=re.compile(prior.END.pattern+SUFFIX)


def parser():
    # Reuse the unchanged full ordered-SD/FDT/link/return validator privately.
    # The source is a fixed local module in the candidate descriptor closure,
    # never a caller-selected module or a program received from the board.
    text=Path(prior.__file__).read_text()
    for old,new in (("'RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG='","'RPI5XNU:BL33:RP1_CONFIG_TRACE_TRIAL TAG='"),
                    ("('ubus_rc','link_rc')","('ubus_rc','link_rc','rp1_rc','rp1_xfer_rc')")):
        if text.count(old)!=1:raise ValueError('Frozen elapsed protocol boundary changed')
        text=text.replace(old,new)
    module=types.ModuleType('rp1_config_private_protocol');module.__package__=prior.__package__
    exec(compile(text,prior.__file__,'exec'),module.__dict__)
    module.FIELDS=FIELDS;module.END=END
    module.HEX=prior.HEX|set(NEW_FIELDS[7:]);module.package_source=package_source
    return module


def inspect(data,report):
    contract=report.get('rp1_config_trace',{})
    if (contract.get('end_fields')!=package_source.profile.FIELDS or
        tuple(contract.get(k) for k in ('snapshot_reads_max','selector_writes_max','endpoint_writes'))!=(32,32,0) or
        contract.get('phase14_means')!='RP1_INSPECTING' or
        contract.get('link_clock_and_config_cores_unchanged') is not True or
        any(contract.get(k) is not False for k in ('extra_mmio','changed_permissions','changed_deadlines',
            'source_corrective_change','physical_rp1_id_verified'))):
        raise ValueError('Exact passive config diagnostic contract required')
    result=parser().inspect(data,report);f=result['telemetry']
    if (f['rp1_call']>5 or f['rp1_step']>5 or f['rp1_pass']>1 or f['rp1_index']>15 or f['rp1_reads']>32 or
        not -10<=f['rp1_rc']<=0 or not -10<=f['rp1_xfer_rc']<=0):
        raise ValueError('RP1 telemetry enum/count outside actual source contract')
    if result['rp1_id_trial_pass'] and (
        tuple(f[k] for k in ('rp1_call','rp1_rc','rp1_step','rp1_pass','rp1_index','rp1_xfer_rc','rp1_reads'))!=(5,0,5,1,15,0,32) or
        f['rp1_id']!=f['id'] or f['rp1_hdr']&0xff0000 or f['rp1_bar0']&15 or f['rp1_bar1']!=f['bar1'] or
        f['rp1_selector']!=0x100000 or f['rp1_status']&0xf0!=0xb0 or
        f['rp1_prev']!=f['rp1_value']):
        raise ValueError('Success row contradicts complete stable RP1 snapshot')
    result['scope']='Exact passive controller/link/RP1 config diagnostic; OK=0 is never ID success. No endpoint writes, IRQ delivery, DMA or packets.'
    return result
