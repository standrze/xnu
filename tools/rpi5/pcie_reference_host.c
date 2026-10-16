/* SPDX-License-Identifier: BSD-2-Clause */
/* Native checker for a filtered Linux topology, never an MMIO adapter. */
#include "pcie_fdt.h"
#include "pcie_resource_plan.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

static int number(const char *text, uint64_t *out)
{
    char *end;
    if (!*text || *text == '-' || *text == '+') return -1;
    errno = 0;
    unsigned long long value = strtoull(text, &end, 0);
    if (errno || *end) return -1;
    *out = (uint64_t)value;
    return 0;
}

int main(int argc, char **argv)
{
    if (argc != 5) return 2;
    struct rpi5_rp1_bar_observation bar = {
        .vendor_id = 0x1de4, .device_id = 1, .bar_index = 1,
        .assigned = 1, .memory_decode_enabled = 1, .space = 0x02000000
    };
    uint64_t cpu;
    if (number(argv[2], &bar.pci_base) || number(argv[3], &bar.size) ||
        number(argv[4], &cpu)) return 2;
    FILE *source = fopen(argv[1], "rb");
    if (!source) return 2;
    unsigned char blob[65537];
    size_t count = fread(blob, 1, sizeof blob, source);
    int failed = ferror(source);
    if (fclose(source) || failed || count > 65536) return 2;
    struct rpi5_pcie_fdt binding;
    struct rpi5_pcie_resource_plan plan;
    if (rpi5_fdt_pcie_rp1(blob, count, &binding)) {
        fputs("Unsupported captured PCIe FDT profile\n", stderr);
        return 3;
    }
    if (rpi5_pcie_resource_plan(&binding, &bar, &plan) || plan.bar_cpu.start != cpu) {
        fputs("FDT/PCI resource translation disagreement\n", stderr);
        return 4;
    }
    printf("{\"bridge_cpu_base\":%" PRIu64 ",\"bar_cpu_start\":%" PRIu64
        ",\"bar_cpu_end\":%" PRIu64 ",\"gem_cpu_start\":%" PRIu64
        ",\"gem_cpu_end\":%" PRIu64 ",\"clock_cpu_start\":%" PRIu64
        ",\"clock_cpu_end\":%" PRIu64 ",\"rp1_irq\":%" PRIu32
        ",\"phy_address\":%" PRIu32 "}\n", binding.bridge_regs.start,
        plan.bar_cpu.start, plan.bar_cpu.end, plan.gem_cpu.start, plan.gem_cpu.end,
        plan.clock_cpu.start, plan.clock_cpu.end, binding.rp1_irq, binding.phy_address);
    return 0;
}
