/* SPDX-License-Identifier: BSD-2-Clause */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "loader/rpi5/handoff.h"
#include "loader/rpi5/watchdog_budget.h"
static uintptr_t copy_watchdog_base;
static struct rpi5_watchdog_budget copy_watchdog_budget;
static const void *validated_kernel;
static size_t validated_kernel_length;
static const uint8_t *validated_init;
static size_t validated_init_length;
static uint64_t fake_now;
static uint32_t route;
static unsigned reads,writes,barriers;
static uint8_t kernel[16],root[16];
static struct rpi5_handoff_plan plan;
static uint32_t read32(uintptr_t address)
{ assert(address==0x10001c);reads++;return route; }
static void write32(uintptr_t address,uint32_t value)
{ assert(address==0x100024 && value==(0x5a000000u|(15u<<16)));writes++; }
/* Python substitutes only the two architecture statement kinds. All phase
 * checks, budget logic, owner binding and PM callsites are the actual body. */
#include "copy_phase_native.inc"
static void reset(void)
{
    memset(&plan,0,sizeof plan);plan.kernel.header=0x7004000;
    plan.kernel.end=0x8230000;plan.kernel.entry=0x7008000;plan.kernel.count=2;
    plan.kernel.destination[0]=0x7004000;plan.kernel.destination[1]=0x7010000;
    validated_kernel=kernel;validated_kernel_length=sizeof kernel;
    validated_init=root;validated_init_length=0x1f0000;
    copy_watchdog_base=0x100000;copy_watchdog_budget=(struct rpi5_watchdog_budget){60000000,0,2,0,2};
    copy_phase_plan=0;copy_phase_kernel=0;copy_phase_root=0;
    copy_phase_kernel_bytes=copy_phase_root_bytes=0;
    memset(&copy_phase_placement,0,sizeof copy_phase_placement);
    copy_phase_frequency=1000000;copy_phase_transfer_admitted=0;
    fake_now=8505251;route=0x20;reads=writes=barriers=0;
}
static void unchanged_failure(size_t phase,const struct rpi5_handoff_plan *p,
    const struct rpi5_macho_placement *copied)
{
    struct rpi5_watchdog_budget old=copy_watchdog_budget;unsigned n=writes,b=barriers;
    assert(!copy_watchdog_checkpoint(phase,p,copied));
    assert(!memcmp(&old,&copy_watchdog_budget,sizeof old));assert(writes==n && barriers==b);
}
int main(void)
{
    reset();unchanged_failure(2,&plan,&plan.kernel);unchanged_failure(0,&plan,0);
    unchanged_failure(SIZE_MAX,&plan,0);unchanged_failure(1,0,0);
    unchanged_failure(1,&plan,&plan.kernel);
    for(unsigned fault=0;fault<14;fault++) {
        reset();
        switch(fault) {
        case 0:copy_watchdog_base=0;break;case 1:validated_kernel=0;break;
        case 2:validated_kernel_length=0;break;case 3:validated_init=0;break;
        case 4:validated_init_length++;break;case 5:validated_init_length=0x4004000;break;
        case 6:plan.kernel.count=33;break;case 7:plan.kernel.entry=plan.kernel.end;break;
        case 8:copy_watchdog_budget.total=3;break;case 9:copy_watchdog_budget.remaining=3;break;
        case 10:fake_now=60000000;break;case 11:copy_watchdog_budget.last_counter=fake_now+1;break;
        case 12:route=0x10;break;case 13:copy_phase_frequency=0;break;
        }
        unchanged_failure(1,&plan,0);
    }
    for(unsigned fault=0;fault<12;fault++) {
        reset();assert(copy_watchdog_checkpoint(1,&plan,0));
        struct rpi5_macho_placement copied=plan.kernel;struct rpi5_handoff_plan other=plan;
        fake_now=15781855;
        const struct rpi5_handoff_plan *p=&plan;const struct rpi5_macho_placement *c=&copied;
        switch(fault) {
        case 0:p=&other;break;case 1:c=0;break;case 2:c=&plan.kernel;break;
        case 3:validated_kernel=root;break;case 4:validated_init=kernel;break;
        case 5:validated_kernel_length++;break;case 6:validated_init_length+=0x4000;break;
        case 7:plan.kernel.destination[1]++;break;case 8:copied.destination[0]++;break;
        case 9:route=0;break;case 10:fake_now=60000000;break;
        case 11:copy_watchdog_budget.remaining=2;break;
        }
        unchanged_failure(2,p,c);
    }
    /* Nominal timeline reproduces the old uncovered gap. A strict 15-second
     * model expires before the old first checkpoint. It is not a claim that
     * the physical PM clock is exact. The new two phases cover the same work. */
    reset();const uint64_t physical_copy=7276604,readback_to_transfer=11000000;
    assert(fake_now+physical_copy>=15000000);
    assert(copy_watchdog_checkpoint(1,&plan,0));uint64_t first=fake_now;
    unchanged_failure(1,&plan,0);
    fake_now+=physical_copy;assert(fake_now-first<15000000);
    struct rpi5_macho_placement copied=plan.kernel;
    assert(copy_watchdog_checkpoint(2,&plan,&copied));assert(writes==2 && barriers==2);
    unchanged_failure(2,&plan,&copied);unchanged_failure(3,&plan,&copied);
    fake_now+=readback_to_transfer;assert(copy_phase_transfer(&plan));
    assert(!copy_phase_transfer(&plan));assert(writes==2);
    for(unsigned fault=0;fault<6;fault++) {
        reset();assert(copy_watchdog_checkpoint(1,&plan,0));copied=plan.kernel;
        fake_now+=physical_copy;assert(copy_watchdog_checkpoint(2,&plan,&copied));
        fake_now+=1;
        switch(fault) {
        case 0:fake_now=copy_watchdog_budget.last_counter+15000000;break;
        case 1:fake_now=copy_watchdog_budget.deadline;break;
        case 2:fake_now=copy_watchdog_budget.last_counter-1;break;
        case 3:plan.kernel.entry++;break;case 4:validated_init_length+=0x4000;break;
        case 5:copy_watchdog_budget.completed=1;break;
        }
        assert(!copy_phase_transfer(&plan));assert(writes==2);
    }
    puts("COPY_PHASE PASS ACTUAL_BODY TWO_RENEWALS OLD_GAP_REPRODUCED OWNER_ORDER_DEADLINE_FAULTS NOMINAL_MODEL_ONLY");
    return 0;
}
