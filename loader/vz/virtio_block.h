/* SPDX-License-Identifier: BSD-2-Clause
 * Original polled virtio 1.2 block transport for the dedicated VZ guest.
 */
#ifndef DARWIN_VZ_VIRTIO_BLOCK_H
#define DARWIN_VZ_VIRTIO_BLOCK_H
#include <stddef.h>
#include <stdint.h>
#define VZ_BLOCK_MAGIC UINT64_C(0x314b4c425a5658)
#define VZ_BLOCK_DMA_BYTES 65536
#define VZ_BLOCK_DATA_OFFSET 16384
#define VZ_BLOCK_MAX_BYTES 32768
struct vz_block_device {
    uint64_t magic, common_pa, notify_pa, config_pa;
    uint32_t notify_multiplier, notify_length;
};
struct vz_block_queue {
    volatile uint8_t *common, *notify, *config, *dma;
    uint64_t dma_pa, capacity;
    uint32_t notify_offset;
    uint16_t available, used;
    uint8_t failed;
};
/* 0: one writable device found; 1: none; -1: ambiguous/unsupported.
 * Read-only EFI block devices are never reset, queued, or written.
 */
int vz_block_discover(uint64_t ecam, unsigned start, unsigned end, struct vz_block_device *out);
int vz_block_start(const struct vz_block_device *, struct vz_block_queue *,
    uintptr_t (*map)(uint64_t, size_t), volatile void *dma, uint64_t dma_pa);
/* Caller serializes all requests. Data is in dma + VZ_BLOCK_DATA_OFFSET.
 * Permanent fail-stop on timeout or invalid completion; retain DMA until VM exit.
 */
int vz_block_request(struct vz_block_queue *, unsigned type, uint64_t sector, uint32_t bytes);
#endif
