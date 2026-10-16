#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Add failure-stage telemetry to the isolated ID kernel without new MMIO."""
import argparse
import json
from pathlib import Path
try:
    from . import build_pcie_id_trial_kernel as previous
except ImportError:
    import build_pcie_id_trial_kernel as previous

ROOT=previous.ROOT
BASE=ROOT/'build/rpi5/pcie-id-trial-kernel-20261013-checked'
BASE_SHA='7b72153435bff13409b0b85a718e5824e6de725eb0ca75e8a7d8b6cd96c64a72'
SET_PHASE=('    void setPhase(unsigned value) { if (value != BCM2712_PHY_FAILED) '
           '__atomic_store_n(&trialLastPhase, value, __ATOMIC_RELEASE); '
           '__atomic_store_n(&phase, value, __ATOMIC_RELEASE); }')


def transform_header(text):
    text=previous.base.replace_once(text,'    unsigned phase = BCM2712_PHY_EMPTY;',
        '    unsigned trialLastPhase = BCM2712_PHY_EMPTY;\n    unsigned phase = BCM2712_PHY_EMPTY;')
    text=previous.base.replace_once(text,
        '    void setPhase(unsigned value) { __atomic_store_n(&phase, value, __ATOMIC_RELEASE); }',SET_PHASE)
    return previous.base.replace_once(text,'    unsigned trialPhase() const { return getPhase(); }',
        '    unsigned trialPhase() const { return getPhase(); }\n'
        '    unsigned trialLast() const { return __atomic_load_n(&trialLastPhase,__ATOMIC_ACQUIRE); }\n'
        '    unsigned trialLife() const { return lifecyclePhase; }\n'
        '    unsigned trialFlags() const { return (unsigned)claimAttempted | ((unsigned)irqClaimed<<1) | '
        '((unsigned)fwClaimed<<2) | ((unsigned)trialPreclaim<<3) | ((unsigned)trialMode<<4); }')


def transform_body(text):
    text=previous.base.replace_once(text,'END OK=%u PHASE=%u ID=%08x',
        'END OK=%u PHASE=%u LAST=%u LIFE=%u FLAGS=%02x ID=%08x')
    return previous.base.replace_once(text,'(unsigned)ok,transport?transport->trialPhase():BCM2712_PHY_EMPTY,',
        '(unsigned)ok,transport?transport->trialPhase():BCM2712_PHY_EMPTY,\n'
        '        transport?transport->trialLast():BCM2712_PHY_EMPTY,\n'
        '        transport?transport->trialLife():0,transport?transport->trialFlags():0,')


def build(output):
    if previous.audit.sha(BASE/'manifest.json')!=BASE_SHA:raise ValueError('Frozen ID manifest changed')
    prior=json.loads((BASE/'manifest.json').read_text())
    pins={**prior['inputs_sha256'],**prior['generated_sha256'],str(BASE/'manifest.json'):BASE_SHA}
    for name,digest in pins.items():
        if previous.audit.sha(Path(name))!=digest:raise ValueError('Frozen ID input changed: '+name)
    for source in (Path(__file__).resolve(),ROOT/'tools/rpi5/tests/test_pcie_id_progress.py'):
        pins[str(source)]=previous.audit.sha(source)
    original_inputs,original_overlay=previous.base.inputs,previous.overlay
    def inputs():
        inherited,report,objects=original_inputs()
        for name,digest in pins.items():
            if name in inherited and inherited[name]!=digest:raise ValueError('Progress input conflict: '+name)
            inherited[name]=digest
        return inherited,report,objects
    def overlay(directory):
        cpp=original_overlay(directory);header=cpp.parent/'BCM2712PCIePHYTransport.h'
        header.write_text(transform_header(header.read_text()))
        body=cpp.parent/'BCM2712PCIeIDTrialProgress.inc'
        body.write_text(transform_body(previous.BODY.read_text()))
        cpp.write_text(previous.base.replace_once(cpp.read_text(),
            '#include "BCM2712PCIeIDTrial.inc"','#include "BCM2712PCIeIDTrialProgress.inc"'))
        return cpp
    previous.base.inputs=inputs;previous.overlay=overlay
    try:report=previous.build(output)
    finally:previous.base.inputs=original_inputs;previous.overlay=original_overlay
    report.update(progress_stage_reporting=True,progress_adds_mmio=False,
        failure_marker_fields=['PHASE','LAST','LIFE','FLAGS'],
        progress_flags=dict(pm_claim_attempted=1,irq_claim_completed=2,firmware_claim_completed=4,
                            preclaim_observed=8,trial_mode=16))
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',required=True,type=Path)
    report=build(parser.parse_args().output_dir.resolve())
    print(json.dumps({k:report[k] for k in ('kernel','kernel_sha256','kernel_bytes','progress_stage_reporting')}))
