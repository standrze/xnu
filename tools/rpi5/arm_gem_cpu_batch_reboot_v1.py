# SPDX-License-Identifier: BSD-2-Clause
"""Unchanged arm-before-single-reboot launcher, new exact CPU-batch recorder."""
import builtins
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import stage_gem_cpu_batch_trial_v1 as stage
def import_(name,*args,**kwargs):
    if name=='serial_link_trial_v2':return builtins.__import__('serial_gem_cpu_batch_trial_v1',*args,**kwargs)
    return builtins.__import__(name,*args,**kwargs)
launch=stage.private(stage.publisher.launch,load_installation=stage.load_installation,
    __builtins__=dict(vars(builtins),__import__=import_),__file__=__file__,__doc__=__doc__)
