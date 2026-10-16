/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_rp1_dma_route.h"

#define RPI5_RP1_DMA_LIMIT (UINT64_C(1) << 40)

static int
valid_extent(uint64_t base, uint64_t bytes)
{
    return bytes && base < RPI5_RP1_DMA_LIMIT &&
        bytes <= RPI5_RP1_DMA_LIMIT - base;
}

static int
contained(uint64_t address, uint64_t bytes, uint64_t base, uint64_t size)
{
    return valid_extent(base, size) && address >= base && bytes <= size &&
        address - base <= size - bytes;
}

static int
overlaps(uint64_t address, uint64_t bytes, const struct rpi5_range *range)
{
    return range->start >= range->end || range->end > RPI5_RP1_DMA_LIMIT ||
        (address < range->end && range->start < address + bytes);
}

static int
same_plan(const struct rpi5_pcie_window_plan *left,
    const struct rpi5_pcie_window_plan *right)
{
    for (unsigned index = 0; index < 3; index++) {
        const struct rpi5_pcie_inbound_encoding *a = &left->inbound[index];
        const struct rpi5_pcie_inbound_encoding *b = &right->inbound[index];
        if (a->cpu_base != b->cpu_base || a->pci_base != b->pci_base ||
            a->size != b->size || a->bar_lo != b->bar_lo ||
            a->bar_hi != b->bar_hi || a->remap_lo != b->remap_lo ||
            a->remap_hi != b->remap_hi) {
            return 0;
        }
    }
    for (unsigned index = 0; index < 2; index++) {
        const struct rpi5_pcie_outbound_encoding *a = &left->outbound[index];
        const struct rpi5_pcie_outbound_encoding *b = &right->outbound[index];
        if (a->cpu_base != b->cpu_base || a->pci_base != b->pci_base ||
            a->size != b->size || a->declared_end != b->declared_end ||
            a->decode_end != b->decode_end || a->pci_lo != b->pci_lo ||
            a->pci_hi != b->pci_hi || a->base_limit != b->base_limit ||
            a->base_hi != b->base_hi || a->limit_hi != b->limit_hi ||
            a->padding_bytes != b->padding_bytes) {
            return 0;
        }
    }
    return 1;
}

int
rpi5_rp1_dma_route(const struct rpi5_pcie_fdt *binding,
    const struct rpi5_pcie_window_plan *live,
    const struct rpi5_fdt_memory *ram,
    const struct rpi5_reservation_plan *reserved,
    const struct rpi5_range *initrd, uint64_t physical, uint64_t bytes,
    struct rpi5_rp1_dma_route *out)
{
    if (!binding || !live || !ram || !reserved || !out || !physical ||
        !valid_extent(physical, bytes) || !ram->count || ram->count > 8 ||
        reserved->fixed.count > 32 || reserved->count > 8 ||
        binding->rp1_dma_count != 3) {
        return -1;
    }

    struct rpi5_pcie_window_plan expected;
    if (rpi5_pcie_windows_plan(binding, RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,
            &expected) || !same_plan(&expected, live)) {
        return -2;
    }

    const struct rpi5_pcie_window *window = &binding->dma[1];
    const struct rpi5_rp1_dma_window *rp1 = &binding->rp1_dma[0];
    if (window->space != UINT32_C(0x43000000) || window->cpu_base != 0 ||
        window->pci_base != UINT64_C(0x1000000000) ||
        window->size != UINT64_C(0x1000000000) ||
        rp1->space != UINT32_C(0x43000000) ||
        rp1->pci_base != window->pci_base ||
        rp1->rp1_base != UINT64_C(0x1000000000) ||
        rp1->size != window->size ||
        !contained(physical, bytes, window->cpu_base, window->size)) {
        return -3;
    }

    uint64_t cursor = physical;
    for (unsigned index = 0; index < ram->count; index++) {
        if (ram->start[index] >= ram->end[index] ||
            ram->end[index] > RPI5_RP1_DMA_LIMIT ||
            (index && ram->start[index] < ram->end[index - 1])) {
            return -4;
        }
        if (cursor >= ram->start[index] && cursor < ram->end[index]) {
            cursor = ram->end[index] < physical + bytes ?
                ram->end[index] : physical + bytes;
        }
    }
    if (cursor != physical + bytes) {
        return -4;
    }

    for (size_t index = 0; index < reserved->fixed.count; index++) {
        if (overlaps(physical, bytes, &reserved->fixed.extent[index])) {
            return -5;
        }
    }
    if (initrd && overlaps(physical, bytes, initrd)) {
        return -5;
    }
    for (unsigned index = 0; index < reserved->count; index++) {
        const struct rpi5_dynamic_reservation *request =
            &reserved->request[index];
        if (!request->size || !request->window_count ||
            request->window_count > 8) {
            return -5;
        }
        for (unsigned window_index = 0;
            window_index < request->window_count; window_index++) {
            if (overlaps(physical, bytes,
                    &request->window[window_index])) {
                return -5;
            }
        }
    }

    uint64_t pci = window->pci_base + (physical - window->cpu_base);
    if (!contained(pci, bytes, rp1->pci_base, rp1->size)) {
        return -3;
    }
    struct rpi5_rp1_dma_route result = {
        physical, pci, rp1->rp1_base + (pci - rp1->pci_base), bytes
    };
    if (!valid_extent(result.rp1, bytes)) {
        return -3;
    }
    *out = result;
    return 0;
}
