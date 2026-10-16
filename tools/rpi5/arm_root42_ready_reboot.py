#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact new recorder with the same durable one-shot guarded SSH reboot."""
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import arm_root42_pthread_reboot as base
import stage_root42_ready_trial as stage
import serial_root42_ready_trial as recorder

scope={**vars(base),'stage':stage,'recorder':recorder,'__file__':__file__,'__doc__':__doc__}
for name in ('launch','main'):
    fn=getattr(base,name);scope[name]=types.FunctionType(fn.__code__,scope,argdefs=fn.__defaults__);globals()[name]=scope[name]


if __name__=='__main__':raise SystemExit(main())
