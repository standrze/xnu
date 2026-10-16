/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_rp1_dma_route.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static void
binding(struct rpi5_pcie_fdt *binding)
{
    memset(binding, 0, sizeof(*binding));
    binding->bridge_regs = (struct rpi5_range){0x1000120000, 0x1000129310};
    binding->mip_regs = (struct rpi5_range){0x1000130000, 0x10001300c0};
    binding->mip_target = (struct rpi5_range){0xfffffff000, 0x10000000000};
    binding->outbound_count = 2;
    binding->dma_count = 3;
    binding->rp1_dma_count = 3;
    binding->outbound[0] = (struct rpi5_pcie_window){
        0x02000000, 0, 0x1f00000000, 0xfffffffc};
    binding->outbound[1] = (struct rpi5_pcie_window){
        0x43000000, 0x400000000, 0x1c00000000, 0x300000000};
    binding->dma[0] = (struct rpi5_pcie_window){
        0x02000000, 0, 0x1f00000000, 0x400000};
    binding->dma[1] = (struct rpi5_pcie_window){
        0x43000000, 0x1000000000, 0, 0x1000000000};
    binding->dma[2] = (struct rpi5_pcie_window){
        0x03000000, 0xfffffff000, 0x1000130000, 0x1000};
    binding->rp1_dma[0] = (struct rpi5_rp1_dma_window){
        0x43000000, 0x1000000000, 0x1000000000, 0x1000000000};
    binding->rp1_dma[1] = (struct rpi5_rp1_dma_window){
        0x02000000, 0xc040000000, 0, 0x410000};
    binding->rp1_dma[2] = (struct rpi5_rp1_dma_window){
        0x02000000, 0, 0x1000000000, 0x1000000000};
}

int
main(void)
{
    struct rpi5_pcie_fdt fdt;
    binding(&fdt);
    struct rpi5_pcie_window_plan plan;
    assert(!rpi5_pcie_windows_plan(&fdt,
        RPI5_PCIE_WINDOW_ACK_FOUR_BYTES, &plan));
    struct rpi5_fdt_memory ram = {
        {0, 0x40000000, 0x100000000},
        {0x3f800000, 0x100000000, 0x200000000}, 3};
    struct rpi5_reservation_plan reserved = {0};
    reserved.fixed.extent[0] = (struct rpi5_range){0, 0x80000};
    reserved.fixed.count = 1;
    reserved.count = 1;
    reserved.request[0].size = 0x4000000;
    reserved.request[0].window_count = 1;
    reserved.request[0].window[0] = (struct rpi5_range){0, 0x40000000};

    struct rpi5_rp1_dma_route route, before;
    assert(!rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x100000000, 0x50000, &route));
    assert(route.physical == 0x100000000 && route.pci == 0x1100000000 &&
        route.rp1 == 0x1100000000 && route.bytes == 0x50000);

    unsigned failures = 0;
#define BAD(expression) do { \
    memset(&route, 0xa5, sizeof(route)); before = route; \
    assert((expression) != 0); \
    assert(!memcmp(&route, &before, sizeof(route))); failures++; \
} while (0)
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0, 0x50000, &route));
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x1fffc0000, 0x50000, &route));
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x100000000, 0, &route));
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x100000000, UINT64_MAX, &route));
    for (unsigned index = 0; index < 3; index++) {
        for (unsigned bit = 0; bit < 32; bit++) {
            struct rpi5_pcie_window_plan changed = plan;
            changed.inbound[index].bar_lo ^= UINT32_C(1) << bit;
            BAD(rpi5_rp1_dma_route(&fdt, &changed, &ram, &reserved, NULL,
                0x100000000, 0x50000, &route));
        }
    }
    struct rpi5_range initrd = {0x100020000, 0x100040000};
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, &initrd,
        0x100000000, 0x50000, &route));
    reserved.fixed.extent[1] = initrd;
    reserved.fixed.count = 2;
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x100000000, 0x50000, &route));
    reserved.fixed.count = 1;
    reserved.request[0].window_count = 0;
    BAD(rpi5_rp1_dma_route(&fdt, &plan, &ram, &reserved, NULL,
        0x100000000, 0x50000, &route));
#undef BAD

    printf("RP1_DMA_ROUTE_PASS negatives=%u NO_DMA_AUTHORITY\n", failures);
    return 0;
}
