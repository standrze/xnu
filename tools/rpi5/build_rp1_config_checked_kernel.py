#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Distinct RP1 observer with explicit BAR0/BAR1 width agreement."""
import argparse
import json
from pathlib import Path
try:
    from . import build_rp1_config_kernel as base
except ImportError:
    import build_rp1_config_kernel as base

def build(output):
    old_core, old_inputs = base.CORE, base.inputs
    base.CORE = base.ROOT/'loader/rpi5/rp1_config_snapshot_checked.c'
    def inputs():
        pins, prior, objects = old_inputs()
        for source in (Path(__file__).resolve(),base.ROOT/'tools/rpi5/tests/test_rp1_config_checked.py'):
            pins[str(source)] = base.audit.sha(source)
        return pins,prior,objects
    base.inputs=inputs
    try:
        report=base.build(output)
    finally:
        base.CORE,base.inputs=old_core,old_inputs
    report['profile']='rp1-read-only-config-kernel-v2'
    report['bar0_cannot_consume_bar1']=True
    (output/'manifest.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    result=build(parser.parse_args().output_dir)
    print(json.dumps({name:result[name] for name in ('kernel','kernel_sha256','kernel_bytes','profile')}))
