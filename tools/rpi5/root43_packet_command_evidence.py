# SPDX-License-Identifier: BSD-2-Clause
"""Exact raw replay:31 file identity, ten outputs and actual B43 process exit."""
from pathlib import Path
import types
try:
    from . import root41_batch_evidence as original
    from . import root43_packet_trial_core as core
except ImportError:
    import root41_batch_evidence as original
    import root43_packet_trial_core as core

text=Path(original.__file__).read_text()
for old,new,count in (('root41_batch_trial_core as core','root43_packet_trial_core as core',2),
    ("('B41:'","('B43:'",1),('29-file identity, eight command outputs/statuses','31-file identity, ten command outputs/statuses',1)):
    text=core.replace(text,old,new,count)
module=types.ModuleType('root43_packet_command_replay_private');module.__package__=core.__package__;module.__file__=str(Path(__file__).resolve())
exec(compile(text,module.__file__,'exec'),module.__dict__)


def replay_commands(state,raw,report,receipt,files):
    core.snapshots(raw,report)
    return core.helpers.private(module.replay_commands,core=core.bind(report))(state,raw,report,receipt,files)
