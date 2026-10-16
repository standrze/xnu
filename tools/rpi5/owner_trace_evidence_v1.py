# SPDX-License-Identifier: BSD-2-Clause
"""Original complete capture/independent-return checks for passive owner rows."""
try:
    from . import owner_trace_trial_v1 as stage
    from . import serial_owner_trace_trial_v1 as recorder
    from . import link_trial_evidence_v2 as original
except ImportError:
    import owner_trace_trial_v1 as stage
    import serial_owner_trace_trial_v1 as recorder
    import link_trial_evidence_v2 as original
return_source_pins=stage.private(original.return_source_pins,stage=stage)
inspect_return=stage.private(original.inspect_return,stage=stage,return_source_pins=return_source_pins)
captured=stage.private(original.captured,stage=stage,recorder=recorder)
collect_return=stage.private(original.collect_return,stage=stage,captured=captured,
    return_source_pins=return_source_pins,inspect_return=inspect_return)
load_return=stage.private(original.load_return,stage=stage,captured=captured,
    return_source_pins=return_source_pins,inspect_return=inspect_return)
