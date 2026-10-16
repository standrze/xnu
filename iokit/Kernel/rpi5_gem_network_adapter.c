/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_network_adapter.h"

static bool
valid_mac(const uint8_t mac[6])
{
	uint8_t any = 0;

	if (mac == NULL || (mac[0] & 1u) != 0) {
		return false;
	}
	for (unsigned i = 0; i < 6; i++) {
		any |= mac[i];
	}
	return any != 0;
}

static bool
valid_ops(const struct rpi5_gem_net_ops *ops)
{
	return ops != NULL && ops->attach_interface != NULL &&
	    ops->register_interface != NULL && ops->detach_interface != NULL &&
	    ops->publish_link != NULL && ops->free_packet != NULL &&
	    ops->input_packet != NULL && ops->flush_input != NULL &&
	    ops->clear_input != NULL && ops->start_output != NULL &&
	    ops->stop_output != NULL && ops->flush_output != NULL &&
	    ops->service_output != NULL && ops->enable_io != NULL &&
	    ops->disable_io != NULL && ops->submit_tx != NULL;
}

void
rpi5_gem_network_adapter_init(struct rpi5_gem_network_adapter *adapter)
{
	if (adapter == NULL) {
		return;
	}
	adapter->ops = NULL;
	adapter->context = NULL;
	adapter->interface_token = NULL;
	adapter->same_boot_cookie = 0;
	adapter->accepted = 0;
	adapter->tx_outstanding = 0;
	for (unsigned i = 0; i < 6; i++) {
		adapter->mac[i] = 0;
	}
	adapter->state = RPI5_GEM_NET_DORMANT;
	adapter->link_active = false;
}

bool
rpi5_gem_network_adapter_qualify(struct rpi5_gem_network_adapter *adapter,
    const struct rpi5_gem_net_acceptance *acceptance,
    const struct rpi5_gem_net_ops *ops, void *context, const uint8_t mac[6])
{
	if (adapter == NULL || acceptance == NULL ||
	    adapter->state != RPI5_GEM_NET_DORMANT ||
	    acceptance->version != RPI5_GEM_NET_ACCEPTANCE_VERSION ||
	    acceptance->accepted != RPI5_GEM_NET_REQUIRED ||
	    acceptance->same_boot_cookie == 0 || !valid_ops(ops) ||
	    !valid_mac(mac)) {
		return false;
	}
	adapter->ops = ops;
	adapter->context = context;
	adapter->same_boot_cookie = acceptance->same_boot_cookie;
	adapter->accepted = acceptance->accepted;
	for (unsigned i = 0; i < 6; i++) {
		adapter->mac[i] = mac[i];
	}
	adapter->state = RPI5_GEM_NET_QUALIFIED;
	return true;
}

bool
rpi5_gem_network_adapter_register(struct rpi5_gem_network_adapter *adapter)
{
	void *token = NULL;

	if (adapter == NULL || adapter->state != RPI5_GEM_NET_QUALIFIED ||
	    adapter->ops == NULL || adapter->interface_token != NULL ||
	    !adapter->ops->attach_interface(adapter->context, &token) ||
	    token == NULL) {
		return false;
	}
	/* Establish a known-down controller state before registerService() can
	 * expose the interface to BSD matching. */
	if (!adapter->ops->publish_link(adapter->context, token,
	    true, false, 0)) {
		adapter->ops->detach_interface(adapter->context, token, true);
		return false;
	}
	if (!adapter->ops->register_interface(adapter->context, token)) {
		adapter->ops->detach_interface(adapter->context, token, true);
		return false;
	}
	adapter->interface_token = token;
	adapter->state = RPI5_GEM_NET_REGISTERED;
	return true;
}

bool
rpi5_gem_network_adapter_enable(struct rpi5_gem_network_adapter *adapter)
{
	if (adapter == NULL || adapter->state != RPI5_GEM_NET_REGISTERED ||
	    adapter->interface_token == NULL || adapter->tx_outstanding != 0 ||
	    !adapter->ops->enable_io(adapter->context)) {
		return false;
	}
	if (!adapter->ops->start_output(adapter->context)) {
		adapter->ops->stop_output(adapter->context);
		(void)adapter->ops->flush_output(adapter->context);
		adapter->state = RPI5_GEM_NET_STOPPING;
		if (adapter->ops->disable_io(adapter->context)) {
			adapter->state = RPI5_GEM_NET_REGISTERED;
		}
		return false;
	}
	adapter->state = RPI5_GEM_NET_ENABLED;
	return true;
}

bool
rpi5_gem_network_adapter_set_link(struct rpi5_gem_network_adapter *adapter,
    bool active, uint64_t bits_per_second)
{
	if (adapter == NULL || adapter->state != RPI5_GEM_NET_ENABLED ||
	    adapter->interface_token == NULL ||
	    (active && bits_per_second == 0)) {
		return false;
	}
	if (!active) {
		/* Queued input is no longer eligible for later delivery once a
		 * link-down transition begins. */
		adapter->link_active = false;
		(void)adapter->ops->clear_input(adapter->context,
		    adapter->interface_token);
	}
	if (!adapter->ops->publish_link(adapter->context,
	    adapter->interface_token, true, active,
	    active ? bits_per_second : 0)) {
		return false;
	}
	adapter->link_active = active;
	return true;
}

enum rpi5_gem_net_output_status
rpi5_gem_network_adapter_output(struct rpi5_gem_network_adapter *adapter,
    void *packet, uint32_t bytes)
{
	if (adapter == NULL || packet == NULL) {
		return RPI5_GEM_NET_OUTPUT_DROPPED;
	}
	if (adapter->ops == NULL || adapter->state != RPI5_GEM_NET_ENABLED ||
	    !adapter->link_active || bytes < RPI5_GEM_NET_HEADER_BYTES ||
	    bytes > RPI5_GEM_NET_MAX_RX_BYTES) {
		if (adapter->ops != NULL && adapter->ops->free_packet != NULL) {
			adapter->ops->free_packet(adapter->context, packet);
		}
		return RPI5_GEM_NET_OUTPUT_DROPPED;
	}
	if (adapter->tx_outstanding == UINT32_MAX) {
		return RPI5_GEM_NET_OUTPUT_STALL;
	}
	switch (adapter->ops->submit_tx(adapter->context, packet, bytes)) {
	case RPI5_GEM_NET_TX_ACCEPTED:
		adapter->tx_outstanding++;
		return RPI5_GEM_NET_OUTPUT_SUCCESS;
	case RPI5_GEM_NET_TX_RETRY:
		return RPI5_GEM_NET_OUTPUT_STALL;
	case RPI5_GEM_NET_TX_DROP:
	default:
		adapter->ops->free_packet(adapter->context, packet);
		return RPI5_GEM_NET_OUTPUT_DROPPED;
	}
}

bool
rpi5_gem_network_adapter_tx_complete(struct rpi5_gem_network_adapter *adapter,
    void *packet)
{
	if (adapter == NULL || packet == NULL || adapter->ops == NULL ||
	    (adapter->state != RPI5_GEM_NET_ENABLED &&
	    adapter->state != RPI5_GEM_NET_STOPPING) ||
	    adapter->tx_outstanding == 0) {
		return false;
	}
	adapter->tx_outstanding--;
	adapter->ops->free_packet(adapter->context, packet);
	if (adapter->state == RPI5_GEM_NET_ENABLED) {
		adapter->ops->service_output(adapter->context);
	}
	return true;
}

bool
rpi5_gem_network_adapter_input(struct rpi5_gem_network_adapter *adapter,
    void *packet, uint32_t bytes, bool queue)
{
	if (adapter == NULL || packet == NULL) {
		return false;
	}
	if (adapter->ops == NULL || adapter->state != RPI5_GEM_NET_ENABLED ||
	    !adapter->link_active || adapter->interface_token == NULL ||
	    bytes < RPI5_GEM_NET_MIN_RX_BYTES ||
	    bytes > RPI5_GEM_NET_MAX_RX_BYTES) {
		if (adapter->ops != NULL && adapter->ops->free_packet != NULL) {
			adapter->ops->free_packet(adapter->context, packet);
		}
		return false;
	}
	adapter->ops->input_packet(adapter->context, adapter->interface_token,
	    packet, bytes, queue);
	return true;
}

uint32_t
rpi5_gem_network_adapter_flush_input(struct rpi5_gem_network_adapter *adapter)
{
	if (adapter == NULL || adapter->ops == NULL ||
	    adapter->state != RPI5_GEM_NET_ENABLED ||
	    !adapter->link_active ||
	    adapter->interface_token == NULL) {
		return 0;
	}
	return adapter->ops->flush_input(adapter->context,
	    adapter->interface_token);
}

bool
rpi5_gem_network_adapter_disable(struct rpi5_gem_network_adapter *adapter)
{
	if (adapter == NULL ||
	    (adapter->state != RPI5_GEM_NET_ENABLED &&
	    adapter->state != RPI5_GEM_NET_STOPPING) ||
	    adapter->ops == NULL) {
		return false;
	}
	if (adapter->state == RPI5_GEM_NET_ENABLED) {
		adapter->ops->stop_output(adapter->context);
		(void)adapter->ops->flush_output(adapter->context);
		adapter->state = RPI5_GEM_NET_STOPPING;
	}
	if (!adapter->ops->disable_io(adapter->context) ||
	    adapter->tx_outstanding != 0) {
		/* Remain STOPPING: registration must not be torn down over live DMA. */
		return false;
	}
	(void)adapter->ops->clear_input(adapter->context,
	    adapter->interface_token);
	if (!adapter->ops->publish_link(adapter->context,
	    adapter->interface_token, true, false, 0)) {
		return false;
	}
	adapter->link_active = false;
	adapter->state = RPI5_GEM_NET_REGISTERED;
	return true;
}

bool
rpi5_gem_network_adapter_teardown(struct rpi5_gem_network_adapter *adapter)
{
	if (adapter == NULL || adapter->ops == NULL ||
	    (adapter->state != RPI5_GEM_NET_REGISTERED &&
	    adapter->state != RPI5_GEM_NET_ENABLED)) {
		return false;
	}
	if (adapter->state == RPI5_GEM_NET_ENABLED &&
	    !rpi5_gem_network_adapter_disable(adapter)) {
		return false;
	}
	if (adapter->state != RPI5_GEM_NET_REGISTERED ||
	    adapter->tx_outstanding != 0) {
		return false;
	}
	(void)adapter->ops->clear_input(adapter->context,
	    adapter->interface_token);
	adapter->ops->detach_interface(adapter->context,
	    adapter->interface_token, true);
	adapter->interface_token = NULL;
	adapter->state = RPI5_GEM_NET_QUALIFIED;
	return true;
}
