#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Future v2 recorder: exact pwd bootstrap oracle, unchanged bounded TX workflow.

Requires its own explicit future staging/launch/evidence selection. This module
does not alter, repair, resume or accept the original failed trial.
"""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_root41_trial as original
import root41_batch_trial_v2 as core

staging,package,root_profile,lease,t=(getattr(original,n) for n in ('staging','package','root_profile','lease','t'))
installation=original.installation
receipt_evidence_pins=original.receipt_evidence_pins
package_evidence_pins=original.package_evidence_pins


def source_pins():
    paths=(Path(__file__).resolve(),Path(core.__file__).resolve(),
        staging.ROOT/'tools/rpi5/tests/test_root41_batch_v2.py')
    return original.source_pins()|{str(p):staging.sha(p) for p in paths}


def armed_line(report):
    return 'ROOT41_V2_CAPTURE_ARMED ZERO_TX_UNTIL_EXACT_FRESH_BOOT WATCHDOG_180_SECONDS IMAGE_SHA='+report['image_sha256']


_bindings=dict(original.__dict__,core=core,source_pins=source_pins,armed_line=armed_line,
    __file__=__file__,__doc__=__doc__)
for _name in ('trial','main'):
    _fn=getattr(original,_name)
    _bindings[_name]=types.FunctionType(_fn.__code__,_bindings,_name,_fn.__defaults__)
    globals()[_name]=_bindings[_name]


if __name__=='__main__':raise SystemExit(main())
