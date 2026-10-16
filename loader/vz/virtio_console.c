/* SPDX-License-Identifier: BSD-2-Clause
 * Original implementation from the public OASIS virtio 1.2 PCI/split-ring ABI.
 * No Linux/Apple guest driver implementation is copied.
 */
#include "virtio_console.h"

struct descriptor { uint64_t address; uint32_t length; uint16_t flags, next; };
struct available { uint16_t flags, index, ring[VZ_CONSOLE_QUEUE_SIZE], used_event; };
struct used_element { uint32_t id, length; };
struct used { uint16_t flags, index; struct used_element ring[VZ_CONSOLE_QUEUE_SIZE]; };
#define AVAIL_OFFSET 0x100
#define USED_OFFSET 0x200
#define BUFFER_OFFSET 0x400
#define BUFFER_SIZE 256

static void barrier(void) { __asm__ volatile("dmb osh" ::: "memory"); }
static uint64_t ticks(void) { uint64_t value; __asm__ volatile("mrs %0, cntvct_el0" : "=r"(value)); return value; }
static uint64_t frequency(void) { uint64_t value; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(value)); return value; }
static uint16_t read16(volatile uint8_t *p, unsigned offset) { return *(volatile uint16_t *)(uintptr_t)(p + offset); }
static uint32_t read32(volatile uint8_t *p, unsigned offset) { return *(volatile uint32_t *)(uintptr_t)(p + offset); }
static void write16(volatile uint8_t *p, unsigned offset, uint16_t value) { *(volatile uint16_t *)(uintptr_t)(p + offset) = value; }
static void write32(volatile uint8_t *p, unsigned offset, uint32_t value) { *(volatile uint32_t *)(uintptr_t)(p + offset) = value; }
static void write64(volatile uint8_t *p, unsigned offset, uint64_t value) { *(volatile uint64_t *)(uintptr_t)(p + offset) = value; }
static uintptr_t identity(uint64_t address, size_t size, int device) { (void)size; (void)device; return (uintptr_t)address; }

int vz_console_discover(uint64_t ecam, unsigned start, unsigned end, struct vz_console_shared *out)
{
    if (!out || !ecam || start > end || end > 255) return -1;
    for (unsigned bus = start; bus <= end; bus++) {
        for (unsigned dev = 0; dev < 32; dev++) {
            for (unsigned function = 0; function < 8; function++) {
                volatile uint8_t *pci = (volatile uint8_t *)(uintptr_t)(ecam +
                    ((uint64_t)(bus - start) << 20) + ((uint64_t)dev << 15) + ((uint64_t)function << 12));
                uint32_t id = read32(pci, 0);
                if (id != UINT32_C(0x10431af4)) continue;
                uint64_t bars[6] = {0};
                for (unsigned i = 0; i < 6; i++) {
                    uint32_t low = read32(pci, 0x10 + i * 4);
                    if (low & 1) continue;
                    bars[i] = low & ~UINT64_C(15);
                    if ((low & 6) == 4 && i < 5) {
                        bars[i] |= (uint64_t)read32(pci, 0x14 + i * 4) << 32;
                        i++;
                    }
                }
                struct vz_console_shared shared = {0};
                unsigned cap = pci[0x34] & ~3U;
                for (unsigned seen = 0; cap >= 0x40 && cap <= 0xfc && seen < 48; seen++) {
                    unsigned next = pci[cap + 1] & ~3U;
                    if (pci[cap] == 9 && cap <= 0xec && pci[cap + 2] >= 16) {
                        unsigned type = pci[cap + 3], bar = pci[cap + 4];
                        uint32_t offset = read32(pci, cap + 8), length = read32(pci, cap + 12);
                        if (bar < 6 && bars[bar] && length && offset <= UINT32_MAX - length) {
                            if (type == 1 && length >= 56) shared.common_pa = bars[bar] + offset;
                            if (type == 2 && pci[cap + 2] >= 20 && cap <= 0xe8) {
                                shared.notify_pa = bars[bar] + offset;
                                shared.notify_multiplier = read32(pci, cap + 16);
                            }
                        }
                    }
                    if (!next || next == cap) break;
                    cap = next;
                }
                if (!shared.common_pa || !shared.notify_pa || !shared.notify_multiplier ||
                    (shared.common_pa & 7) || (shared.notify_pa & 1)) return -1;
                /* Enable memory and bus mastering while suppressing legacy INTx.
                 * This first console uses polling, no MSI/MSI-X programming.
                 */
                write16(pci, 4, (uint16_t)(read16(pci, 4) | 6 | 0x400));
                shared.magic = VZ_CONSOLE_MAGIC;
                *out = shared;
                return 0;
            }
        }
    }
    return -1;
}

int vz_console_bind(struct vz_console_shared *s, vz_console_map_fn map, struct vz_console_binding *out)
{
    if (!s || s->magic != VZ_CONSOLE_MAGIC || !map || !out ||
        !s->common_pa || !s->notify_pa || !s->notify_multiplier ||
        (s->common_pa & 7) || (s->notify_pa & 1) ||
        !s->queue_pa[0] || !s->queue_pa[1] ||
        ((s->queue_pa[0] | s->queue_pa[1]) & (VZ_CONSOLE_QUEUE_BYTES - 1))) return -1;
    struct vz_console_binding binding = {0};
    binding.shared = s;
    binding.common = (volatile uint8_t *)map(s->common_pa, 56, 1);
    binding.notify = (volatile uint8_t *)map(s->notify_pa, 4096, 1);
    for (unsigned i = 0; i < 2; i++) {
        uint64_t notify_bytes = (uint64_t)s->notify_offset[i] * s->notify_multiplier;
        if (notify_bytes > 4094 || (notify_bytes & 1)) return -1;
        binding.queues[i] = (volatile uint8_t *)map(s->queue_pa[i], VZ_CONSOLE_QUEUE_BYTES, 0);
        if (!binding.queues[i]) return -1;
    }
    if (!binding.common || !binding.notify) return -1;
    *out = binding;
    return 0;
}

static void notify(struct vz_console_binding *b, unsigned queue)
{
    barrier();
    write16(b->notify, b->shared->notify_offset[queue] * b->shared->notify_multiplier, (uint16_t)queue);
}

int vz_console_start(struct vz_console_shared *s, uint64_t rx, uint64_t tx, struct vz_console_binding *out)
{
    if (!s || s->magic != VZ_CONSOLE_MAGIC || !rx || !tx || rx == tx || ((rx | tx) & 0x3fff)) return -1;
    s->queue_pa[0] = rx; s->queue_pa[1] = tx;
    s->received_used = s->received_offset = s->transmitted_used = 0;
    volatile uint8_t *common = (volatile uint8_t *)(uintptr_t)s->common_pa;
    common[20] = 0;
    uint64_t begin = ticks(), budget = frequency();
    if (!budget) return -1;
    while (common[20]) if (ticks() - begin > budget) return -1;
    common[20] = 1; common[20] = 3;
    write32(common, 0, 1);
    if (!(read32(common, 4) & 1)) return -1; /* VIRTIO_F_VERSION_1 */
    write32(common, 8, 0); write32(common, 12, 0);
    write32(common, 8, 1); write32(common, 12, 1);
    common[20] = 11;
    if (!(common[20] & 8)) return -1;
    write16(common, 16, UINT16_MAX);
    for (unsigned queue = 0; queue < 2; queue++) {
        write16(common, 22, (uint16_t)queue);
        if (read16(common, 24) < VZ_CONSOLE_QUEUE_SIZE || read16(common, 28)) return -1;
        write16(common, 24, VZ_CONSOLE_QUEUE_SIZE);
        write16(common, 26, UINT16_MAX);
        s->notify_offset[queue] = read16(common, 30);
        volatile uint8_t *area = (volatile uint8_t *)(uintptr_t)s->queue_pa[queue];
        for (unsigned i = 0; i < VZ_CONSOLE_QUEUE_BYTES; i++) area[i] = 0;
        volatile struct descriptor *descs = (volatile struct descriptor *)(uintptr_t)area;
        for (unsigned i = 0; i < VZ_CONSOLE_QUEUE_SIZE; i++) {
            descs[i].address = s->queue_pa[queue] + BUFFER_OFFSET + i * BUFFER_SIZE;
            descs[i].length = BUFFER_SIZE;
            descs[i].flags = queue ? 0 : 2; /* Device writes receive buffers. */
        }
        volatile struct available *available = (volatile struct available *)(uintptr_t)(area + AVAIL_OFFSET);
        available->flags = 1; /* No used-buffer interrupts. */
        if (!queue) {
            for (unsigned i = 0; i < VZ_CONSOLE_QUEUE_SIZE; i++) available->ring[i] = (uint16_t)i;
            available->index = VZ_CONSOLE_QUEUE_SIZE;
        }
        write64(common, 32, s->queue_pa[queue]);
        write64(common, 40, s->queue_pa[queue] + AVAIL_OFFSET);
        write64(common, 48, s->queue_pa[queue] + USED_OFFSET);
        barrier();
        write16(common, 28, 1);
    }
    if (vz_console_bind(s, identity, out)) return -1;
    common[20] = 15;
    barrier();
    if (common[20] != 15) return -1;
    notify(out, 0);
    return 0;
}

int vz_console_tx_ready(struct vz_console_binding *b)
{
    if (!b || !b->shared) return 0;
    volatile struct available *available = (volatile struct available *)(uintptr_t)(b->queues[1] + AVAIL_OFFSET);
    volatile struct used *used = (volatile struct used *)(uintptr_t)(b->queues[1] + USED_OFFSET);
    uint16_t completed = used->index;
    /* Acquire completion before reusing the device's previous TX buffer. */
    barrier();
    return completed == available->index;
}

int vz_console_putc(struct vz_console_binding *b, uint8_t byte)
{
    if (!b || !b->shared) return -1;
    uint64_t begin = ticks(), budget = frequency();
    while (!vz_console_tx_ready(b)) if (ticks() - begin > budget) return -1;
    volatile struct descriptor *descs = (volatile struct descriptor *)(uintptr_t)b->queues[1];
    volatile struct available *available = (volatile struct available *)(uintptr_t)(b->queues[1] + AVAIL_OFFSET);
    b->queues[1][BUFFER_OFFSET] = byte;
    descs[0].length = 1;
    available->ring[available->index % VZ_CONSOLE_QUEUE_SIZE] = 0;
    barrier();
    available->index++;
    notify(b, 1);
    return 0;
}

static void recycle_rx(struct vz_console_binding *b, uint32_t id)
{
    struct vz_console_shared *s = b->shared;
    volatile struct available *available = (volatile struct available *)(uintptr_t)(b->queues[0] + AVAIL_OFFSET);
    available->ring[available->index % VZ_CONSOLE_QUEUE_SIZE] = (uint16_t)id;
    barrier();
    available->index++;
    s->received_used++; s->received_offset = 0;
    notify(b, 0);
}

int vz_console_rx_ready(struct vz_console_binding *b)
{
    if (!b || !b->shared) return 0;
    volatile struct used *used = (volatile struct used *)(uintptr_t)(b->queues[0] + USED_OFFSET);
    for (unsigned skipped = 0; skipped < VZ_CONSOLE_QUEUE_SIZE; skipped++) {
        uint16_t completed = used->index;
        /* The used index publishes ring metadata AND the DMA-written bytes. */
        barrier();
        if (completed == b->shared->received_used) return 0;
        if ((uint16_t)(completed - b->shared->received_used) > VZ_CONSOLE_QUEUE_SIZE) return -2;
        unsigned slot = b->shared->received_used % VZ_CONSOLE_QUEUE_SIZE;
        uint32_t id = used->ring[slot].id, length = used->ring[slot].length;
        if (id >= VZ_CONSOLE_QUEUE_SIZE) return -3;
        if (length > BUFFER_SIZE) return -4;
        if (!length && !b->shared->received_offset) {
            /* Empty device completions carry no character. Return their descriptor,
             * never cast the no-byte sentinel to a spurious input byte 0xff. */
            recycle_rx(b, id);
            continue;
        }
        if (b->shared->received_offset >= length) return -5;
        return 1;
    }
    return 0;
}

int vz_console_getc(struct vz_console_binding *b)
{
    int ready = vz_console_rx_ready(b);
    if (ready != 1) return ready < 0 ? ready : -1;
    struct vz_console_shared *s = b->shared;
    volatile struct used *used = (volatile struct used *)(uintptr_t)(b->queues[0] + USED_OFFSET);
    unsigned slot = s->received_used % VZ_CONSOLE_QUEUE_SIZE;
    uint32_t id = used->ring[slot].id, length = used->ring[slot].length;
    if (id >= VZ_CONSOLE_QUEUE_SIZE || !length || length > BUFFER_SIZE || s->received_offset >= length) return -1;
    int byte = b->queues[0][BUFFER_OFFSET + id * BUFFER_SIZE + s->received_offset++];
    if (s->received_offset == length) {
        recycle_rx(b, id);
    }
    return byte;
}
