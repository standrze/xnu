/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef DARWIN_VZ_VIRTIO_NET_H
#define DARWIN_VZ_VIRTIO_NET_H
#include <stddef.h>
#include <stdint.h>

#define VZ_NET_MAGIC UINT64_C(0x3154454e5a565844)
#define VZ_NET_QUEUE_SIZE 8
#define VZ_NET_QUEUE_BYTES 32768
#define VZ_NET_DMA_BYTES (2*VZ_NET_QUEUE_BYTES)
#define VZ_NET_FRAME_MAX 1514
#define VZ_NET_HEADER_BYTES 12
#define VZ_NET_BUFFER_OFFSET 1024
#define VZ_NET_BUFFER_BYTES 2048

struct vz_net_device {
    uint64_t magic, common_pa, notify_pa, config_pa;
    uint32_t notify_multiplier, notify_length;
};
struct vz_net_queue {
    volatile uint8_t *common, *notify, *config, *dma;
    uint64_t dma_pa;
    uint32_t notify_offset[2];
    uint16_t available[2], used[2], tx_busy;
    unsigned char mac[6];
    unsigned stage;
    uint32_t features_low, features_high;
    uint64_t last_rejected;
    int failed;
};
/* Discovery only: no device reset, feature negotiation or DMA before kernel ownership. */
int vz_net_discover(uint64_t ecam, unsigned first_bus, unsigned last_bus, struct vz_net_device *out);
int vz_net_start(const struct vz_net_device *, struct vz_net_queue *,
    uintptr_t (*map)(uint64_t,size_t), volatile void *dma, uint64_t pa);
/* A single worker owns these calls. TX: 0 accepted, 1 full, -1 failed.
 * RX: 0 empty, 1 complete frame, 2 unsupported packet dropped, -1 failed. */
int vz_net_send(struct vz_net_queue *, const unsigned char *frame, size_t size);
int vz_net_receive(struct vz_net_queue *, unsigned char frame[VZ_NET_FRAME_MAX], size_t *size);
#endif
