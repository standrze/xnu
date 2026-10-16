#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Private adaptation of the frozen no-input ID loader for passive telemetry."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
PRIOR_PACKAGE=ROOT/'build/rpi5/pcie-id-trial-wpo7wy6_'
PRIOR_MANIFEST_SHA='ebcb3e48f34e087109089eea22e1bfa63f4bbc622d765a170e55b234c283a741'
PRIOR_BUILDER=ROOT/'tools/rpi5/build_pcie_id_trial_package.py'
PRIOR_BUILDER_SHA='bd91da772bf5bb09758f62ec4f34faef5faad3809b14f4e7d841b7a6097d562f'
PRIOR_CHECKER=ROOT/'tools/rpi5/check_pcie_id_trial_package.py'
PRIOR_CHECKER_SHA='4557de77f22ee720cf476c1faf1649def85ff9caa7dd3b0444dd1fe78fb790f7'
CHECKER=ROOT/'tools/rpi5/check_pcie_id_trace_package.py'
TEST=ROOT/'tools/rpi5/tests/test_pcie_id_trace_package.py'
KERNEL_PACKAGE=ROOT/'build/rpi5/pcie-id-trace-kernel-20261013-checked'
KERNEL_SHA='4020b6f2fdd7701c3f91aab0607c4e5e62ad864bce0e18069d0329264084fb93'
KERNEL_MANIFEST_SHA='7a4a7ea375d77b19c0d851c0f9a11f78a6591f314f8a01823d0f91e85e42c213'
PROFILE='pcie-id-passive-trace-single-cpu-loader-v1'
TRACE_END=('RPI5XNU:PCIEID:END OK=%u PHASE=%u LAST=%u LIFE=%u FLAGS=%02x ID=%08x '
    'COMMAND=%04x BAR1=%08x GEN=%u LANES=%u UBUS_STEP=%u UBUS_RC=%d UBUS_CB=%u '
    'GUARD=%u BANK=%u OFFSET=%08x DIR=%u IO_STAGE=%u VALUE=%08x\n')


def load_private(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def trace_contract():
    raw=(KERNEL_PACKAGE/'kernel.rp1-config').read_bytes()
    if raw.count(TRACE_END.encode()+b'\0')!=1:
        raise ValueError('Actual trace kernel END telemetry format missing or duplicated')
    return dict(end_format=TRACE_END,extra_mmio=False,changed_permissions=False,changed_deadlines=False,
        terminal_kprintf_count=3,phase7_means='UBUS_CONFIGURING',
        ubus_steps={1:'initial-guard',2:'init',3:'configure',4:'final-guard',5:'complete'},
        io_stages={1:'requested',2:'admitted-before-access',3:'access-completed',4:'post-guard-complete'},
        guard_reasons={1:'phase-owner-or-PM',2:'claim-state',3:'IRQ-before',4:'firmware-before',
            5:'lifecycle-provider',6:'owner-after',7:'firmware-after',8:'IRQ-after',9:'PM-after'})


def configured_builder():
    builder=load_private(PRIOR_BUILDER,'_rpi5_private_trace_loader')
    if builder.sha(PRIOR_BUILDER)!=PRIOR_BUILDER_SHA or builder.sha(PRIOR_CHECKER)!=PRIOR_CHECKER_SHA or \
       builder.sha(PRIOR_PACKAGE/'manifest.json')!=PRIOR_MANIFEST_SHA:
        raise ValueError('Frozen failed-ID loader chain changed')
    builder.PROFILE=PROFILE;builder.KERNEL_PACKAGE=KERNEL_PACKAGE
    builder.KERNEL_SHA=KERNEL_SHA;builder.KERNEL_MANIFEST_SHA=KERNEL_MANIFEST_SHA;builder.CHECKER=CHECKER
    original_marker,original_inputs=builder.marker,builder.inputs
    def marker(tag):
        return original_marker(tag).replace('PCIE_ID_TRIAL ','PCIE_ID_TRACE_TRIAL ')
    def inputs():
        pins,reports=original_inputs()
        previous=json.loads((PRIOR_PACKAGE/'manifest.json').read_text())
        inherited=previous['inputs_sha256']|previous['generated_sha256']
        inherited[str(PRIOR_PACKAGE/'manifest.json')]=PRIOR_MANIFEST_SHA
        for source in (Path(__file__).resolve(),CHECKER,TEST,PRIOR_CHECKER):
            inherited[str(source)]=builder.sha(source)
        for name,digest in inherited.items():
            if name in pins and pins[name]!=digest:raise ValueError('Trace package input conflict: '+name)
            pins[name]=digest
        builder.verify(pins);return pins,reports
    builder.marker=marker;builder.inputs=inputs
    return builder


def native_comparison(package):
    # The actual newly linked image is passed, not a historical/synthetic probe extent.
    result=subprocess.run(['python3',str(ROOT/'tools/rpi5/compare_native_macho.py'),
        str(KERNEL_PACKAGE/'kernel.rp1-config'),'--probe-build',str(package),'--post-cma-layout'],
        cwd=ROOT,capture_output=True,text=True,timeout=60)
    if result.returncode or result.stderr:raise ValueError('Actual trace native loader comparison failed: '+result.stderr)
    return json.loads(result.stdout)


def build():
    builder=configured_builder();contract=trace_contract()
    package,report=builder.build()
    if max(row['address']+row['memory_size'] for row in report['loads'])>=0xb000000:
        raise ValueError('Trace loader collides with retained FDT')
    report.update(trace_contract=contract,native_loader_comparison=native_comparison(package),
        failed_id_package_manifest_sha256=PRIOR_MANIFEST_SHA)
    (package/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return package,report


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    directory,report=build()
    print(json.dumps({name:report[name] for name in ('image','image_sha256','image_bytes','trial_tag','kernel_sha256')},indent=2))
