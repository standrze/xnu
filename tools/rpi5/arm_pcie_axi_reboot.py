#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Same exact armed-child/one-shot reboot guard, bound to corrected AXI recorder."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import arm_pcie_trace_reboot as original
import serial_pcie_axi_trial as recorder

arm_once,reboot_source=original.arm_once,original.reboot_source
_bindings=dict(original.__dict__,recorder=recorder,__file__=__file__,__doc__=__doc__)
main=types.FunctionType(original.main.__code__,_bindings,argdefs=original.main.__defaults__)


if __name__=='__main__':raise SystemExit(main())
