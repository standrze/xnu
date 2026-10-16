/* SPDX-License-Identifier: BSD-2-Clause */
#include "fdt_sanitize.h"
#include "fdt.h"
int rpi5_fdt_sanitize_boot_seeds(void *copy, size_t bytes)
{
    struct rpi5_fdt_layout layout;
    struct rpi5_fdt_property properties[3] = {{0}};
    const char *names[3] = {"rng-seed", "kaslr-seed", "random-seed"};
    if (!copy || rpi5_fdt_layout(copy, bytes, &layout) || layout.total != bytes ||
        rpi5_fdt_structure(copy, bytes)) return -1;
    for (unsigned i = 0; i < 3; i++) {
        int status = rpi5_fdt_property(copy, bytes, "/chosen", names[i], &properties[i]);
        if (status == -2 && i != 0) continue;
        if (status || (i == 0 && properties[i].length != 64)) return -1;
    }
    /* All validation completed. The original firmware source is never edited. */
    for (unsigned i = 0; i < 3; i++)
        for (uint32_t j = 0; j < properties[i].length; j++)
            ((volatile uint8_t *)copy)[properties[i].offset + j] = 0;
    return 0;
}
