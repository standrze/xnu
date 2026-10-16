/* SPDX-License-Identifier: BSD-2-Clause */
/* Execute the actual protocol + immutable lease with explicit hardware doubles.
 * These returned operations do not emulate a bus hang or physical PM reset. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define RPI5_RECOVERY_PM_PROBE 1
#include "recovery_pm.inc"

static struct {
    uint64_t now, step, written_at, bad_counter;
    unsigned route_calls, count_calls, counter_calls, writes, orders, records;
    unsigned bad_route_at, bad_count_at, bad_counter_at, record_fail;
    uint32_t bad_route, bad_count;
    int stopped, reenter, stall_count;
    struct rpi5_recovery_observation recorded[2];
} fake;

static void reentry(void)
{
    if (fake.reenter) {
        struct rpi5_recovery_observation out, saved;
        memset(&out, 0xa5, sizeof(out)); saved = out;
        assert(recovery_run(&out) == -1 && !memcmp(&out, &saved, sizeof(out)));
    }
}
uint32_t rpi5_recovery_route(void)
{
    fake.route_calls++; reentry();
    return fake.route_calls == fake.bad_route_at ? fake.bad_route : 0x20;
}
uint32_t rpi5_recovery_countdown(void)
{
    fake.count_calls++; reentry();
    if (fake.count_calls == fake.bad_count_at) return fake.bad_count;
    if (!fake.writes) return 10u << 16;
    if (fake.stall_count && fake.count_calls >= 3) return recovery_lease.first_countdown;
    uint64_t elapsed = fake.now-fake.written_at;
    uint64_t ticks = elapsed*65536/recovery_pm.frequency;
    return ticks < (15u << 16) ? (15u << 16)-(uint32_t)ticks : 0;
}
void rpi5_recovery_write_countdown(uint32_t value)
{
    assert(value == 0x5a0f0000 && fake.writes == 0 && recovery_pm.write_attempts == 1);
    fake.writes++; fake.written_at = fake.now; reentry();
}
void rpi5_recovery_order(void) { fake.orders++; reentry(); }
uint64_t rpi5_recovery_counter(void)
{
    fake.counter_calls++; reentry();
    if (!(fake.stopped && fake.counter_calls >= 3)) fake.now += fake.step;
    return fake.counter_calls == fake.bad_counter_at ? fake.bad_counter : fake.now;
}
static int recovery_record(unsigned phase, const struct rpi5_recovery_observation *value)
{
    assert(phase == fake.records+1 && fake.records < 2);
    fake.recorded[fake.records++] = *value; reentry();
    return phase == fake.record_fail ? -1 : 0;
}
static void reset(uint64_t frequency)
{
    memset(&fake, 0, sizeof(fake)); memset(&recovery_pm, 0, sizeof(recovery_pm));
    memset(&recovery_lease, 0, sizeof(recovery_lease));
    recovery_pm.frequency = frequency; fake.now = frequency; fake.step = frequency/1000;
}
static void refused(unsigned expected_writes)
{
    struct rpi5_recovery_observation out, saved;
    memset(&out, 0xa5, sizeof(out)); saved = out;
    assert(recovery_run(&out) == -1 && !memcmp(&out, &saved, sizeof(out)));
    assert(recovery_pm.phase == 3 && recovery_lease.state == RPI5_PCIE_WDOG_QUARANTINED);
    assert(fake.writes == expected_writes && fake.writes <= 1);
    unsigned calls = fake.counter_calls+fake.route_calls+fake.count_calls+fake.writes+fake.records;
    assert(recovery_run(&out) == -1 && !memcmp(&out, &saved, sizeof(out)));
    assert(calls == fake.counter_calls+fake.route_calls+fake.count_calls+fake.writes+fake.records);
}
int main(void)
{
    const uint64_t frequencies[] = {1000000, 54000000, 1000000000};
    for (unsigned i = 0; i < 3; i++) {
        reset(frequencies[i]); fake.reenter = 1;
        struct rpi5_recovery_observation out;
        assert(!recovery_run(&out) && recovery_pm.phase == 2);
        assert(fake.writes == 1 && fake.orders == 1 && fake.records == 2);
        assert(fake.route_calls == 3 && fake.count_calls == 3 && recovery_lease.callbacks == 12);
        assert(out.frequency == frequencies[i] && out.checks == 1 && out.route == 0x20);
        assert(out.waited_ticks >= (frequencies[i]+499)/500 && out.waited_ticks <= frequencies[i]);
        assert(out.watchdog.deadline-out.watchdog.start == frequencies[i]*12);
        assert(out.final_countdown < out.watchdog.armed_countdown);
        assert(!memcmp(&out, &fake.recorded[1], sizeof(out)));
        assert(recovery_run(&out) == -1 && fake.writes == 1);
    }
    const uint64_t invalid_frequency[] = {0, 999999, 1000000001, UINT64_MAX};
    for (unsigned i = 0; i < 4; i++) {
        reset(invalid_frequency[i]); struct rpi5_recovery_observation out;
        assert(recovery_run(&out) == -1 && !fake.counter_calls && !fake.writes && !recovery_pm.phase);
    }
    reset(1000000); assert(recovery_run(NULL) == -1 && !fake.counter_calls && !recovery_pm.phase);
    for (unsigned at = 1; at <= 3; at++) for (unsigned variant = 0; variant < 3; variant++) {
        reset(1000000); fake.bad_route_at = at;
        fake.bad_route = (uint32_t[]){0, 0x10, UINT32_MAX}[variant]; refused(at == 1 ? 0 : 1);
    }
    const uint32_t invalid_prior[] = {0, 2u << 16, UINT32_MAX};
    for (unsigned i = 0; i < 3; i++) {
        reset(1000000); fake.bad_count_at = 1; fake.bad_count = invalid_prior[i]; refused(0);
    }
    const uint32_t invalid_armed[] = {0, (14u << 16)-1, (15u << 16)+1, UINT32_MAX};
    for (unsigned i = 0; i < 4; i++) {
        reset(1000000); fake.bad_count_at = 2; fake.bad_count = invalid_armed[i]; refused(1);
    }
    const uint32_t invalid_final[] = {0, 2u << 16, (15u << 16)+1, UINT32_MAX};
    for (unsigned i = 0; i < 4; i++) {
        reset(1000000); fake.bad_count_at = 3; fake.bad_count = invalid_final[i]; refused(1);
    }
    reset(1000000); fake.stall_count = 1; refused(1);
    reset(1000000); fake.stopped = 1; refused(1);
    assert(fake.counter_calls == 1000004); /* Finite stopped-counter wait. */
    for (unsigned at = 2; at <= 9; at++) {
        reset(1000000); fake.bad_counter_at = at; fake.bad_counter = 0; refused(1);
    }
    reset(1000000); fake.bad_counter_at = 1; fake.bad_counter = UINT64_MAX-11000000; refused(0);
    reset(1000000); fake.bad_counter_at = 2; fake.bad_counter = 3000000; refused(1);
    reset(1000000); fake.bad_counter_at = 7; fake.bad_counter = 3000000; refused(1);
    reset(1000000); fake.bad_counter_at = 8; fake.bad_counter = 13001000; refused(1);
    reset(1000000); fake.bad_counter_at = 9; fake.bad_counter = 13001000; refused(1);
    for (unsigned phase = 1; phase <= 2; phase++) {
        reset(1000000); fake.record_fail = phase; refused(1);
    }
    reset(1000000);
    uint32_t count; uint64_t counter;
    assert(recovery_write(&recovery_pm, 0x5a0f0000) == -1);
    recovery_pm.phase = 1;
    assert(recovery_write(&recovery_pm, 0x5a000000) == -1);
    assert(recovery_write(NULL, 0x5a0f0000) == -1 && !fake.writes);
    assert(!recovery_write(&recovery_pm, 0x5a0f0000));
    assert(recovery_write(&recovery_pm, 0x5a0f0000) == -1 && fake.writes == 1);
    assert(recovery_read_route(NULL, &count) == -1 && recovery_read_route(&recovery_pm, NULL) == -1);
    assert(recovery_read_count(NULL, &count) == -1 && recovery_read_count(&recovery_pm, NULL) == -1);
    assert(recovery_counter(NULL, &counter) == -1 && recovery_counter(&recovery_pm, NULL) == -1);
    assert(recovery_order(NULL) == -1);
    puts("recovery protocol: real lease/provider, one write, bounded wait, failure/reentry/output checks passed");
    return 0;
}
