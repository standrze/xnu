/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual decoder -> window encoder composition on saved/synthetic DTBs. */
#include "pcie_windows.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv)
{
    assert(argc == 2);
    FILE *file = fopen(argv[1],"rb"); assert(file);
    assert(!fseek(file,0,SEEK_END)); long bytes = ftell(file); assert(bytes > 40);
    rewind(file);
    void *blob = malloc((size_t)bytes); assert(blob);
    assert(fread(blob,1,(size_t)bytes,file) == (size_t)bytes); assert(!fclose(file));
    struct rpi5_pcie_fdt fdt;
    assert(!rpi5_fdt_pcie_rp1(blob,(size_t)bytes,&fdt)); free(blob);
    struct rpi5_pcie_window_plan plan;
    assert(rpi5_pcie_windows_plan(&fdt,RPI5_PCIE_WINDOW_EXACT,&plan) == RPI5_PCIE_WINDOWS_ARGUMENT);
    assert(!rpi5_pcie_windows_plan(&fdt,RPI5_PCIE_WINDOW_ACK_FOUR_BYTES,&plan));
    assert(plan.outbound[0].cpu_base == 0x1f00000000 && plan.outbound[0].pci_base == 0);
    assert(plan.outbound[0].size == 0xfffffffc && plan.outbound[0].padding_bytes == 4);
    assert(plan.outbound[0].declared_end == 0x1ffffffffc && plan.outbound[0].decode_end == 0x2000000000);
    assert(plan.outbound[1].cpu_base == 0x1c00000000 && plan.outbound[1].pci_base == 0x400000000);
    assert(plan.outbound[1].size == 0x300000000 && plan.outbound[1].padding_bytes == 0);
    assert(plan.outbound[1].base_hi == 0x1c && plan.outbound[1].limit_hi == 0x1e);
    for (unsigned i = 0; i < 3; i++) {
        assert(plan.inbound[i].pci_base == fdt.dma[i].pci_base);
        assert(plan.inbound[i].cpu_base == fdt.dma[i].cpu_base);
        assert(plan.inbound[i].size == fdt.dma[i].size);
    }
    assert(plan.inbound[0].bar_lo == 7 && plan.inbound[0].remap_hi == 0x1f);
    assert(plan.inbound[1].size == 0x1000000000 && plan.inbound[1].bar_lo == 21);
    assert(plan.inbound[1].bar_hi == 0x10 && plan.inbound[1].remap_hi == 0);
    assert(plan.inbound[2].bar_lo == 0xfffff01c && plan.inbound[2].remap_lo == 0x130001);
    puts("PCIE_WINDOWS_FDT_HOST_PASS");
    return 0;
}
