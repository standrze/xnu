# SPDX-License-Identifier: BSD-2-Clause
"""Same three raw exchanges, late-root admission and exact snapshot filtering."""
try:
    from . import root42_pthread_command_evidence as base
    from . import root42_ready_trial_core as core
    from . import stage_pcie_trial_v3 as helpers
except ImportError:
    import root42_pthread_command_evidence as base
    import root42_ready_trial_core as core
    import stage_pcie_trial_v3 as helpers


def replay_commands(state,raw,report,receipt,files):
    core.snapshots(raw,report)
    return helpers.private(base.replay_commands,core=core.bind(report))(state,raw,report,receipt,files)
