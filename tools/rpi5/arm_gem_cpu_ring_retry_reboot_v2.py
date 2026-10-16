# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged one-reboot launcher in the successor transport namespace."""
import builtins
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from . import stage_gem_cpu_ring_retry_trial_v2 as stage
    from . import serial_gem_cpu_ring_retry_trial_v2 as recorder
except ImportError:
    import stage_gem_cpu_ring_retry_trial_v2 as stage
    import serial_gem_cpu_ring_retry_trial_v2 as recorder
def import_(name,*args,**kwargs):
    if name=='serial_link_trial_v2':return recorder
    return builtins.__import__(name,*args,**kwargs)
launch=stage.private(stage.publisher.launch,load_installation=stage.load_installation,
    __builtins__=dict(vars(builtins),__import__=import_),__file__=__file__,__doc__=__doc__)
