/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_RP1_USB_XHCI_CAPS_H
#define RPI5_RP1_USB_XHCI_CAPS_H

#include <stddef.h>
#include <stdint.h>

#define RPI5_RP1_USB_CONTROLLER_COUNT 2u
#define RPI5_RP1_USB_WINDOW_SIZE 0x100000u
#define RPI5_RP1_USB0_BAR1_OFFSET 0x200000u
#define RPI5_RP1_USB1_BAR1_OFFSET 0x300000u
#define RPI5_RP1_XHCI_CAP_WORDS 8u

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_rp1_xhci_caps {
	uint32_t raw[RPI5_RP1_XHCI_CAP_WORDS];
	uint32_t capability_length;
	uint32_t interface_version;
	uint32_t max_slots;
	uint32_t max_interrupters;
	uint32_t max_ports;
	uint32_t max_scratchpad_buffers;
	uint32_t doorbell_offset;
	uint32_t runtime_offset;
	uint32_t extended_capability_offset;
	uint32_t address_64;
	uint32_t context_64;
	uint32_t port_power_control;
};

/* Decode the eight read-only xHCI capability dwords at offsets 0x00..0x1c.
 * This performs no MMIO and grants no reset, DMA, interrupt or port authority. */
int rpi5_rp1_xhci_caps_decode(
	const uint32_t raw[RPI5_RP1_XHCI_CAP_WORDS],
	struct rpi5_rp1_xhci_caps *out);

/* Translate one of the two official RP1 DWC3 child offsets into a checked
 * offset within the already assigned/mapped 4-MiB RP1 BAR1 aperture. */
int rpi5_rp1_usb_bar1_range(unsigned controller, uint32_t *offset,
	uint32_t *length);

#ifdef __cplusplus
}
#endif

#endif
