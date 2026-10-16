/* SPDX-License-Identifier: BSD-2-Clause */
/* Included only in a distinct, single-primary loader composition.  Phase 1
 * is callable only after the original container/root verification and exact
 * resolved-plan success; phase 2 follows materialize and placement equality.
 * It does not manufacture those proofs, retry, extend the outer deadline or
 * increase the existing two-renewal budget. */
static const void *copy_phase_kernel;
static const uint8_t *copy_phase_root;
static size_t copy_phase_kernel_bytes, copy_phase_root_bytes;
static const struct rpi5_handoff_plan *copy_phase_plan;
static struct rpi5_macho_placement copy_phase_placement;
static uint64_t copy_phase_frequency;
static unsigned copy_phase_transfer_admitted;

static int copy_phase_equal(const struct rpi5_macho_placement *a,
    const struct rpi5_macho_placement *b)
{
    if (a->header!=b->header || a->end!=b->end || a->entry!=b->entry ||
        !a->count || a->count>32 || a->count!=b->count) return 0;
    for (uint32_t i=0;i<a->count;i++)
        if (a->destination[i]!=b->destination[i]) return 0;
    return 1;
}

static int copy_watchdog_checkpoint(size_t completed,
    const struct rpi5_handoff_plan *plan,
    const struct rpi5_macho_placement *materialized)
{
    uint64_t now;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
    if (!copy_watchdog_base || !copy_phase_frequency ||
        copy_phase_frequency>UINT32_MAX || !plan || !validated_kernel ||
        !validated_kernel_length || !validated_init || !validated_init_length ||
        (validated_init_length&0x3fff) || validated_init_length>0x4000000 ||
        !plan->kernel.count || plan->kernel.count>32 ||
        plan->kernel.header>=plan->kernel.end || plan->kernel.end>(1ull<<40) ||
        plan->kernel.entry<plan->kernel.header || plan->kernel.entry>=plan->kernel.end ||
        (completed!=1 && completed!=2) ||
        completed!=copy_watchdog_budget.completed+1 ||
        copy_watchdog_budget.total!=2 || copy_watchdog_budget.remaining!=3-completed)
        return 0;
    if (completed==1) {
        if (copy_phase_plan || materialized) return 0;
    } else if (completed==2) {
        if (!materialized || materialized==&plan->kernel || plan!=copy_phase_plan ||
            copy_phase_kernel!=validated_kernel || copy_phase_root!=validated_init ||
            copy_phase_kernel_bytes!=validated_kernel_length ||
            copy_phase_root_bytes!=validated_init_length ||
            !copy_phase_equal(&plan->kernel,&copy_phase_placement) ||
            !copy_phase_equal(materialized,&copy_phase_placement)) return 0;
    } else return 0;
    struct rpi5_watchdog_budget next=copy_watchdog_budget;
    if (!rpi5_watchdog_budget_step(&next,now,completed,2) ||
        (read32(copy_watchdog_base+0x1c)&0x30u)!=0x20u) return 0;
    /* The original same-boot FDT provider selected this already-running full
     * reset watchdog. Only its countdown changes; routing/status are read-only. */
    write32(copy_watchdog_base+0x24,0x5a000000u|(15u<<16));
    __asm__ volatile("dsb sy" ::: "memory");
    copy_watchdog_budget=next;
    if (completed==1) {
        copy_phase_plan=plan;copy_phase_placement=plan->kernel;
        copy_phase_kernel=validated_kernel;copy_phase_root=validated_init;
        copy_phase_kernel_bytes=validated_kernel_length;
        copy_phase_root_bytes=validated_init_length;
    } else copy_watchdog_base=0;
    return 1;
}

/* Admission only, no PM write. Keep the existing final transfer renewal, but
 * do not let late readback/secondary setup escape the original outer bound or
 * silently restart a consumed copy workflow. The 15s counter comparison is
 * nominal software policy, not a measured hardware watchdog-clock bound. */
static int copy_phase_transfer(const struct rpi5_handoff_plan *plan)
{
    uint64_t now;
    __asm__ volatile("isb; mrs %0, cntvct_el0" : "=r"(now));
    if (copy_phase_transfer_admitted || copy_watchdog_base ||
        copy_watchdog_budget.completed!=2 || copy_watchdog_budget.remaining ||
        copy_watchdog_budget.total!=2 || !plan || plan!=copy_phase_plan ||
        !copy_phase_frequency || copy_phase_frequency>UINT32_MAX ||
        now<copy_watchdog_budget.last_counter || now>=copy_watchdog_budget.deadline ||
        now-copy_watchdog_budget.last_counter>=15*copy_phase_frequency ||
        validated_kernel!=copy_phase_kernel || validated_init!=copy_phase_root ||
        validated_kernel_length!=copy_phase_kernel_bytes ||
        validated_init_length!=copy_phase_root_bytes ||
        !copy_phase_equal(&plan->kernel,&copy_phase_placement)) return 0;
    copy_phase_transfer_admitted=1;
    return 1;
}
