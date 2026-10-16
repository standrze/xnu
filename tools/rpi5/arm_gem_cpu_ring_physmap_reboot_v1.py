#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""One-reboot launcher namespace for the physmap CPU-ring trial."""
import builtins
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from . import stage_gem_cpu_ring_physmap_trial_v1 as stage
    from . import serial_gem_cpu_ring_physmap_trial_v1 as recorder
except ImportError:
    import stage_gem_cpu_ring_physmap_trial_v1 as stage
    import serial_gem_cpu_ring_physmap_trial_v1 as recorder


def import_(name, *args, **kwargs):
    if name == "serial_link_trial_v2":
        return recorder
    return builtins.__import__(name, *args, **kwargs)


launch = stage.private(stage.publisher.launch, load_installation=stage.load_installation,
    __builtins__=dict(vars(builtins), __import__=import_), __file__=__file__, __doc__=__doc__)
