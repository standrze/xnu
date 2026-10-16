/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_watchdog_lease.h"
#include "pcie_watchdog_gate.h"
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>

struct model {
    struct rpi5_pcie_watchdog_lease lease;
    uint32_t route, count, written, writes, calls, fail_at;
    uint64_t counter, step;
    int reenter;
    unsigned corrupt_at, corrupt_kind;
    uint64_t corrupt_value;
};
static int callback(struct model *m)
{
    m->calls++;
    if (m->calls == m->corrupt_at) {
        if (m->corrupt_kind == 1) m->route = (uint32_t)m->corrupt_value;
        if (m->corrupt_kind == 2) m->count = (uint32_t)m->corrupt_value;
        if (m->corrupt_kind == 3) m->counter = m->corrupt_value;
    }
    if (m->reenter) {
        struct rpi5_pcie_watchdog_observation out;
        assert(rpi5_pcie_watchdog_begin(&m->lease, &out) == -1);
        assert(rpi5_pcie_watchdog_check(&m->lease) == -1);
    }
    return m->calls == m->fail_at ? -1 : 0;
}
static int route(void *context, uint32_t *out)
{
    struct model *m = context;
    if (callback(m)) return -1;
    *out = m->route;
    return 0;
}
static int count(void *context, uint32_t *out)
{
    struct model *m = context;
    if (callback(m)) return -1;
    *out = m->count;
    return 0;
}
static int write_count(void *context, uint32_t value)
{
    struct model *m = context;
    /* A returned failure may still leave the physical write visible. */
    m->written = value; m->count = value & 0xfffff; m->writes++;
    return callback(m);
}
static int order(void *context) { return callback(context); }
static int counter(void *context, uint64_t *out)
{
    struct model *m = context;
    if (callback(m)) return -1;
    *out = m->counter; m->counter += m->step;
    return 0;
}
static void prepare(struct model *m)
{
    memset(m, 0, sizeof(*m));
    m->route = 0x20; m->count = 10u << 16;
    m->counter = 1000000; m->step = 1;
    struct rpi5_pcie_watchdog_io io = {m, route, count, write_count, order, counter};
    assert(!rpi5_pcie_watchdog_init(&m->lease, &io, 1000000));
    assert(!m->calls && m->lease.state == RPI5_PCIE_WDOG_READY);
}
static void reject_begin(struct model *m)
{
    struct rpi5_pcie_watchdog_observation out, before;
    memset(&before, 0xa5, sizeof(before)); out = before;
    assert(rpi5_pcie_watchdog_begin(&m->lease, &out) == -1);
    assert(!memcmp(&out, &before, sizeof(out)));
    assert(m->lease.state == RPI5_PCIE_WDOG_QUARANTINED);
    unsigned calls = m->calls, writes = m->writes;
    assert(rpi5_pcie_watchdog_begin(&m->lease, &out) == -1);
    assert(rpi5_pcie_watchdog_check(&m->lease) == -1);
    assert(m->calls == calls && m->writes == writes); /* No retry or cleanup. */
}
static void arm(struct model *m)
{
    struct rpi5_pcie_watchdog_observation out;
    assert(!rpi5_pcie_watchdog_begin(&m->lease, &out));
    assert(m->calls == 8 && m->lease.callbacks == 8);
    assert(m->writes == 1 && m->written == 0x5a0f0000);
    assert(out.start == 1000000 && out.deadline == 13000000 && out.armed_countdown == (15u << 16));
    assert(m->lease.state == RPI5_PCIE_WDOG_ARMED);
}
static void reject_check(struct model *m)
{
    assert(rpi5_pcie_watchdog_check(&m->lease) == -1);
    assert(m->lease.state == RPI5_PCIE_WDOG_QUARANTINED && m->writes == 1);
    unsigned calls = m->calls;
    assert(rpi5_pcie_watchdog_check(&m->lease) == -1 && m->calls == calls);
}

static struct rpi5_pcie_watchdog_gate gate;
static int identity, other_identity;
static pthread_mutex_t rendezvous = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t condition = PTHREAD_COND_INITIALIZER;
static int entered, release_service;
static void *service_thread(void *unused)
{
    (void)unused;
    assert(rpi5_pcie_watchdog_gate_service(&gate));
    assert(!rpi5_pcie_watchdog_gate_service(&gate)); /* Same-thread recursion. */
    pthread_mutex_lock(&rendezvous);
    entered = 1; pthread_cond_signal(&condition);
    while (!release_service) pthread_cond_wait(&condition, &rendezvous);
    pthread_mutex_unlock(&rendezvous);
    rpi5_pcie_watchdog_gate_leave(&gate);
    return NULL;
}
static void *post_claim_thread(void *unused)
{
    (void)unused;
    for (unsigned i = 0; i < 10000; i++) {
        assert(!rpi5_pcie_watchdog_gate_service(&gate));
        assert(!rpi5_pcie_watchdog_gate_claim(&gate, &other_identity));
        assert(!rpi5_pcie_watchdog_gate_owner(&gate, &other_identity));
    }
    return NULL;
}
int main(void)
{
    struct model m;
    struct rpi5_pcie_watchdog_observation out;
    prepare(&m); arm(&m);
    assert(!rpi5_pcie_watchdog_check(&m.lease));
    assert(m.calls == 12 && m.writes == 1 && m.lease.checks == 1);
    m.count--; m.counter = m.lease.start + 1000;
    assert(!rpi5_pcie_watchdog_check(&m.lease));
    assert(m.calls == 16 && m.writes == 1);
    /* Exact check budget remains finite even with an otherwise stalled model. */
    prepare(&m); m.step = 0; arm(&m);
    for (unsigned i = 0; i < 65536; i++) assert(!rpi5_pcie_watchdog_check(&m.lease));
    unsigned calls = m.calls; reject_check(&m); assert(m.calls == calls);
    for (unsigned fail = 1; fail <= 8; fail++) {
        prepare(&m); m.fail_at = fail; reject_begin(&m);
        assert(m.calls == fail);
        if (fail >= 4) assert(m.writes == 1); /* Never roll back failed writes. */
    }
    for (unsigned fail = 9; fail <= 12; fail++) {
        prepare(&m); arm(&m); m.fail_at = fail; reject_check(&m); assert(m.calls == fail);
    }
    prepare(&m); m.corrupt_at = 6; m.corrupt_kind = 1; m.corrupt_value = 0x30;
    reject_begin(&m); assert(m.calls == 6 && m.writes == 1);
    uint32_t bad_armed[] = {0, (14u << 16)-1, (15u << 16)+1, UINT32_MAX};
    for (unsigned i = 0; i < sizeof(bad_armed)/sizeof(bad_armed[0]); i++) {
        prepare(&m); m.corrupt_at = 7; m.corrupt_kind = 2; m.corrupt_value = bad_armed[i];
        reject_begin(&m); assert(m.calls == 7 && m.writes == 1);
    }
    prepare(&m); m.corrupt_at = 8; m.corrupt_kind = 3; m.corrupt_value = 999999;
    reject_begin(&m); assert(m.calls == 8 && m.writes == 1);
    prepare(&m); m.reenter = 1; arm(&m); assert(!rpi5_pcie_watchdog_check(&m.lease));
    uint32_t invalid_routes[] = {0, 0x10, 0x30, UINT32_MAX};
    for (unsigned i = 0; i < sizeof(invalid_routes)/sizeof(invalid_routes[0]); i++) {
        prepare(&m); m.route = invalid_routes[i]; reject_begin(&m); assert(!m.writes);
        prepare(&m); arm(&m); m.route = invalid_routes[i]; reject_check(&m);
    }
    uint32_t invalid_counts[] = {0, 1, 2u << 16, UINT32_MAX};
    for (unsigned i = 0; i < sizeof(invalid_counts)/sizeof(invalid_counts[0]); i++) {
        prepare(&m); m.count = invalid_counts[i]; reject_begin(&m); assert(!m.writes);
        prepare(&m); arm(&m); m.count = invalid_counts[i]; reject_check(&m);
    }
    prepare(&m); m.counter = UINT64_MAX - 11999999; reject_begin(&m); assert(!m.writes);
    prepare(&m); m.step = 1000001; reject_begin(&m); assert(m.writes == 1);
    prepare(&m); arm(&m); m.counter = m.lease.last_counter - 1; reject_check(&m);
    prepare(&m); arm(&m); m.counter = m.lease.deadline; reject_check(&m);
    prepare(&m); arm(&m); m.counter = m.lease.deadline - 1; reject_check(&m); /* Expires during callback. */
    prepare(&m); arm(&m); m.corrupt_at = 12; m.corrupt_kind = 3; m.corrupt_value = 0;
    reject_check(&m); /* Counter regresses during a returned callback. */
    prepare(&m); arm(&m); m.counter = m.lease.start + 1000; reject_check(&m); /* Stalled physical countdown. */
    prepare(&m); arm(&m); m.count--; assert(!rpi5_pcie_watchdog_check(&m.lease));
    m.count++; reject_check(&m); /* A foreign reload is not lease continuation. */
    prepare(&m);
    struct rpi5_pcie_watchdog_lease copy = m.lease;
    assert(rpi5_pcie_watchdog_init(&m.lease, &m.lease.io, 1000000) == -1);
    assert(!memcmp(&copy, &m.lease, sizeof(copy)));
    assert(rpi5_pcie_watchdog_begin(NULL, &out) == -1);
    assert(rpi5_pcie_watchdog_check(NULL) == -1);
    struct rpi5_pcie_watchdog_lease empty = {};
    struct rpi5_pcie_watchdog_io io = m.lease.io;
    for (unsigned i = 0; i < 5; i++) {
        struct rpi5_pcie_watchdog_io bad = io;
        if (i == 0) bad.read_route = NULL;
        if (i == 1) bad.read_countdown = NULL;
        if (i == 2) bad.write_countdown = NULL;
        if (i == 3) bad.order = NULL;
        if (i == 4) bad.counter = NULL;
        assert(rpi5_pcie_watchdog_init(&empty, &bad, 1000000) == -1);
        assert(empty.state == RPI5_PCIE_WDOG_EMPTY);
    }
    assert(rpi5_pcie_watchdog_begin(&m.lease, NULL) == -1);
    assert(m.lease.state == RPI5_PCIE_WDOG_READY);
    assert(rpi5_pcie_watchdog_init(&empty, &m.lease.io, 0) == -1);
    assert(rpi5_pcie_watchdog_init(&empty, &m.lease.io, UINT64_MAX/12+1) == -1);
    assert(empty.state == RPI5_PCIE_WDOG_EMPTY);

    assert(!rpi5_pcie_watchdog_gate_claim(&gate, NULL));
    assert(!rpi5_pcie_watchdog_gate_owner(&gate, &identity));
    pthread_t thread;
    assert(!pthread_create(&thread, NULL, service_thread, NULL));
    pthread_mutex_lock(&rendezvous);
    while (!entered) pthread_cond_wait(&condition, &rendezvous);
    assert(!rpi5_pcie_watchdog_gate_claim(&gate, &identity)); /* In-flight service owns lock. */
    assert(!__atomic_load_n(&gate.owner, __ATOMIC_ACQUIRE));
    release_service = 1; pthread_cond_signal(&condition); pthread_mutex_unlock(&rendezvous);
    assert(!pthread_join(thread, NULL));
    assert(rpi5_pcie_watchdog_gate_claim(&gate, &identity));
    assert(!rpi5_pcie_watchdog_gate_service(&gate));
    assert(!rpi5_pcie_watchdog_gate_owner(&gate, &identity)); /* Owner recursion is nonblocking. */
    rpi5_pcie_watchdog_gate_leave(&gate);
    assert(rpi5_pcie_watchdog_gate_owner(&gate, &identity));
    rpi5_pcie_watchdog_gate_leave(&gate);
    pthread_t workers[4];
    for (unsigned i = 0; i < 4; i++) assert(!pthread_create(&workers[i], NULL, post_claim_thread, NULL));
    for (unsigned i = 0; i < 4; i++) assert(!pthread_join(workers[i], NULL));
    assert(gate.owner == &identity); /* Even a failed physical begin cannot clear this gate. */
    puts("PCIE_WATCHDOG_HOST_PASS FAILURE_POSITIONS=12 CHECK_LIMIT=65536 THREAD_ATTEMPTS=120000 NO_MMIO=1");
    return 0;
}
