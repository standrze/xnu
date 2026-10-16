# SPDX-License-Identifier: BSD-2-Clause
"""Private profile adapter around the frozen, actual-file-tested media engine.

Only profile and temporary filename bindings change. The shared original module
is never mutated; the no-reclaim policy cannot invoke the old unlink branch.
"""
import types
import root96_media_core as original

GOOD_SHA,GOOD_BYTES,FIRMWARE_SHA=original.GOOD_SHA,original.GOOD_BYTES,original.FIRMWARE_SHA
RETAINED,REDUNDANT=original.RETAINED,original.REDUNDANT
MODES=('root96-fdt-install-v1','root96-fdt-restore-v1')
TEMP={MODES[0]:'probe.root96-fdt-20261013.tmp',MODES[1]:'probe.root96-fdt-restore-20261013.tmp'}


def validate(plan):
    if plan.get('profile') not in MODES:raise ValueError('Corrected FDT install/restore only; no reclaim')
    if REDUNDANT in plan['protected_files']:raise ValueError('Expected already-reclaimed exact baseline')
    original.validate(dict(plan,profile=original.MODES[1+MODES.index(plan['profile'])]))


def execute(plan,capture,helper,snapshots,reference,guarded,run=None):
    validate(plan)
    namespace=dict(original.__dict__,MODES=('disabled-reclaim',*MODES),TEMP=TEMP,validate=validate)
    namespace['journal']=types.FunctionType(original.journal.__code__,namespace)
    operation=types.FunctionType(original.execute.__code__,namespace,argdefs=original.execute.__defaults__)
    return operation(plan,capture,helper,snapshots,reference,guarded,run)
