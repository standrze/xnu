#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact no-decode BAR relocation/restoration loader; original pair preserved."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_guard_composition_package as prior
from tools.rpi5 import build_pcie_bars_assignment_kernel as kernel
from tools.rpi5 import build_pcie_id_trace_package as private
ROOT=prior.ROOT
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-bars-assignment-kernel-20261013-v2'
KERNEL_SHA='0508ad379c23d572e4761aaff46ebd65ae2442b2d31902d6e0cbdfe12f3ad6e5'
KERNEL_MANIFEST_SHA='9c038627143bc79fc453af85996ab8e74e073a18a90f4885dc868c906f4083bc'
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-zcz8y3h6'
PRIOR_SHA='5d72e57ee438b20f9cb12c5074c75416a487044c1e8ee156020d1625fcfef661'
PROFILE='pcie-bars-assignment-restoration-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_bars_assignment_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_bars_assignment_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_bars_assignment_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_bars_assignment_serial.py'


def assignment_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact assignment kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or m['assignment_contract']!=kernel.contract() or
        len(m['assignment_object_replacements'])!=1 or len(m['assignment_added_objects'])!=1 or m['logging_calls']!=23 or
        m['owner_client_core_secure_objects_unchanged'] is not True):raise ValueError('Exact guarded assignment required')
    return dict(m['assignment_contract'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['assignment_object_replacements'],added_objects=m['assignment_added_objects'])


guard_contract=prior.guard_contract


def owner_contract():
    result=prior.owner_contract();historical=result.pop('object_replacements')
    contract=assignment_contract()
    result.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,object_replacements=contract['object_replacements'],
        added_objects=contract['added_objects'],predecessor_guard_object_replacements=historical,
        transport_guard_composition_changed=False,transport_guard_composition_unchanged_from_parent=True,
        existing_bar_size_sequence_unchanged=True,assignment_sequence_added=True,
        scope='Same passive owner snapshot and fresh nested guard composition; bounded BAR relocation/restoration adds guarded config transactions')
    return result


def trace_contract():
    result=prior.trace_contract();m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in m['assignment_record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact linked assignment row missing')
    result.update(record_formats=m['assignment_record_formats'],terminal_kprintf_count=23,
        scope='Nineteen inherited bounded records plus four passive assignment/restoration/map-candidate rows; END remains last')
    return result


def configured_guard():
    g=private.load_private(Path(prior.__file__).resolve(),'_bars_assignment_guard_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST'):
        setattr(g,name,globals()[name])
    g.owner_contract=owner_contract;g.guard_contract=guard_contract;g.trace_contract=trace_contract
    original=g.configured_owner
    def configured_owner():
        owner=original();configure=owner.configured_source
        def configured():
            source=configure();factory=source.configured_builder
            def configured_builder():
                b=factory();inputs,marker=b.inputs,b.marker
                def complete_inputs():
                    pins,reports=inputs()
                    if b.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_SHA:raise ValueError('Frozen guard predecessor changed')
                    m=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
                    more=m['inputs_sha256']|m['headers_sha256']|m['generated_sha256']|{str(PRIOR_PACKAGE/'manifest.json'):PRIOR_SHA}
                    more[str(Path(__file__).resolve())]=b.sha(Path(__file__).resolve())
                    for path,value in more.items():
                        if path in pins and pins[path]!=value:raise ValueError('Assignment loader source conflict')
                        pins[path]=value
                    b.verify(pins);return pins,reports
                b.inputs=complete_inputs
                b.marker=lambda tag:marker(tag).replace('PCIE_GUARD_COMPOSITION_TRIAL ','PCIE_BARS_ASSIGNMENT_TRIAL ')
                return b
            source.configured_builder=configured_builder;return source
        owner.configured_source=configured;return owner
    g.configured_owner=configured_owner;return g


def configured_source():return configured_guard().configured_source()


def build():
    package,m=configured_guard().build()
    m.update(assignment_contract=assignment_contract(),previous_guard_package_manifest_sha256=PRIOR_SHA,
        guard_contract_scope='Unchanged predecessor component only; current object delta is in assignment_contract')
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return package,m


if __name__=='__main__':
    path,m=build();print(json.dumps(dict(image=str(path/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker']),indent=2))
