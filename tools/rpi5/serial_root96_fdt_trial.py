#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Corrected FDT composition; original five bounded commands and auto-return."""
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_root96_trial as original
import stage_root96_fdt_trial as staging
import check_root96_fdt_package as package
import root96_fdt_trial_core as core
t,lease=core.t,original.lease
receipt_evidence_pins=original.receipt_evidence_pins


def source_pins():
    return staging.source_pins()|{str(Path(m.__file__).resolve()):staging.sha(Path(m.__file__)) for m in
        (original,core,core.original,core.identity,t,t.shell,core.prior)}


def installation(directory,report):
    directory=directory.resolve()
    if directory.parent!=staging.ROOT/'build/rpi5':raise ValueError('Exact corrected local installation required')
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    staging.validate_result(result,plan)
    if (plan['profile']!=staging.MODES['install'] or plan['preflight']!=report or
        result['protected_files_sha256']['probe.bin']!=report['image_sha256']):
        raise ValueError('Exact corrected installed candidate required')
    return dict(directory=str(directory),plan_sha256=staging.sha(directory/'plan.json'),result_sha256=staging.sha(directory/'result.json'))


_bindings=dict(original.__dict__,staging=staging,package=package,core=core,source_pins=source_pins,
               installation=installation,__doc__=__doc__)
trial=types.FunctionType(original.trial.__code__,_bindings)
_bindings['trial']=trial
main=types.FunctionType(original.main.__code__,_bindings,argdefs=original.main.__defaults__)


if __name__=='__main__':raise SystemExit(main())
