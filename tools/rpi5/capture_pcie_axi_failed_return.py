#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Preserve corrected AXI diagnostic failure and independently witness SSD return."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture_pcie_trace_failed_return as original
import pcie_axi_evidence as evidence
import capture_pcie_axi_linux_return as normal

stage,recorder=evidence.stage,evidence.recorder
_bindings=dict(original.__dict__,stage=stage,recorder=recorder,evidence=evidence,normal=normal,
    __file__=__file__,__doc__=__doc__)
for _name in ('failed','main'):
    _fn=getattr(original,_name)
    _bindings[_name]=types.FunctionType(_fn.__code__,_bindings,_name,_fn.__defaults__)
    globals()[_name]=_bindings[_name]


if __name__=='__main__':raise SystemExit(main())
