#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Zero-TX receiver namespace for the corrected physmap mapping v5 transport."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from . import stage_gem_physmap_mapping_trial_v5 as stage
    from . import serial_phy_reset_trial_v1 as original
except ImportError:
    import stage_gem_physmap_mapping_trial_v5 as stage
    import serial_phy_reset_trial_v1 as original
accepted = original.accepted
assert_modem_ready = original.assert_modem_ready
bound_sources = stage.private(original.bound_sources, stage=stage, __name__=__name__)
revalidate = stage.private(original.revalidate, stage=stage, bound_sources=bound_sources)
base_bindings = stage.private(original.base_bindings, stage=stage, revalidate=revalidate,
    __file__=__file__, __doc__=__doc__)
bindings = stage.private(original.bindings, base_bindings=base_bindings,
    assert_modem_ready=assert_modem_ready, __file__=__file__)
main = stage.private(original.main, stage=stage, bindings=bindings, __doc__=__doc__)
if __name__ == "__main__":
    raise SystemExit(main())
