# SPDX-License-Identifier: BSD-2-Clause
"""Physmap v4 raw capture and independent automatic NVMe return namespace."""
try:
    from . import stage_gem_physmap_mapping_trial_v4 as stage
    from . import serial_gem_physmap_mapping_trial_v4 as recorder
    from . import phy_reset_evidence_v1 as original
except ImportError:
    import stage_gem_physmap_mapping_trial_v4 as stage
    import serial_gem_physmap_mapping_trial_v4 as recorder
    import phy_reset_evidence_v1 as original
return_source_pins = stage.private(original.return_source_pins, stage=stage)
inspect_return = stage.private(original.inspect_return, stage=stage,
    return_source_pins=return_source_pins)
captured = stage.private(original.captured, stage=stage, recorder=recorder)
collect_return = stage.private(original.collect_return, stage=stage, captured=captured,
    return_source_pins=return_source_pins, inspect_return=inspect_return)
load_return = stage.private(original.load_return, stage=stage, captured=captured,
    return_source_pins=return_source_pins, inspect_return=inspect_return)

