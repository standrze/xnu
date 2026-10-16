# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged full raw capture and independent-return bodies, v2 source binding."""
try:
    from . import phy_reset_trial_v2 as stage
    from . import serial_phy_reset_trial_v2 as recorder
    from . import phy_reset_evidence_v1 as original
except ImportError:
    import phy_reset_trial_v2 as stage
    import serial_phy_reset_trial_v2 as recorder
    import phy_reset_evidence_v1 as original
return_source_pins=stage.private(original.return_source_pins,stage=stage)
inspect_return=stage.private(original.inspect_return,stage=stage,return_source_pins=return_source_pins)
captured=stage.private(original.captured,stage=stage,recorder=recorder)
collect_return=stage.private(original.collect_return,stage=stage,captured=captured,
    return_source_pins=return_source_pins,inspect_return=inspect_return)
load_return=stage.private(original.load_return,stage=stage,captured=captured,
    return_source_pins=return_source_pins,inspect_return=inspect_return)
