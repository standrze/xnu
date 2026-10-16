# SPDX-License-Identifier: BSD-2-Clause
"""Successor full raw capture and independent NVMe return namespace."""
try:
    from . import stage_gem_cpu_ring_retry_trial_v2 as stage
    from . import serial_gem_cpu_ring_retry_trial_v2 as recorder
    from . import phy_reset_evidence_v1 as original
except ImportError:
    import stage_gem_cpu_ring_retry_trial_v2 as stage
    import serial_gem_cpu_ring_retry_trial_v2 as recorder
    import phy_reset_evidence_v1 as original
return_source_pins=stage.private(original.return_source_pins,stage=stage)
inspect_return=stage.private(original.inspect_return,stage=stage,return_source_pins=return_source_pins)
captured=stage.private(original.captured,stage=stage,recorder=recorder)
collect_return=stage.private(original.collect_return,stage=stage,captured=captured,return_source_pins=return_source_pins,inspect_return=inspect_return)
load_return=stage.private(original.load_return,stage=stage,captured=captured,return_source_pins=return_source_pins,inspect_return=inspect_return)
