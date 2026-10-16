#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Extend the frozen executable contract to actual platform TSD dispatch."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
PARENT=ROOT/'tools/rpi5/check_apple_pthread_kernel_contract.py'


def build():
    raw=PARENT.read_text()
    replacements={
        "prefix='apple-pthread-kernel-contract-'":"prefix='apple-pthread-kernel-tsd-contract-'",
        "commands,headers,comparisons=[],{},[]":"""commands,headers,comparisons=[],{},[]
    pins[str(ROOT/'tools/rpi5/check_apple_pthread_kernel_contract.py')]=sha(ROOT/'tools/rpi5/check_apple_pthread_kernel_contract.py')""",
        "'machine_routines.c':('_user_cont_hwclock_allowed','_user_timebase_type'),":"""'machine_routines.c':('_user_cont_hwclock_allowed','_user_timebase_type','_platform_syscall'),
        'machdep_call.c':('_thread_set_cthread_self',),
        'pcb.c':('_machine_thread_set_tsd_base',),""",
        "--disassemble-symbols=__bsdthread_register,_user_cont_hwclock_allowed,_user_timebase_type":"--disassemble-symbols=__bsdthread_register,_user_cont_hwclock_allowed,_user_timebase_type,_platform_syscall,_thread_set_cthread_self,_machine_thread_set_tsd_base",
        "profile='actual-linked-pi-pthread-kernel-contract-v1'":"profile='actual-linked-pi-pthread-kernel-tsd-contract-v2'",
        "actual_static_candidate_lc_unixthread=True,":"actual_static_candidate_lc_unixthread=True,actual_kernel_tsd_syscall_recompiled=True,",
    }
    for a,b in replacements.items():
        if raw.count(a)!=1:raise ValueError('Frozen kernel contract derivation changed')
        raw=raw.replace(a,b)
    scope={'__name__':'private_kernel_tsd_contract','__file__':str(Path(__file__).resolve())}
    exec(compile(raw,str(PARENT),'exec'),scope)
    return scope['build']()


if __name__=='__main__':build()
