# SPDX-License-Identifier: BSD-2-Clause
"""Read-only same-schema evidence replay with v3 sealed source bindings."""
try:
    from . import stage_pcie_trial_v3 as stage
    from . import serial_pcie_trial_v3 as recorder
    from . import link_trial_evidence_v2 as base
except ImportError:
    import stage_pcie_trial_v3 as stage
    import serial_pcie_trial_v3 as recorder
    import link_trial_evidence_v2 as base

return_source_pins=stage.private(base.return_source_pins,stage=stage)
inspect_return=stage.private(base.inspect_return,stage=stage,return_source_pins=return_source_pins)
captured=stage.private(base.captured,stage=stage,recorder=recorder)
collect_return=stage.private(base.collect_return,stage=stage,captured=captured,return_source_pins=return_source_pins,inspect_return=inspect_return)
load_return=stage.private(base.load_return,stage=stage,captured=captured,return_source_pins=return_source_pins,inspect_return=inspect_return)
