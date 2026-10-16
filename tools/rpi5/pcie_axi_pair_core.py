# SPDX-License-Identifier: BSD-2-Clause
"""Private exact-card publication profile for the corrected C1 AXI trace pair."""
import types
try:
    from . import pcie_trace_pair_core as original
except ImportError:
    import pcie_trace_pair_core as original

TRIAL='pcie-axi-trace-pair-trial-v1'
RESTORE='pcie-axi-trace-pair-restore-v1'
NAMES={
    TRIAL:{
        'bl31.bin':('bl31.pre-rp1axi-20261013.bin','bl31.rp1axi-20261013.tmp','firmware-before.bin'),
        'probe.bin':(original.REUSED_ZSH_BACKUP,'probe.rp1axi-20261013.tmp','loader-before.bin')},
    RESTORE:{
        'bl31.bin':('bl31.rp1axi-trial-20261013.bin','bl31.post-rp1axi-20261013.tmp','firmware-trial.bin'),
        'probe.bin':(None,'probe.post-rp1axi-20261013.tmp','loader-trial.bin')},
}
TARGETS=original.TARGETS
REUSED_ZSH_BACKUP=original.REUSED_ZSH_BACKUP
GOOD_ZSH_SHA,GOOD_ZSH_BYTES=original.GOOD_ZSH_SHA,original.GOOD_ZSH_BYTES
os=original.os


def reuse_backup(plan,row):return plan['profile']==TRIAL and row['target']=='probe.bin'


def ssd_only_backup(plan,row):return plan['profile']==RESTORE and row['target']=='probe.bin'


# Rebind real publication functions in a private namespace. This preserves all
# exact block, mount, copy, journal, failure and cleanup semantics without
# mutating the accepted trace module or translating an incoming old profile.
_bindings=dict(original.__dict__,NAMES=NAMES,reuse_backup=reuse_backup,ssd_only_backup=ssd_only_backup)
for _name,_value in vars(original).items():
    if isinstance(_value,types.FunctionType) and _name not in ('reuse_backup','ssd_only_backup'):
        _bindings[_name]=types.FunctionType(_value.__code__,_bindings,_name,_value.__defaults__,_value.__closure__)
        globals()[_name]=_bindings[_name]
