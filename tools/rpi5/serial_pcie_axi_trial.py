#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Receive-only corrected AXI trace recorder; accepted capture engine, private profile."""
import json
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import serial_pcie_trace_trial as original
import stage_pcie_axi_trial as staging
import pcie_axi_serial_core as protocol

receipt_guard,lease=original.receipt_guard,original.lease
inventory=protocol.inventory


def installation(directory):
    directory=directory.resolve()
    if directory.parent!=staging.ROOT/'build/rpi5':raise ValueError('Local corrected pair installation required')
    plan=json.loads((directory/'plan.json').read_text());result=json.loads((directory/'result.json').read_text())
    if plan['profile']!=staging.TRIAL:raise ValueError('Exact corrected AXI trial, not old/restored profile, required')
    staging.validate_result(result,plan)
    return dict(directory=str(directory),plan_sha256=staging.sha(directory/'plan.json'),
        result_sha256=staging.sha(directory/'result.json'),preflight=plan['preflight'],
        pair_sha256=result['pair_sha256'],original_linux_boot_id=plan['linux_boot_id'])


# The generic ARMED line retains its accepted spelling; both exact image and
# firmware hashes are part of that line and the new profile is receipt-bound.
_bindings=dict(original.__dict__,staging=staging,protocol=protocol,installation=installation,
    inventory=inventory,__file__=__file__,__doc__=__doc__)
main=types.FunctionType(original.main.__code__,_bindings,argdefs=original.main.__defaults__)


if __name__=='__main__':raise SystemExit(main())
