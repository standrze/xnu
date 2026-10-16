#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Clock-state/GEM MID trial bound to the accepted exact Device handoff."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_decode_cycle_package as prior
from tools.rpi5 import build_pcie_gem_known_kernel as kernel
ROOT,private=prior.ROOT,prior.private
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-gem-identify-kernel-20261013-v2'
KERNEL_SHA='2959ed80b47c62aca7d74a648f15c18ef7c0fc3a7942f9165a9b4f118aad6643'
KERNEL_MANIFEST_SHA='090697cffdd4fb1604ae9fadef792e04261b565b756b6bdbccb984aacb13a624'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-omaujuxp'
PRIOR_SHA='2013d9e58efdb62253a96c86d273f1fc53df1311e58c7f5d17684240663186d1'
PROFILE='pcie-known-clocks-gem-mid-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_gem_identify_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_identify_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_gem_identify_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_gem_identify_serial.py'
DEVICE_MARKER=prior.DEVICE_MARKER
assignment_contract,guard_contract=prior.assignment_contract,prior.guard_contract


def gem_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact known-clock kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['gem_contract']!=kernel.contract() or
        len(m['gem_object_replacements'])!=2 or len(m['gem_added_objects'])!=1 or m['logging_calls']!=35 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact guarded GEM kernel required')
    return dict(m['gem_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['gem_object_replacements'],added_objects=m['gem_added_objects'])


def decode_contract():
    result=prior.decode_contract();old=result.pop('object_replacements');added=result.pop('added_objects')
    current=gem_contract()
    result.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=current['object_replacements'],
        added_objects=current['added_objects'],predecessor_decode_object_replacements=old,
        predecessor_decode_added_objects=added,endpoint_register_access=True,
        endpoint_register_access_scope='Read-only clock state and MID inside held maps; gem_contract is authoritative',
        native_modeled_pm_checks=62044,native_modeled_firmware_sequence=15509,native_modeled_guards=7754)
    return result


def owner_contract():
    result=prior.owner_contract();old=result.pop('object_replacements');added=result.pop('added_objects')
    current=gem_contract()
    result.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=current['object_replacements'],
        added_objects=current['added_objects'],predecessor_decode_object_replacements=old,
        predecessor_decode_added_objects=added,gem_reads_added=True,
        scope='Same passive owners and fresh guards; known inherited clock state and two MID reads inside held Device maps')
    return result


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['gem_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact GEM record missing')
    result.update(record_formats=m['gem_record_formats'],terminal_kprintf_count=35,
        scope='Twenty-five inherited records plus ten bounded clock/MID rows; END last; full raw health scan')
    return result


def configured_source():
    p=private.load_private(Path(prior.__file__).resolve(),'_gem_decode_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST','PRIOR_PACKAGE','PRIOR_SHA'):
        setattr(p,name,globals()[name])
    p.kernel=kernel;p.decode_contract=decode_contract;p.owner_contract=owner_contract;p.trace_contract=trace_contract
    source=p.configured_source();factory=source.configured_builder
    def configured_builder():
        b=factory();inputs,marker=b.inputs,b.marker
        def complete_inputs():
            pins,reports=inputs();path=Path(__file__).resolve();value=b.sha(path)
            if str(path) in pins and pins[str(path)]!=value:raise ValueError('GEM builder pin changed')
            pins[str(path)]=value;b.verify(pins);return pins,reports
        b.inputs=complete_inputs
        b.marker=lambda tag:marker(tag).replace('PCIE_DECODE_CYCLE_TRIAL ','PCIE_GEM_IDENTIFY_TRIAL ')
        return b
    source.configured_builder=configured_builder;return source


def build():
    source=configured_source();package,m=source.build()
    previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
    for name in ('link_elapsed','rp1_config_trace','root_route','bars_contract','guard_composition','rp1_device_handoff'):
        m[name]=previous[name]
    m.update(gem_contract=gem_contract(),decode_contract=decode_contract(),assignment_contract=assignment_contract(),owner_trace=owner_contract(),
        previous_decode_package_manifest_sha256=PRIOR_SHA,prior_component_contracts_are_scoped_not_whole_trial=True,
        endpoint_register_access=True,endpoint_register_writes=False,
        assignment_contract_scope='Unchanged BAR component; held-map register reads are specified by gem_contract')
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n');return package,m


if __name__=='__main__':
    p,m=build();print(json.dumps(dict(image=str(p/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
