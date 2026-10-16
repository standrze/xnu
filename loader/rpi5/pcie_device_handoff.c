/* SPDX-License-Identifier: BSD-2-Clause */
#include "pcie_device_handoff.h"
#include "pcie_fdt.h"
/* Pure shared geometry, with no IOKit types or kernel execution dependency. */
#include "../../iokit/Kernel/BCM2712PCIePHYPolicy.h"

int rpi5_pcie_device_handoff(const void *fdt, size_t fdt_bytes,
    const struct rpi5_memory_types *input, struct rpi5_memory_types *out)
{
    if (!input || !out || input == out || rpi5_memory_types_validate(input) || input->device.count > 29)
        return -1;
    struct rpi5_pcie_fdt binding;
    if (rpi5_fdt_pcie_rp1(fdt, fdt_bytes, &binding)) return -1;
    struct rpi5_memory_types result = *input;
    const struct rpi5_range ranges[3] = {binding.bridge_regs, binding.rescal_regs, binding.bridge_reset_regs};
    for (unsigned bank = 0; bank < 3; bank++) {
        struct bcm2712_phy_mapping plan;
        if (!bcm2712_phy_mapping_plan(bank, ranges[bank].start,
                ranges[bank].end - ranges[bank].start, &plan)) return -1;
        struct rpi5_range added = {plan.page, plan.page + plan.page_bytes};
        size_t position = 0;
        for (size_t i = 0; i < result.device.count; i++) {
            struct rpi5_range existing = result.device.extent[i];
            if (added.start < existing.end && existing.start < added.end) return -1;
            if (existing.start < added.start) position++;
        }
        for (size_t i = result.device.count; i > position; i--)
            result.device.extent[i] = result.device.extent[i - 1];
        result.device.extent[position] = added;
        result.device.count++;
    }
    if (rpi5_memory_types_validate(&result)) return -1;
    *out = result;
    return 0;
}
