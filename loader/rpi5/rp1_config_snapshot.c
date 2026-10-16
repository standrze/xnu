/* SPDX-License-Identifier: BSD-2-Clause */
#include "rp1_config_snapshot.h"
int rpi5_rp1_config_snapshot(struct rpi5_pcie_config *config,
    struct rpi5_rp1_config_snapshot *out)
{
    if (!config || !out) return -1;
    struct rpi5_rp1_config_snapshot result = {0};
    for (unsigned pass = 0; pass < 2; pass++) {
        for (unsigned index = 0; index < 16; index++) {
            struct rpi5_pcie_config_request request = {1,0,0,index*4,4,0,0};
            uint32_t value;
            if (rpi5_pcie_config_transfer(config, &request, &value)) return -2;
            if (pass && value != result.header[index]) return -3;
            result.header[index] = value;
        }
    }
    /* RP1 1de4:0001, single-function type-0 header and non-prefetchable MEM32
     * BAR1. Size is deliberately not guessed from a BAR value or the DTB. */
    if (result.header[0] != UINT32_C(0x00011de4) ||
        (result.header[3] & UINT32_C(0x00ff0000)) ||
        (result.header[5] & 15)) return -4;
    result.bar1_pci_base = result.header[5];
    result.command = (uint16_t)result.header[1];
    result.status = (uint16_t)(result.header[1] >> 16);
    result.revision = (uint8_t)result.header[2];
    *out = result;
    return 0;
}
