#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct contained BAR image with fresh nested-guard composition."""
import json
from pathlib import Path
from tools.rpi5 import build_pcie_owner_trace_package as prior
from tools.rpi5 import build_pcie_guard_composition_kernel as kernel
from tools.rpi5 import build_pcie_id_trace_package as private
ROOT=prior.ROOT
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-guard-composition-kernel-20261013-v1'
KERNEL_SHA='a6fcad2e4736ad8de960679fe93496b0689985a2e02f09b5a5b5edaccdcd5b98'
KERNEL_MANIFEST_SHA='89792a4b0c86fec83d9123cf9f92247bf92257c9e19439ae7383bd65fe34b71c'
PRIOR_OWNER_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-h62s3uww'
PRIOR_OWNER_SHA='d1230ae161b7ed904e157927ff024d50230e03f47d2a5a3e077e8ebab7fefb7d'
PROFILE='pcie-fresh-nested-guard-composition-bars-single-cpu-loader-v1'
CHECKER=ROOT/'tools/rpi5/check_pcie_guard_composition_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_guard_composition_package.py'
PROTOCOL=ROOT/'tools/rpi5/pcie_guard_composition_serial_core.py'
SERIAL_TEST=ROOT/'tools/rpi5/tests/test_pcie_guard_composition_serial.py'


def guard_contract():
    if kernel.audit.sha(KERNEL_PACKAGE/'manifest.json')!=KERNEL_MANIFEST_SHA:raise ValueError('Exact guard kernel changed')
    m=json.loads((KERNEL_PACKAGE/'manifest.json').read_text())
    if (m['profile']!=kernel.PROFILE or m['kernel_sha256']!=KERNEL_SHA or
        m['guard_composition']!=kernel.profile.unchanged_contract() or
        m['guard_predicates_and_call_order_unchanged'] is not False or
        m['owner_client_core_secure_objects_unchanged'] is not True or
        m['transport_mmio_guard_sites_unchanged'] is not True or
        len(m['guard_composition_object_replacements'])!=1):raise ValueError('Exact nested composition required')
    return dict(m['guard_composition'],kernel_manifest_sha256=KERNEL_MANIFEST_SHA,
        object_replacements=m['guard_composition_object_replacements'])


def owner_contract():
    contract=prior.owner_contract()
    predecessor_delta=contract.pop('object_replacements')
    contract.update(kernel_manifest_sha256=KERNEL_MANIFEST_SHA,guard_policy_unchanged=False,
        object_replacements=guard_contract()['object_replacements'],
        predecessor_owner_trace_object_replacements=predecessor_delta,
        transport_guard_composition_changed=True,owner_implementations_unchanged=True,
        cause_proven_scope='This passive snapshot is not a standalone physical cause proof; preceding PM-limit receipt is separately bound in the new kernel manifest',
        scope='Unchanged passive in-memory owner telemetry; transport composes the same fresh owner calls without redundant outer PM/IRQ calls')
    return contract


def trace_contract():
    result=prior.trace_contract();raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    for fmt in result['record_formats']:
        if raw.count(fmt.encode()+b'\0')!=1:raise ValueError('Exact linked passive row missing')
    result['scope']='Same bounded nineteen passive rows; fresh nested guard composition is separately and explicitly described'
    return result


def configured_owner():
    owner=private.load_private(Path(prior.__file__).resolve(),'_guard_owner_loader')
    for name in ('KERNEL_PACKAGE','KERNEL_SHA','KERNEL_MANIFEST_SHA','PROFILE','CHECKER','TEST','PROTOCOL','SERIAL_TEST'):
        setattr(owner,name,globals()[name])
    owner.owner_contract=owner_contract;owner.trace_contract=trace_contract
    configure=owner.configured_source
    def configured():
        source=configure();original=source.configured_builder
        def configured_builder():
            b=original();inputs=b.inputs;marker=b.marker
            def complete_inputs():
                pins,reports=inputs()
                if b.sha(PRIOR_OWNER_PACKAGE/'manifest.json')!=PRIOR_OWNER_SHA:raise ValueError('Frozen owner package changed')
                m=json.loads((PRIOR_OWNER_PACKAGE/'manifest.json').read_text())
                extra=m['inputs_sha256']|m['headers_sha256']|m['generated_sha256']|{str(PRIOR_OWNER_PACKAGE/'manifest.json'):PRIOR_OWNER_SHA}
                extra[str(Path(__file__).resolve())]=b.sha(Path(__file__).resolve())
                for path,value in extra.items():
                    if path in pins and pins[path]!=value:raise ValueError('Guard package input conflict')
                    pins[path]=value
                b.verify(pins);return pins,reports
            b.inputs=complete_inputs
            b.marker=lambda tag:marker(tag).replace('PCIE_OWNER_TRACE_TRIAL ','PCIE_GUARD_COMPOSITION_TRIAL ')
            return b
        source.configured_builder=configured_builder;return source
    owner.configured_source=configured
    return owner


def configured_source():return configured_owner().configured_source()


def build():
    package,m=configured_owner().build()
    m.update(guard_composition=guard_contract(),previous_owner_package_manifest_sha256=PRIOR_OWNER_SHA)
    (package/'manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')
    return package,m


if __name__=='__main__':
    path,m=build()
    print(json.dumps(dict(image=str(path/'probe.bin'),image_sha256=m['image_sha256'],image_bytes=m['image_bytes'],marker=m['marker'],kernel_sha256=m['kernel_sha256']),indent=2))
