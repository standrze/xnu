/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_caps.h"

static int
apart(const void *a, size_t a_size, const void *b, size_t b_size)
{
	const uintptr_t x = (uintptr_t)a;
	const uintptr_t y = (uintptr_t)b;
	return a != NULL && b != NULL && a_size <= UINTPTR_MAX - x &&
	    b_size <= UINTPTR_MAX - y && (x + a_size <= y || y + b_size <= x);
}

int
rpi5_rp1_usb_bar1_range(unsigned controller, uint32_t *offset,
	uint32_t *length)
{
	if (offset == NULL || length == NULL || offset == length ||
	    controller >= RPI5_RP1_USB_CONTROLLER_COUNT) {
		return -1;
	}
	*offset = controller == 0 ? RPI5_RP1_USB0_BAR1_OFFSET :
	    RPI5_RP1_USB1_BAR1_OFFSET;
	*length = RPI5_RP1_USB_WINDOW_SIZE;
	return 0;
}

int
rpi5_rp1_xhci_caps_decode(const uint32_t raw[RPI5_RP1_XHCI_CAP_WORDS],
	struct rpi5_rp1_xhci_caps *out)
{
	if (raw == NULL || out == NULL ||
	    !apart(raw, sizeof(uint32_t) * RPI5_RP1_XHCI_CAP_WORDS,
	    out, sizeof(*out))) {
		return -1;
	}
	const uint32_t cap_length = raw[0] & 0xff;
	const uint32_t version = raw[0] >> 16;
	const uint32_t slots = raw[1] & 0xff;
	const uint32_t interrupters = (raw[1] >> 8) & 0x7ff;
	const uint32_t ports = raw[1] >> 24;
	const uint32_t scratchpads = ((raw[2] >> 27) & 0x1f) << 5 |
	    ((raw[2] >> 21) & 0x1f);
	const uint32_t doorbell = raw[5] & ~3u;
	const uint32_t runtime = raw[6] & ~31u;
	const uint32_t extended = ((raw[4] >> 16) & 0xffff) * 4u;

	if (cap_length < 0x20 || cap_length > 0x100 || (cap_length & 3) != 0 ||
	    version < 0x0100 || version > 0x0120 || slots == 0 || ports == 0 ||
	    interrupters == 0 || doorbell < cap_length || runtime < cap_length ||
	    doorbell >= RPI5_RP1_USB_WINDOW_SIZE ||
	    runtime >= RPI5_RP1_USB_WINDOW_SIZE ||
	    (extended != 0 && (extended < 0x20 ||
	    extended >= RPI5_RP1_USB_WINDOW_SIZE))) {
		return -2;
	}

	struct rpi5_rp1_xhci_caps result = { 0 };
	for (size_t i = 0; i < RPI5_RP1_XHCI_CAP_WORDS; i++) {
		result.raw[i] = raw[i];
	}
	result.capability_length = cap_length;
	result.interface_version = version;
	result.max_slots = slots;
	result.max_interrupters = interrupters;
	result.max_ports = ports;
	result.max_scratchpad_buffers = scratchpads;
	result.doorbell_offset = doorbell;
	result.runtime_offset = runtime;
	result.extended_capability_offset = extended;
	result.address_64 = raw[4] & 1;
	result.context_64 = (raw[4] >> 2) & 1;
	result.port_power_control = (raw[4] >> 3) & 1;
	*out = result;
	return 0;
}
