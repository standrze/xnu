#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent Linux witness for a failed-before-admission corrected boot only."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture_root96_failed_return as original
import serial_root96_fdt_trial as recorder
import audit_root96_fdt_trial as audit


def source_pins():
    return audit.return_source_pins()|{str(Path(m.__file__).resolve()):recorder.staging.sha(Path(m.__file__)) for m in
        (sys.modules[__name__],original)}


_bindings=dict(original.__dict__,recorder=recorder,audit=audit,source_pins=source_pins,__doc__=__doc__)
for _name in ('load_failed','validate_return','main'):
    _function=getattr(original,_name)
    globals()[_name]=types.FunctionType(_function.__code__,_bindings,argdefs=_function.__defaults__)
    _bindings[_name]=globals()[_name]


if __name__=='__main__':raise SystemExit(main())
