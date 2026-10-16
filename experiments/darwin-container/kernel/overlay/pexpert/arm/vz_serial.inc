/* SPDX-License-Identifier: APSL-2.0
 * Darwin container project addition, 2026-10-12.
 * Included after the common pe_serial registration machinery.
 */
#include "virtio_console.h"
#include <mach/vm_types.h>
/* pmap's internal header is intentionally not exported into pexpert. Keep
 * these source-only bridge declarations identical to osfmk's definitions. */
extern vm_map_address_t phystokv(uint64_t pa);
extern unsigned rpi5_physical_memory_type(uint64_t start, uint64_t end);

static struct vz_console_binding vz_console;

static uintptr_t
vz_serial_map(uint64_t physical, size_t bytes, int device)
{
	if (!bytes || physical >= (1ULL << 36) || bytes > (1ULL << 36) - physical) return 0;
	uint64_t first = physical & ~UINT64_C(0x3fff);
	uint64_t last = (physical + bytes + 0x3fff) & ~UINT64_C(0x3fff);
	if (rpi5_physical_memory_type(first, last) != (device ? 2U : 1U)) return 0;
	if (device) return ml_io_map(physical, bytes);
	return (uintptr_t)phystokv(physical);
}

static void vz_serial_init(void) { /* Established rings are retained, never reset. */ }
static unsigned int vz_serial_tx_ready(void) { return (unsigned int)vz_console_tx_ready(&vz_console); }
static unsigned int
vz_serial_rx_ready(void)
{
	boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
	int result = vz_console_rx_ready(&vz_console);
	if (result < 0) panic("VZGENERIC: virtio console invalid RX completion %d", result);
	ml_set_interrupts_enabled(interrupts);
	return (unsigned int)result;
}
static uint8_t
vz_serial_getc(void)
{
	boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
	int byte = vz_console_getc(&vz_console);
	if (byte < 0) panic("VZGENERIC: virtio console receive failed %d", byte);
	ml_set_interrupts_enabled(interrupts);
	return (uint8_t)byte;
}
static void
vz_serial_putc(uint8_t byte)
{
	/* Even on one CPU a console write can be interrupted by kprintf. The
	 * descriptor publication sequence must be indivisible with respect to
	 * that nested writer. Device completion does not require a guest IRQ. */
	boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
	int result = vz_console_putc(&vz_console, byte);
	ml_set_interrupts_enabled(interrupts);
	if (result) panic("VZGENERIC: virtio console transmit failed");
}

static struct pe_serial_functions vz_serial_functions = {
	.init = vz_serial_init,
	.transmit_ready = vz_serial_tx_ready,
	.transmit_data = vz_serial_putc,
	.receive_ready = vz_serial_rx_ready,
	.receive_data = vz_serial_getc,
	.has_irq = false,
	.device = SERIAL_UNKNOWN,
};

static void
vz_serial_setup(const DeviceTreeNode *node __unused)
{
	DTEntry chosen;
	const void *data;
	unsigned size;
	if (SecureDTLookupEntry(NULL, "/chosen", &chosen) != kSuccess ||
	    SecureDTGetProperty(chosen, "vz-console", &data, &size) != kSuccess || size != sizeof(uint64_t)) {
		panic("VZGENERIC: missing console handoff");
	}
	uint64_t physical;
	memcpy(&physical, data, sizeof(physical));
	uintptr_t address = vz_serial_map(physical, sizeof(struct vz_console_shared), 0);
	if (!address || vz_console_bind((struct vz_console_shared *)address, vz_serial_map, &vz_console)) {
		panic("VZGENERIC: invalid console handoff");
	}
	register_serial_functions(&vz_serial_functions);
}

/* Bring-up checkpoints after the final kernel VM mapping is live. This
 * binding uses the normal mapping allocator, never an identity alias, and
 * does not reset/reinitialize the loader's established queues. It is separate
 * from driver registration so it can locate a failure inside serial_init. */
extern uint64_t vz_early_console_pa;
void vz_post_vm_mark(unsigned int stage);
static struct vz_console_binding vz_post_vm_console;
static boolean_t vz_post_vm_console_bound;

void
vz_post_vm_mark(unsigned int stage)
{
	if (!vz_post_vm_console_bound) {
		uintptr_t shared = vz_serial_map(vz_early_console_pa, sizeof(struct vz_console_shared), 0);
		if (!shared || vz_console_bind((struct vz_console_shared *)shared, vz_serial_map, &vz_post_vm_console)) {
			panic("VZGENERIC: post-VM trace mapping failed");
		}
		vz_post_vm_console_bound = TRUE;
	}
	boolean_t interrupts = ml_set_interrupts_enabled(FALSE);
	int result = vz_console_putc(&vz_post_vm_console, (uint8_t)stage);
	ml_set_interrupts_enabled(interrupts);
	if (result) panic("VZGENERIC: post-VM trace transmit failed");
}
