#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Retained-FDT single-CPU BAR inventory with bounded diagnostic records."""
import argparse
import json
from pathlib import Path
import re
try:
    from . import build_pcie_id_trace_package as engine
    from . import build_pcie_root_route_package as route
    from . import build_rp1_bars_root_kernel as kernel
except ImportError:
    import build_pcie_id_trace_package as engine
    import build_pcie_root_route_package as route
    import build_rp1_bars_root_kernel as kernel

ROOT=engine.ROOT
KERNEL_PACKAGE=ROOT/'build/rpi5/rp1-bars-root-kernel-20261013-v2'
KERNEL_SHA='aacec31cdd1463055e71e5361d706d3845bb3418b70ae3f99ba5f3f49d32f03e'
KERNEL_MANIFEST_SHA='67bc091bb7a0712c132229dd02e206b4b6063553b2116379ff89c10c21735164'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-1fklcw3v'
PRIOR_SHA='8e7325f77fe808fdd0a6855f1935b90fe19d5324c86f9d22304eadd273b04b4b'
PROFILE='rp1-six-bars-root-route-bounded-log-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_rp1_bars_root_package.py'
TEST=ROOT/'tools/rpi5/tests/test_rp1_bars_root_package.py'
PROTOCOL=ROOT/'tools/rpi5/rp1_bars_root_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_rp1_bars_root_serial.py'


def formats():
    rows=kernel.profile.logging.records((kernel.profile.FROZEN/'BCM2712PCIeIDTrialProgress.inc').read_text())
    result=[fmt.replace('\\n','\n') for _,fmt,_ in rows[:-1]]
    result += [fmt.replace('\\n','\n') for fmt in re.findall(r'kprintf\("([^"\n]+)"',kernel.profile.diagnostic_calls())]
    return result+[rows[-1][1].replace('\\n','\n')]


TRACE_END=formats()[-1]


def trace_contract():
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in formats():
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Actual bounded diagnostic record missing or duplicated')
    return dict(end_format=TRACE_END,record_formats=formats(),extra_mmio=False,changed_permissions=False,
        changed_deadlines=False,terminal_kprintf_count=14,max_scalar_arguments=15,max_encoded_bytes=100,
        normal_apple_logging_enabled=True,logging_assertions_enabled=True,final_end_after_diagnostics=True,
        reject_faults_through_normal_return=True,inter_call_atomicity_claimed=False,
        scope='Logging-only contract; additional endpoint size/restore operations are declared in bars_contract')


def configured_source():
    source=engine.load_private(Path(engine.__file__).resolve(),'_rp1_bars_bounded_loader')
    source.KERNEL_PACKAGE=KERNEL_PACKAGE;source.KERNEL_SHA=KERNEL_SHA;source.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA
    source.PROFILE=PROFILE;source.CHECKER=CHECKER;source.TEST=TEST;source.TRACE_END=TRACE_END
    source.trace_contract=trace_contract;original=source.configured_builder
    def configured_builder():
        b=original();old_inputs,old_marker=b.inputs,b.marker
        def inputs():
            pins,reports=old_inputs()
            if b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:raise ValueError('Root-route predecessor changed')
            m=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
            inherited=m['inputs_sha256']|m['headers_sha256']|m['generated_sha256']|{str(PRIOR_PACKAGE/'manifest.json'):PRIOR_SHA}
            for path in (Path(__file__).resolve(),CHECKER,TEST,PROTOCOL,SERIAL_TEST,
                ROOT/'tools/rpi5/pcie_capture_health_v1.py'):
                inherited[str(path)]=b.sha(path)
            for name,value in inherited.items():
                if name in pins and pins[name]!=value:raise ValueError('Bounded BAR loader source conflict')
                pins[name]=value
            b.verify(pins);return pins,reports
        b.inputs=inputs;b.marker=lambda tag:old_marker(tag).replace('PCIE_ID_TRACE_TRIAL ','RP1_BARS_ROOT_TRIAL ')
        return b
    source.configured_builder=configured_builder
    return source


def bars_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact BAR kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m.get('profile')!=kernel.PROFILE or m.get('kernel_sha256')!=KERNEL_SHA or
        tuple(m.get(k) for k in ('endpoint_config_writes_max','endpoint_config_reads_max','selector_writes_max',
            'bar_config_transactions_max','command_writes','logging_calls','logging_max_scalar_arguments'))!=(12,69,81,49,0,14,15) or
        any(m.get(k) is not True for k in ('config_core_unchanged','bar_probe_and_plan_objects_unchanged',
            'root_route_object_unchanged','global_log_encoder_unchanged','logging_assertions_enabled','firmware_guard_unchanged','watchdog_unchanged')) or
        any(m.get(k) is not False for k in ('bar_assignment_performed','bar_memory_decode_enabled','bar_mmio_mapped',
            'bar_failure_exact_restoration_claimed','logging_adds_mmio','logging_changes_guards','logging_changes_deadlines'))):
        raise ValueError('Exact contained BAR kernel contract differs')
    return dict(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,transport_replacements=m['bars_transport_replacements'],
        added_objects=m['bars_added_objects'],call_steps={1:'probe',2:'guard',3:'pure-plan',4:'guard',5:'complete'},
        config_transactions_max=49,endpoint_writes_max=12,endpoint_reads_max=69,selector_writes_max=81,
        write_offsets=list(range(0x10,0x28,4)),command_writes=0,all_six_mem32_nonprefetch_required=True,
        command_io_mem_bme_remain_disabled=True,original_values_restored_on_success=True,
        failed_access_quarantines_without_cleanup=True,failed_access_restoration_claimed=False,
        assignment_performed=False,bar_mmio_mapped=False,inbound_dma=False,irq_delivery=False,packets=False,
        allocation_plan_only=True,expected_root_route=m['root_route_physical_capture_sha256'],
        prior_route_runtime_clean=False,guards_and_watchdogs_unchanged=True)


def build():
    source=configured_source();bars=bars_contract();package,m=source.build()
    m.update(link_elapsed=route.previous.previous.elapsed_contract(),rp1_config_trace=route.previous.config_contract(),
        root_route=route.root_contract(),bars_contract=bars,previous_root_route_package_manifest_sha256=PRIOR_SHA,
        prior_component_contracts_are_scoped_not_whole_trial=True)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return package,m


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();p,m=build()
    print(json.dumps({k:m[k] for k in ('image','image_sha256','image_bytes','marker','kernel_sha256')},indent=2))
