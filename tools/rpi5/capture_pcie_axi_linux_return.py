#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Independent read-only normal SSD witness for the corrected AXI pair capture."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture_pcie_trace_linux_return as original
import pcie_axi_evidence as evidence

stage=evidence.stage
_bindings=dict(original.__dict__,stage=stage,evidence=evidence,__file__=__file__,__doc__=__doc__)
for _name in ('remote_source','main'):
    _fn=getattr(original,_name)
    _bindings[_name]=types.FunctionType(_fn.__code__,_bindings,_name,_fn.__defaults__)
    globals()[_name]=_bindings[_name]


if __name__=='__main__':raise SystemExit(main())
