#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact minimal phase schedule; two renewals, 60s outer bound, 15s hardware.

Apply to a distinct probe_main derivative, never edit its accepted parent.
The actual pre-copy call is dominated by successful container/root verification
and resolved non-overlap placement; the second by complete materialization and
placement equality. The former post-readback renewal is removed, not duplicated.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BODY=ROOT/'loader/rpi5/copy_watchdog_phase.inc'
OLD='''static void copy_watchdog_checkpoint(size_t completed)
{
    uint64_t now;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
    if (copy_watchdog_base && completed==copy_watchdog_budget.completed+1 &&
        rpi5_watchdog_budget_step(&copy_watchdog_budget,now,completed,2) &&
        (read32(copy_watchdog_base+0x1c)&0x30u)==0x20u) {
        write32(copy_watchdog_base+0x24,0x5a000000u|(15u<<16));
        __asm__ volatile("dsb sy" ::: "memory");
    }
    if (completed==2) copy_watchdog_base=0;
}'''


def transform(text):
    replacements=(
        (OLD, '#include "copy_watchdog_phase.inc"'),
        ('if (!reported || !payload_stage("PHYSICAL_COPY_BEGIN")) return 0;',
         'if (!reported || !copy_watchdog_checkpoint(1,&handoff,0) ||\n'
         '        !payload_stage("PHYSICAL_COPY_BEGIN")) return 0;'),
        ('    copy_watchdog_checkpoint(1);\n    if (!payload_stage("PHYSICAL_READBACK_BEGIN")) return 0;',
         '    if (!copy_watchdog_checkpoint(2,&handoff,&copied)) return 0;\n'
         '    if (!payload_stage("PHYSICAL_READBACK_BEGIN")) return 0;'),
        ('    copy_watchdog_checkpoint(2);\n    if (!(seed_stack_selftest()',
         '    /* No third renewal: readback and transfer use the second countdown. */\n'
         '    if (!(seed_stack_selftest()'),
        ('        copy_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,2,0,2};',
         '        copy_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,2,0,2};\n'
         '        copy_phase_frequency=frequency;'),
        ('        if (!transfer_watchdog_base ||\n',
         '        if (!copy_phase_transfer(pending_boot_data.handoff) || !transfer_watchdog_base ||\n'),
    )
    for old,new in replacements:
        if text.count(old)!=1:raise ValueError('Exact original copy phase boundary required')
        text=text.replace(old,new,1)
    # This profile is only for the actual full container+root materializer.
    required=('if (payload_ok && cpus_ok && psci_ok && reservations_ok',
        'rpi5_resolved_tree_handoff(validated_kernel,validated_kernel_length,',
        'rpi5_macho_materialize(validated_kernel,validated_kernel_length,',
        'if (copied.header!=handoff.kernel.header || copied.end!=handoff.kernel.end ||',
        'hash_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,0,0,128};',
        'copy_watchdog_budget=(struct rpi5_watchdog_budget){now+60*frequency,now,2,0,2};')
    if any(text.count(value)!=1 for value in required):raise ValueError('Exact full-image ownership and original budgets required')
    if text.count('copy_watchdog_checkpoint(')!=2:raise ValueError('Exactly two one-shot phase callsites required')
    ordered=('rpi5_resolved_tree_handoff(validated_kernel,validated_kernel_length,',
        'copy_watchdog_checkpoint(1,&handoff,0)',
        'rpi5_macho_materialize(validated_kernel,validated_kernel_length,',
        'copied.destination[i]!=handoff.kernel.destination[i]',
        'copy_watchdog_checkpoint(2,&handoff,&copied)',
        'rpi5_macho_verify_materialized(validated_kernel,validated_kernel_length,',
        'copy_phase_transfer(pending_boot_data.handoff)')
    positions=[text.index(value) for value in ordered]
    if positions!=sorted(positions):raise ValueError('Exact verified phase dominance required')
    return text


def sources():
    return [Path(__file__).resolve(),BODY,ROOT/'loader/rpi5/watchdog_budget.h',
        ROOT/'tools/rpi5/tests/test_loader_copy_phase.py',ROOT/'tools/rpi5/tests/loader_copy_phase_host.c']
