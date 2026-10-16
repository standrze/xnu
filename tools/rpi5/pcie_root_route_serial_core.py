# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only fixed root routing diagnostics, preserving complete capture API."""
from pathlib import Path
import re
import types
try:
    from . import rp1_config_trace_serial_core as prior
    from . import build_pcie_root_route_package as package_source
except ImportError:
    import rp1_config_trace_serial_core as prior
    import build_pcie_root_route_package as package_source

PREFIX,BEGIN,TRANSFER,ENTRY,COMMIT,PREPARED=(getattr(prior,n) for n in
    ('PREFIX','BEGIN','TRANSFER','ENTRY','COMMIT','PREPARED'))
PREPARED_PREFIX=prior.prior.PREPARED_PREFIX
inventory=prior.inventory
return_positions=prior.return_positions
NEW_FIELDS=('root_step','root_rc','root_reads','root_writes','root_id','root_hdr','root_bus_before',
    'root_bus_wanted','root_bus_actual','root_bus_post_link')
FIELDS=prior.FIELDS+NEW_FIELDS
SUFFIX=(rb' ROOT_STEP=(\d+) ROOT_RC=(-?\d+) ROOT_READS=(\d+) ROOT_WRITES=(\d+) ROOT_ID=([0-9a-f]{8}) '
    rb'ROOT_HDR=([0-9a-f]{8}) ROOT_BUS_BEFORE=([0-9a-f]{8}) ROOT_BUS_WANTED=([0-9a-f]{8}) '
    rb'ROOT_BUS_ACTUAL=([0-9a-f]{8}) ROOT_BUS_POST_LINK=([0-9a-f]{8})')
END=re.compile(prior.END.pattern+SUFFIX)


def parser():
    # Fixed already-pinned source, not received/caller-selected Python.
    text=Path(prior.prior.__file__).read_text()
    for old,new in (("'RPI5XNU:BL33:PCIE_ID_LINK_ELAPSED_TRIAL TAG='","'RPI5XNU:BL33:PCIE_ROOT_ROUTE_TRIAL TAG='"),
        ("('ubus_rc','link_rc')","('ubus_rc','link_rc','rp1_rc','rp1_xfer_rc','root_rc')")):
        if text.count(old)!=1:raise ValueError('Frozen root-route protocol boundary changed')
        text=text.replace(old,new)
    module=types.ModuleType('root_route_private_protocol');module.__package__=prior.prior.__package__
    exec(compile(text,prior.prior.__file__,'exec'),module.__dict__)
    module.FIELDS=FIELDS;module.END=END
    module.HEX=prior.prior.HEX|set(prior.NEW_FIELDS[7:])|set(NEW_FIELDS[4:])
    module.package_source=package_source
    return module


def inspect(data,report):
    contract=report.get('root_route',{})
    if (contract.get('end_fields')!=package_source.profile.FIELDS or
        tuple(contract.get(k) for k in ('root_id','header_type','primary_bus','secondary_bus','subordinate_bus',
            'root_write_offset','low24_value','root_reads_max','root_writes_max','endpoint_writes','command_writes'))!=
            (0x271214e4,1,0,1,1,0x18,0x010100,6,1,0,0) or
        any(contract.get(k) is not True for k in ('preserve_latency_byte','immediate_and_final_readbacks',
            'post_link_readback','write_before_perst_release','exact_write_value_guard','source_corrective_change',
            'root_permissions_extended','link_clock_config_snapshot_cores_unchanged','firmware_and_watchdogs_unchanged')) or
        any(contract.get(k) is not False for k in ('bar_sizing_or_assignment','changed_deadlines','physical_cause_proven','physical_id_verified'))):
        raise ValueError('Exact root-route diagnostic contract required')
    original=types.FunctionType(prior.inspect.__code__,dict(prior.inspect.__globals__,parser=parser))
    result=original(data,report);f=result['telemetry']
    if f['root_step']>9 or not -8<=f['root_rc']<=0 or f['root_reads']>6 or f['root_writes']>1:
        raise ValueError('Root-route telemetry outside actual source bounds')
    if result['rp1_id_trial_pass'] and (
        tuple(f[k] for k in ('root_step','root_rc','root_reads','root_writes','root_id'))!=(9,0,6,1,0x271214e4) or
        f['root_hdr']&0xff0000!=0x10000 or
        f['root_bus_wanted']!=(f['root_bus_before']&0xff000000)|0x010100 or
        f['root_bus_actual']!=f['root_bus_wanted'] or f['root_bus_post_link']!=f['root_bus_wanted']):
        raise ValueError('Success row contradicts completed exact root route/readbacks')
    result['scope']='One root0->bus1 route write with held-reset/value guards and post-link readback, then read-only RP1 ID. OK=0 remains failure; no endpoint writes, BAR, IRQ delivery, DMA or packets.'
    return result
