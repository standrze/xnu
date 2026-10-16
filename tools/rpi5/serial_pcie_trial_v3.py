#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Same sealed receive-only v2 engine, immutable v3 case bindings."""
import builtins
from pathlib import Path
import sys
import types
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_pcie_trial_v3 as stage
import serial_link_trial_v2 as base


bound_sources=stage.private(base.bound_sources,stage=stage,__name__=__name__)
revalidate=stage.private(base.revalidate,stage=stage,bound_sources=bound_sources)
bindings=stage.private(base.bindings,stage=stage,revalidate=revalidate,__file__=__file__,__doc__=__doc__)
main=stage.private(base.main,stage=stage,bindings=bindings,__doc__=__doc__)

if __name__=='__main__':raise SystemExit(main())
