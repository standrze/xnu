# SPDX-License-Identifier: BSD-2-Clause
"""Exact nine-command raw replay derived from the accepted three-exchange body."""
from pathlib import Path
import types
try:
    from . import root41_batch_evidence as original
    from . import root42_pthread_trial_core as core
except ImportError:
    import root41_batch_evidence as original
    import root42_pthread_trial_core as core

text = Path(original.__file__).read_text()
for old, new, count in (
    ('root41_batch_trial_core as core', 'root42_pthread_trial_core as core', 2),
    ("('B41:'", "('B42:'", 1),
    ('29-file identity, eight command outputs/statuses', '30-file identity, nine command outputs/statuses', 1),
):
    if text.count(old) != count:
        raise ValueError('Frozen three-exchange replay boundary changed')
    text = text.replace(old, new)
module = types.ModuleType('root42_command_replay_private')
module.__package__ = core.__package__
module.__file__ = str(Path(__file__).resolve())
exec(compile(text, module.__file__, 'exec'), module.__dict__)
module.core = types.SimpleNamespace(**vars(core), unsafe_response=core.prior.unsafe_response)
replay_commands = module.replay_commands
