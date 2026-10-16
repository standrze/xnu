#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Capabilities receive-only body with original checked pre-ARM modem gate."""
from pathlib import Path
import struct
import sys
import termios
sys.path.insert(0,str(Path(__file__).resolve().parent))
import gem_capabilities_trial_v1 as stage
import serial_link_trial_v2 as original
import serial_root_forward_trial_v2 as accepted
assert_modem_ready=accepted.assert_modem_ready
bound_sources=stage.private(original.bound_sources,stage=stage,__name__=__name__)
revalidate=stage.private(original.revalidate,stage=stage,bound_sources=bound_sources)
base_bindings=stage.private(original.bindings,stage=stage,revalidate=revalidate,__file__=__file__,__doc__=__doc__)
bindings=stage.private(accepted.bindings,base_bindings=base_bindings,
    assert_modem_ready=assert_modem_ready,__file__=__file__)
main=stage.private(original.main,stage=stage,bindings=bindings,__doc__=__doc__)
if __name__=='__main__':raise SystemExit(main())
