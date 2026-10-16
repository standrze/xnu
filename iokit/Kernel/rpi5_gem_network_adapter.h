/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_GEM_NETWORK_ADAPTER_H
#define RPI5_GEM_NETWORK_ADAPTER_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/*
 * Software-only boundary between a future IOEthernetController subclass and
 * the separately qualified BCM2712/RP1 GEM transport.  This file does not
 * register an interface or touch hardware by itself.  Control and packet
 * callbacks must be serialized on the controller work loop.
 *
 * The bridge must remain absent from the production driver catalogue until a
 * same-boot acceptance record supplies every bit in RPI5_GEM_NET_REQUIRED.
 */
enum rpi5_gem_net_acceptance_bits {
	RPI5_GEM_NET_ACCEPT_RAM_ROUTE       = 1u << 0,
	RPI5_GEM_NET_ACCEPT_DESCRIPTOR_RING = 1u << 1,
	RPI5_GEM_NET_ACCEPT_DMA_TX          = 1u << 2,
	RPI5_GEM_NET_ACCEPT_DMA_RX          = 1u << 3,
	RPI5_GEM_NET_ACCEPT_IRQ             = 1u << 4,
	RPI5_GEM_NET_ACCEPT_TX_COMPLETION   = 1u << 5,
	RPI5_GEM_NET_ACCEPT_RX_OWNERSHIP    = 1u << 6,
	RPI5_GEM_NET_ACCEPT_APPLE_FAMILY    = 1u << 7,
	RPI5_GEM_NET_REQUIRED               = 0xffu
};

#define RPI5_GEM_NET_ACCEPTANCE_VERSION 1u
#define RPI5_GEM_NET_ETHERNET_MTU 1500u
#define RPI5_GEM_NET_HEADER_BYTES 14u
#define RPI5_GEM_NET_CRC_BYTES 4u
#define RPI5_GEM_NET_MAX_FRAME_BYTES 1518u
#define RPI5_GEM_NET_MIN_RX_BYTES 60u
#define RPI5_GEM_NET_MAX_RX_BYTES \
	(RPI5_GEM_NET_MAX_FRAME_BYTES - RPI5_GEM_NET_CRC_BYTES)

struct rpi5_gem_net_acceptance {
	uint32_t version;
	uint32_t accepted;
	uint64_t same_boot_cookie;
};

enum rpi5_gem_net_tx_result {
	/* Backend owns the packet until one matching tx_complete(). */
	RPI5_GEM_NET_TX_ACCEPTED = 0,
	/* Backend did not take ownership; Apple output queue must retry it. */
	RPI5_GEM_NET_TX_RETRY = 1,
	/* Backend did not take ownership; adapter consumes and frees it. */
	RPI5_GEM_NET_TX_DROP = 2
};

enum rpi5_gem_net_output_status {
	/* Values intentionally match Apple's IOOutputQueue status/command ABI. */
	RPI5_GEM_NET_OUTPUT_SUCCESS = 0x0000,
	RPI5_GEM_NET_OUTPUT_DROPPED = 0x0001,
	RPI5_GEM_NET_OUTPUT_STALL = 0x0102
};

enum rpi5_gem_net_state {
	RPI5_GEM_NET_DORMANT = 0,
	RPI5_GEM_NET_QUALIFIED,
	RPI5_GEM_NET_REGISTERED,
	RPI5_GEM_NET_ENABLED,
	RPI5_GEM_NET_STOPPING
};

struct rpi5_gem_net_ops {
	/* Family bridge: attachInterface(..., false), registerService(), and
	 * detachInterface(..., true).  The token is an IONetworkInterface*. */
	bool (*attach_interface)(void *context, void **interface_token);
	bool (*register_interface)(void *context, void *interface_token);
	void (*detach_interface)(void *context, void *interface_token, bool sync);

	/* Family bridge: setLinkStatus() and mbuf ownership helpers. */
	bool (*publish_link)(void *context, void *interface_token,
	    bool valid, bool active, uint64_t bits_per_second);
	void (*free_packet)(void *context, void *packet);
	void (*input_packet)(void *context, void *interface_token,
	    void *packet, uint32_t bytes, bool queue);
	uint32_t (*flush_input)(void *context, void *interface_token);
	uint32_t (*clear_input)(void *context, void *interface_token);
	/* IOOutputQueue bridge.  start_output configures capacity and starts the
	 * queue; stop_output synchronously prevents new outputPacket() calls;
	 * flush_output consumes queued mbufs; service_output restarts a stalled
	 * queue after a TX completion frees a descriptor. */
	bool (*start_output)(void *context);
	void (*stop_output)(void *context);
	uint32_t (*flush_output)(void *context);
	void (*service_output)(void *context);

	/* Qualified GEM transport.  enable_io() may enable queues/IRQs only
	 * after registration. disable_io() must quiesce IRQ/DMA and complete or
	 * release every accepted TX packet before returning true. */
	bool (*enable_io)(void *context);
	bool (*disable_io)(void *context);
	enum rpi5_gem_net_tx_result (*submit_tx)(void *context, void *packet,
	    uint32_t bytes);
};

struct rpi5_gem_network_adapter {
	const struct rpi5_gem_net_ops *ops;
	void *context;
	void *interface_token;
	uint64_t same_boot_cookie;
	uint32_t accepted;
	uint32_t tx_outstanding;
	uint8_t mac[6];
	enum rpi5_gem_net_state state;
	bool link_active;
};

void rpi5_gem_network_adapter_init(struct rpi5_gem_network_adapter *adapter);

/* Accepts only the complete, current, same-boot gate and a valid unicast MAC.
 * No callback is invoked on failure. */
bool rpi5_gem_network_adapter_qualify(
	struct rpi5_gem_network_adapter *adapter,
	const struct rpi5_gem_net_acceptance *acceptance,
	const struct rpi5_gem_net_ops *ops, void *context,
	const uint8_t mac[6]);

/* Registration is deliberately separate from qualification.  Failure rolls
 * back any created interface synchronously and leaves the adapter qualified. */
bool rpi5_gem_network_adapter_register(
	struct rpi5_gem_network_adapter *adapter);
bool rpi5_gem_network_adapter_enable(
	struct rpi5_gem_network_adapter *adapter);
bool rpi5_gem_network_adapter_set_link(
	struct rpi5_gem_network_adapter *adapter, bool active,
	uint64_t bits_per_second);

enum rpi5_gem_net_output_status rpi5_gem_network_adapter_output(
	struct rpi5_gem_network_adapter *adapter, void *packet, uint32_t bytes);

/* Exactly one completion is required for each ACCEPTED output.  The qualified
 * backend is responsible for mapping a completion descriptor to its original
 * packet without duplication; ownership then returns to Apple's mbuf pool. */
bool rpi5_gem_network_adapter_tx_complete(
	struct rpi5_gem_network_adapter *adapter, void *packet);

/* The received packet is always consumed: delivered to inputPacket() when the
 * interface is enabled and link-active, otherwise returned via free_packet(). */
bool rpi5_gem_network_adapter_input(
	struct rpi5_gem_network_adapter *adapter, void *packet, uint32_t bytes,
	bool queue);
uint32_t rpi5_gem_network_adapter_flush_input(
	struct rpi5_gem_network_adapter *adapter);

/* disable() first stops and flushes Apple's output queue, then requires the
 * backend to retire all accepted TX packets before it returns.  teardown() is
 * synchronous and returns to QUALIFIED state. */
bool rpi5_gem_network_adapter_disable(
	struct rpi5_gem_network_adapter *adapter);
bool rpi5_gem_network_adapter_teardown(
	struct rpi5_gem_network_adapter *adapter);

#ifdef __cplusplus
}
#endif
#endif
