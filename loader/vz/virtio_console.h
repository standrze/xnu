/* SPDX-License-Identifier: BSD-2-Clause
 * Polling single-port virtio 1.x PCI console, shared by EFI and the VZ kernel.
 */
#ifndef DARWIN_VZ_VIRTIO_CONSOLE_H
#define DARWIN_VZ_VIRTIO_CONSOLE_H
#include <stddef.h>
#include <stdint.h>

#define VZ_CONSOLE_MAGIC UINT64_C(0x31534e4f435a5658)
#define VZ_CONSOLE_QUEUE_SIZE 8
#define VZ_CONSOLE_QUEUE_BYTES 16384

/* Physical addresses survive EFI ExitBootServices and XNU's new mappings.
 * Place this record and both 16-KiB queue areas in retained loader-owned RAM.
 */
struct vz_console_shared {
    uint64_t magic, common_pa, notify_pa;
    uint64_t queue_pa[2];
    uint32_t notify_multiplier;
    uint16_t notify_offset[2];
    uint16_t received_used, received_offset, transmitted_used;
    uint16_t reserved;
};
typedef uintptr_t (*vz_console_map_fn)(uint64_t physical, size_t bytes, int device);
struct vz_console_binding {
    struct vz_console_shared *shared;
    volatile uint8_t *common, *notify;
    volatile uint8_t *queues[2];
};

/* Call before ExitBootServices only to discover already assigned PCI BARs.
 * Does not size BARs, relocate devices, or access a physical host device.
 */
int vz_console_discover(uint64_t ecam, unsigned bus_start, unsigned bus_end,
    struct vz_console_shared *shared);
/* Configure fresh rings with identity-mapped EFI pointers. Firmware must no
 * longer own this console. Both queue regions must be zeroed, exclusive RAM.
 */
int vz_console_start(struct vz_console_shared *shared, uint64_t receive_queue,
    uint64_t transmit_queue, struct vz_console_binding *binding);
/* Rebind the established rings after XNU takes over address translation. */
int vz_console_bind(struct vz_console_shared *shared, vz_console_map_fn map,
    struct vz_console_binding *binding);
int vz_console_tx_ready(struct vz_console_binding *binding);
int vz_console_putc(struct vz_console_binding *binding, uint8_t byte);
/* 1: byte available; 0: empty; negative: invalid device completion. */
int vz_console_rx_ready(struct vz_console_binding *binding);
int vz_console_getc(struct vz_console_binding *binding);
#endif
