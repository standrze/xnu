#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact frozen command/return replay for the corrected FDT recorder only."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import audit_root96_trial as original
import serial_root96_fdt_trial as recorder
core,t,stage=recorder.core,recorder.t,recorder.staging
identity_audit,return_program=original.identity_audit,original.return_program


def return_source_pins():
    return recorder.source_pins()|{str(Path(m.__file__).resolve()):stage.sha(Path(m.__file__)) for m in
        (sys.modules[__name__],original,identity_audit,return_program)}


_bindings=dict(original.__dict__,recorder=recorder,core=core,t=t,stage=stage,
               return_source_pins=return_source_pins,__doc__=__doc__)
for _name in ('replay','local_child','load_capture','inspect_return','audit','main'):
    _function=getattr(original,_name)
    globals()[_name]=types.FunctionType(_function.__code__,_bindings,argdefs=_function.__defaults__)
    _bindings[_name]=globals()[_name]


if __name__=='__main__':raise SystemExit(main())
