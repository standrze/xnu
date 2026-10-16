/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_network_adapter.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum event {
	EV_ATTACH = 1, EV_REGISTER, EV_LINK_DOWN, EV_ENABLE, EV_LINK_UP,
	EV_OUTPUT_START, EV_OUTPUT_STOP, EV_OUTPUT_FLUSH, EV_OUTPUT_SERVICE,
	EV_TX, EV_FREE, EV_RX_QUEUE, EV_RX_DIRECT, EV_FLUSH, EV_DISABLE,
	EV_CLEAR, EV_DETACH
};

struct model {
	struct rpi5_gem_network_adapter *adapter;
	unsigned events[128], event_count;
	unsigned attach_count, register_count, detach_count, link_count;
	unsigned enable_count, disable_count, tx_count, free_count;
	unsigned input_count, flush_count, clear_count;
	unsigned output_start_count, output_stop_count, output_flush_count;
	unsigned output_service_count;
	bool attach_ok, register_ok, link_ok, enable_ok, disable_ok;
	bool output_start_ok;
	bool complete_on_disable;
	enum rpi5_gem_net_tx_result tx_result;
	void *accepted_packet;
};

static void ev(struct model *m, enum event value)
{ assert(m->event_count < 128); m->events[m->event_count++] = value; }
static bool attach_interface(void *c, void **token)
{
	struct model *m = c; ev(m, EV_ATTACH); m->attach_count++;
	if (!m->attach_ok) return false;
	*token = (void *)(uintptr_t)0x1234; return true;
}
static bool register_interface(void *c, void *token)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234);
	ev(m, EV_REGISTER); m->register_count++; return m->register_ok;
}
static void detach_interface(void *c, void *token, bool sync)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234 && sync);
	ev(m, EV_DETACH); m->detach_count++;
}
static bool publish_link(void *c, void *token, bool valid, bool active,
    uint64_t speed)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234 && valid);
	assert((active && speed != 0) || (!active && speed == 0));
	ev(m, active ? EV_LINK_UP : EV_LINK_DOWN); m->link_count++;
	return m->link_ok;
}
static void free_packet(void *c, void *packet)
{
	struct model *m = c; assert(packet != NULL); ev(m, EV_FREE); m->free_count++;
}
static void input_packet(void *c, void *token, void *packet, uint32_t bytes,
    bool queue)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234);
	assert(packet != NULL && bytes >= 60 && bytes <= 1514);
	ev(m, queue ? EV_RX_QUEUE : EV_RX_DIRECT); m->input_count++;
}
static uint32_t flush_input(void *c, void *token)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234);
	ev(m, EV_FLUSH); m->flush_count++; return 3;
}
static uint32_t clear_input(void *c, void *token)
{
	struct model *m = c; assert(token == (void *)(uintptr_t)0x1234);
	ev(m, EV_CLEAR); m->clear_count++; return 2;
}
static bool start_output(void *c)
{
	struct model *m = c; ev(m, EV_OUTPUT_START); m->output_start_count++;
	return m->output_start_ok;
}
static void stop_output(void *c)
{ struct model *m = c; ev(m, EV_OUTPUT_STOP); m->output_stop_count++; }
static uint32_t flush_output(void *c)
{
	struct model *m = c; ev(m, EV_OUTPUT_FLUSH); m->output_flush_count++;
	return 4;
}
static void service_output(void *c)
{ struct model *m = c; ev(m, EV_OUTPUT_SERVICE); m->output_service_count++; }
static bool enable_io(void *c)
{ struct model *m = c; ev(m, EV_ENABLE); m->enable_count++; return m->enable_ok; }
static bool disable_io(void *c)
{
	struct model *m = c; ev(m, EV_DISABLE); m->disable_count++;
	if (m->complete_on_disable && m->accepted_packet != NULL) {
		void *packet = m->accepted_packet; m->accepted_packet = NULL;
		assert(rpi5_gem_network_adapter_tx_complete(m->adapter, packet));
	}
	return m->disable_ok;
}
static enum rpi5_gem_net_tx_result submit_tx(void *c, void *packet,
    uint32_t bytes)
{
	struct model *m = c; assert(packet != NULL && bytes >= 14 && bytes <= 1514);
	ev(m, EV_TX); m->tx_count++;
	if (m->tx_result == RPI5_GEM_NET_TX_ACCEPTED) m->accepted_packet = packet;
	return m->tx_result;
}
static const struct rpi5_gem_net_ops ops = {
	attach_interface, register_interface, detach_interface, publish_link,
	free_packet, input_packet, flush_input, clear_input, start_output,
	stop_output, flush_output, service_output, enable_io, disable_io, submit_tx
};

static void defaults(struct model *m)
{
	memset(m, 0, sizeof(*m));
	m->attach_ok = m->register_ok = m->link_ok = true;
	m->enable_ok = m->disable_ok = m->output_start_ok = true;
	m->tx_result = RPI5_GEM_NET_TX_ACCEPTED;
}

static struct rpi5_gem_net_acceptance accepted(void)
{
	struct rpi5_gem_net_acceptance a = {
		RPI5_GEM_NET_ACCEPTANCE_VERSION, RPI5_GEM_NET_REQUIRED,
		UINT64_C(0xfeed000000000001)
	};
	return a;
}

static void test_gate(void)
{
	struct rpi5_gem_network_adapter a;
	struct model m; defaults(&m); m.adapter = &a;
	const uint8_t mac[6] = { 0x02, 0, 0, 0, 0, 1 };
	struct rpi5_gem_net_acceptance proof = accepted();
	rpi5_gem_network_adapter_init(&a);
	assert(a.state == RPI5_GEM_NET_DORMANT && a.ops == NULL);
	for (unsigned bit = 0; bit < 8; bit++) {
		proof.accepted = RPI5_GEM_NET_REQUIRED & ~(1u << bit);
		assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
		assert(a.state == RPI5_GEM_NET_DORMANT && m.event_count == 0);
	}
	proof = accepted(); proof.version++;
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	proof = accepted(); proof.same_boot_cookie = 0;
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	uint8_t bad[6] = { 1, 0, 0, 0, 0, 1 };
	proof = accepted();
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, bad));
	memset(bad, 0, sizeof bad);
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, bad));
	struct rpi5_gem_net_ops missing;
#define MISSING(field) do { \
	missing = ops; missing.field = NULL; \
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &missing, &m, mac)); \
} while (0)
	MISSING(attach_interface); MISSING(register_interface);
	MISSING(detach_interface); MISSING(publish_link); MISSING(free_packet);
	MISSING(input_packet); MISSING(flush_input); MISSING(clear_input);
	MISSING(start_output); MISSING(stop_output); MISSING(flush_output);
	MISSING(service_output); MISSING(enable_io); MISSING(disable_io);
	MISSING(submit_tx);
#undef MISSING
	assert(rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	assert(a.state == RPI5_GEM_NET_QUALIFIED && !memcmp(a.mac, mac, 6));
	assert(!rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
}

static void test_register_failures(void)
{
	const uint8_t mac[6] = { 0x02, 1, 2, 3, 4, 5 };
	struct rpi5_gem_net_acceptance proof = accepted();
	struct rpi5_gem_network_adapter a; struct model m;
	defaults(&m); m.adapter = &a; rpi5_gem_network_adapter_init(&a);
	assert(rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	m.attach_ok = false;
	assert(!rpi5_gem_network_adapter_register(&a));
	assert(m.attach_count == 1 && m.detach_count == 0);
	m.attach_ok = true; m.register_ok = false;
	assert(!rpi5_gem_network_adapter_register(&a));
	assert(m.detach_count == 1 && a.state == RPI5_GEM_NET_QUALIFIED);
	m.register_ok = true; m.link_ok = false;
	assert(!rpi5_gem_network_adapter_register(&a));
	assert(m.detach_count == 2 && a.interface_token == NULL);
	m.link_ok = true;
	assert(rpi5_gem_network_adapter_register(&a));
	assert(a.state == RPI5_GEM_NET_REGISTERED && !a.link_active);
	assert(m.events[m.event_count - 2] == EV_LINK_DOWN);
	assert(m.events[m.event_count - 1] == EV_REGISTER);
	assert(!rpi5_gem_network_adapter_register(&a));
}

static void test_packets_and_teardown(void)
{
	const uint8_t mac[6] = { 0x02, 1, 2, 3, 4, 5 };
	struct rpi5_gem_net_acceptance proof = accepted();
	struct rpi5_gem_network_adapter a; struct model m;
	int p1, p2, p3, p4, p5, p6, p7;
	defaults(&m); m.adapter = &a; rpi5_gem_network_adapter_init(&a);
	assert(rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	assert(rpi5_gem_network_adapter_register(&a));
	m.enable_ok = false; assert(!rpi5_gem_network_adapter_enable(&a));
	m.enable_ok = true; m.output_start_ok = false;
	assert(!rpi5_gem_network_adapter_enable(&a));
	assert(a.state == RPI5_GEM_NET_REGISTERED && m.disable_count == 1);
	m.output_start_ok = true; assert(rpi5_gem_network_adapter_enable(&a));
	assert(a.state == RPI5_GEM_NET_ENABLED);
	assert(rpi5_gem_network_adapter_output(&a, &p1, 60) ==
	    RPI5_GEM_NET_OUTPUT_DROPPED && m.free_count == 1);
	assert(!rpi5_gem_network_adapter_input(&a, &p2, 60, true));
	assert(m.free_count == 2);
	assert(!rpi5_gem_network_adapter_set_link(&a, true, 0));
	assert(rpi5_gem_network_adapter_set_link(&a, true, UINT64_C(1000000000)));
	a.tx_outstanding = UINT32_MAX;
	unsigned tx_before = m.tx_count;
	assert(rpi5_gem_network_adapter_output(&a, &p1, 60) ==
	    RPI5_GEM_NET_OUTPUT_STALL && m.tx_count == tx_before);
	a.tx_outstanding = 0;
	m.tx_result = RPI5_GEM_NET_TX_RETRY;
	assert(rpi5_gem_network_adapter_output(&a, &p1, 60) ==
	    RPI5_GEM_NET_OUTPUT_STALL && m.free_count == 2);
	m.tx_result = RPI5_GEM_NET_TX_DROP;
	assert(rpi5_gem_network_adapter_output(&a, &p2, 60) ==
	    RPI5_GEM_NET_OUTPUT_DROPPED && m.free_count == 3);
	m.tx_result = RPI5_GEM_NET_TX_ACCEPTED;
	assert(rpi5_gem_network_adapter_output(&a, &p3, 1514) ==
	    RPI5_GEM_NET_OUTPUT_SUCCESS && a.tx_outstanding == 1);
	assert(rpi5_gem_network_adapter_tx_complete(&a, &p3));
	assert(a.tx_outstanding == 0 && m.free_count == 4);
	assert(m.output_service_count == 1);
	assert(!rpi5_gem_network_adapter_tx_complete(&a, &p3));
	assert(rpi5_gem_network_adapter_input(&a, &p4, 60, true));
	assert(rpi5_gem_network_adapter_input(&a, &p5, 1514, true));
	assert(rpi5_gem_network_adapter_input(&a, &p6, 60, false));
	assert(m.input_count == 3 && rpi5_gem_network_adapter_flush_input(&a) == 3);
	assert(rpi5_gem_network_adapter_input(&a, &p4, 60, true));
	unsigned clears = m.clear_count;
	assert(rpi5_gem_network_adapter_set_link(&a, false, 0));
	assert(m.clear_count == clears + 1);
	assert(rpi5_gem_network_adapter_flush_input(&a) == 0);
	assert(!rpi5_gem_network_adapter_input(&a, &p4, 60, true));
	assert(m.free_count == 5);
	assert(rpi5_gem_network_adapter_set_link(&a, true, UINT64_C(1000000000)));
	assert(!rpi5_gem_network_adapter_input(&a, &p7, 1515, true));
	assert(m.free_count == 6);
	assert(!rpi5_gem_network_adapter_input(&a, &p7, 59, true));
	assert(m.free_count == 7);
	assert(rpi5_gem_network_adapter_output(&a, &p7, 13) ==
	    RPI5_GEM_NET_OUTPUT_DROPPED && m.free_count == 8);
	assert(rpi5_gem_network_adapter_output(&a, &p7, 1515) ==
	    RPI5_GEM_NET_OUTPUT_DROPPED && m.free_count == 9);

	/* Accepted TX is completed while the backend is quiescing. */
	assert(rpi5_gem_network_adapter_output(&a, &p7, 60) ==
	    RPI5_GEM_NET_OUTPUT_SUCCESS && a.tx_outstanding == 1);
	m.complete_on_disable = true;
	assert(rpi5_gem_network_adapter_disable(&a));
	assert(a.state == RPI5_GEM_NET_REGISTERED && a.tx_outstanding == 0);
	assert(m.output_stop_count == 2 && m.output_flush_count == 2);
	assert(m.events[m.event_count - 2] == EV_CLEAR);
	assert(m.events[m.event_count - 1] == EV_LINK_DOWN);
	assert(rpi5_gem_network_adapter_teardown(&a));
	assert(a.state == RPI5_GEM_NET_QUALIFIED && a.interface_token == NULL);
	assert(m.events[m.event_count - 2] == EV_CLEAR);
	assert(m.events[m.event_count - 1] == EV_DETACH);
}

static void test_disable_fail_closed(void)
{
	const uint8_t mac[6] = { 0x02, 1, 2, 3, 4, 5 };
	struct rpi5_gem_net_acceptance proof = accepted();
	struct rpi5_gem_network_adapter a; struct model m; int packet;
	defaults(&m); m.adapter = &a; rpi5_gem_network_adapter_init(&a);
	assert(rpi5_gem_network_adapter_qualify(&a, &proof, &ops, &m, mac));
	assert(rpi5_gem_network_adapter_register(&a));
	assert(rpi5_gem_network_adapter_enable(&a));
	assert(rpi5_gem_network_adapter_set_link(&a, true, UINT64_C(1000000000)));
	assert(rpi5_gem_network_adapter_output(&a, &packet, 60) ==
	    RPI5_GEM_NET_OUTPUT_SUCCESS);
	assert(!rpi5_gem_network_adapter_disable(&a));
	assert(a.state == RPI5_GEM_NET_STOPPING && a.interface_token != NULL);
	assert(m.output_stop_count == 1 && m.output_flush_count == 1);
	assert(!rpi5_gem_network_adapter_teardown(&a) && m.detach_count == 0);
	assert(rpi5_gem_network_adapter_tx_complete(&a, &packet));
	m.disable_ok = false;
	assert(!rpi5_gem_network_adapter_disable(&a));
	assert(a.state == RPI5_GEM_NET_STOPPING && m.detach_count == 0);
	m.disable_ok = true;
	assert(rpi5_gem_network_adapter_disable(&a));
	assert(rpi5_gem_network_adapter_teardown(&a));
}

int main(void)
{
	test_gate();
	test_register_failures();
	test_packets_and_teardown();
	test_disable_fail_closed();
	puts("GEM_NETWORK_ADAPTER_PASS DEFAULT_OFF OWNERSHIP_EXACT NO_HARDWARE");
	return 0;
}
