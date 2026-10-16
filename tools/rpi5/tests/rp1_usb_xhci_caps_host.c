/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_usb_xhci_caps.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int
main(void)
{
	/* xHCI 1.1, 32 slots, four interrupters, two ports, 64-bit addresses,
	 * 64-byte contexts, PPC, xECP at 0x100, valid doorbell/runtime blocks. */
	uint32_t raw[8] = {
		0x01100020, 0x02000420, (2u << 27) | (3u << 21), 0,
		(0x40u << 16) | 0x0d, 0x1000, 0x2000, 0,
	};
	struct rpi5_rp1_xhci_caps caps;
	assert(rpi5_rp1_xhci_caps_decode(raw, &caps) == 0);
	assert(caps.capability_length == 0x20 && caps.interface_version == 0x110);
	assert(caps.max_slots == 32 && caps.max_interrupters == 4 &&
	    caps.max_ports == 2 && caps.max_scratchpad_buffers == 67);
	assert(caps.address_64 && caps.context_64 && caps.port_power_control);
	assert(caps.extended_capability_offset == 0x100 &&
	    caps.doorbell_offset == 0x1000 && caps.runtime_offset == 0x2000);

	uint32_t offset, length;
	assert(rpi5_rp1_usb_bar1_range(0, &offset, &length) == 0 &&
	    offset == 0x200000 && length == 0x100000);
	assert(rpi5_rp1_usb_bar1_range(1, &offset, &length) == 0 &&
	    offset == 0x300000 && length == 0x100000);
	assert(rpi5_rp1_usb_bar1_range(2, &offset, &length) != 0);

	struct rpi5_rp1_xhci_caps before;
	memset(&before, 0xa5, sizeof(before));
	for (unsigned mutation = 0; mutation < 9; mutation++) {
		uint32_t invalid[8];
		memcpy(invalid, raw, sizeof(invalid));
		switch (mutation) {
		case 0: invalid[0] = (invalid[0] & ~0xffu) | 0x1c; break;
		case 1: invalid[0] = 0x00900020; break;
		case 2: invalid[1] &= ~0xffu; break;
		case 3: invalid[1] &= ~(0x7ffu << 8); break;
		case 4: invalid[1] &= ~(0xffu << 24); break;
		case 5: invalid[5] = 0x10; break;
		case 6: invalid[6] = 0x10; break;
		case 7: invalid[5] = 0x100000; break;
		default: invalid[4] = 1u << 16; break;
		}
		caps = before;
		assert(rpi5_rp1_xhci_caps_decode(invalid, &caps) == -2);
		assert(memcmp(&caps, &before, sizeof(caps)) == 0);
	}
	assert(rpi5_rp1_xhci_caps_decode(raw, (void *)raw) == -1);
	printf("RP1_USB_XHCI_CAPS_PASS CONTROLLERS=2 READ_ONLY_WORDS=8 FAULTS=9 NO_HARDWARE=1\n");
	return 0;
}
