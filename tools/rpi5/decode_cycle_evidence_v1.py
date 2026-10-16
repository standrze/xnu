# SPDX-License-Identifier: BSD-2-Clause
"""Use existing complete capture and independent Linux return evidence bodies."""
try:
    from . import decode_cycle_trial_v1 as stage
    from . import serial_decode_cycle_trial_v1 as recorder
    from . import link_trial_evidence_v2 as original
except ImportError:
    import decode_cycle_trial_v1 as stage
    import serial_decode_cycle_trial_v1 as recorder
    import link_trial_evidence_v2 as original
return_source_pins = stage.private(original.return_source_pins, stage=stage)
inspect_return = stage.private(original.inspect_return, stage=stage,
    return_source_pins=return_source_pins)
captured = stage.private(original.captured, stage=stage, recorder=recorder)
collect_return = stage.private(original.collect_return, stage=stage,
    captured=captured, return_source_pins=return_source_pins, inspect_return=inspect_return)
load_return = stage.private(original.load_return, stage=stage,
    captured=captured, return_source_pins=return_source_pins, inspect_return=inspect_return)
