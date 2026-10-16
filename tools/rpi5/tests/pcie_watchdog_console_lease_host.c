/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_watchdog_console_lease.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

struct model {
    uint64_t counter;
    uint32_t route, countdown;
    unsigned active, terminal_calls, route_calls, countdown_calls,
        counter_calls;
};

static int terminal_active(void *opaque)
{
    struct model *model = opaque;
    model->terminal_calls++;
    return model->active;
}

static int read_route(void *opaque, uint32_t *output)
{
    struct model *model = opaque;
    model->route_calls++;
    *output = model->route;
    return 0;
}

static int read_countdown(void *opaque, uint32_t *output)
{
    struct model *model = opaque;
    model->countdown_calls++;
    *output = model->countdown;
    return 0;
}

static int counter(void *opaque, uint64_t *output)
{
    struct model *model = opaque;
    model->counter_calls++;
    *output = model->counter++;
    return 0;
}

static struct rpi5_pcie_watchdog_console_io io(struct model *model)
{
    return (struct rpi5_pcie_watchdog_console_io){
        model, terminal_active, read_route, read_countdown, counter,
    };
}

static struct model good_model(void)
{
    return (struct model){
        .counter = 100,
        .route = 0x20,
        .countdown = 14u << 16,
        .active = 1,
    };
}

int main(void)
{
    struct model model = good_model();
    struct rpi5_pcie_watchdog_console_io callbacks = io(&model);
    struct rpi5_pcie_watchdog_console_lease lease = {0};
    struct rpi5_pcie_watchdog_console_observation observation = {0};
    assert(!rpi5_pcie_watchdog_console_init(&lease, &callbacks, 1000));
    assert(!rpi5_pcie_watchdog_console_begin(&lease, &observation));
    assert(observation.start == 100 && observation.sampled_counter == 101 &&
        observation.countdown == (14u << 16));
    assert(lease.state == RPI5_PCIE_CONSOLE_WDOG_ACTIVE &&
        lease.callbacks == 6);

    /* The independent terminal service may reload between checks. */
    model.countdown = 3u << 16;
    assert(!rpi5_pcie_watchdog_console_check(&lease));
    model.countdown = 15u << 16;
    assert(!rpi5_pcie_watchdog_console_check(&lease));
    assert(lease.checks == 2 && lease.state == RPI5_PCIE_CONSOLE_WDOG_ACTIVE);

    /* Loss of terminal service is permanent and cannot be retried. */
    model.active = 0;
    assert(rpi5_pcie_watchdog_console_check(&lease) == -1);
    assert(lease.state == RPI5_PCIE_CONSOLE_WDOG_QUARANTINED);
    assert(rpi5_pcie_watchdog_console_check(&lease) == -1);

    /* Fail closed on bad route, low margin, excessive countdown and clock. */
    for (unsigned fault = 0; fault < 4; fault++) {
        model = good_model();
        callbacks = io(&model);
        memset(&lease, 0, sizeof lease);
        memset(&observation, 0xa5, sizeof observation);
        assert(!rpi5_pcie_watchdog_console_init(&lease, &callbacks, 1000));
        if (fault == 0) model.route = 0;
        if (fault == 1) model.countdown = 2u << 16;
        if (fault == 2) model.countdown = 16u << 16;
        if (fault == 3) model.counter = UINT64_MAX;
        assert(rpi5_pcie_watchdog_console_begin(&lease, &observation) == -1);
        assert(lease.state == RPI5_PCIE_CONSOLE_WDOG_QUARANTINED);
        const unsigned char *bytes = (const unsigned char *)&observation;
        for (size_t index = 0; index < sizeof observation; index++) {
            assert(bytes[index] == 0xa5);
        }
    }

    puts("PCIE_WATCHDOG_CONSOLE_LEASE_PASS OBSERVE_ONLY SERVICE_RELOAD_ALLOWED");
    return 0;
}
