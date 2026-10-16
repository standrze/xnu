/* SPDX-License-Identifier: BSD-2-Clause */
#include "BCM2712PCIeQoSPolicy.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
    const unsigned widths[] = {0,1,2,4,8}; unsigned reads = 0, writes = 0;
    for (unsigned phase = 0; phase < 12; phase++)
    for (unsigned bank = 0; bank < 5; bank++)
    for (unsigned wi = 0; wi < 5; wi++)
    for (unsigned write = 0; write < 3; write++)
    for (uint32_t off = 0; off <= 0xa000; off++) {
        int allowed = bcm2712_qos_access_allowed(phase, bank, off, widths[wi], write);
        if (phase != BCM2712_PHY_QOS_CONFIGURING)
            assert(allowed == bcm2712_unused_access_allowed(phase, bank, off, widths[wi], write));
        else {
            int ro = off == 0x4068 || off == 0x4064 || off == 0x4304 || off == 0x416c;
            int rw = off == 0x40a0 || off == 0x4168 || off == 0x4164 || off == 0x0a0c || off == 0x0a20 ||
                (off >= 0x4144 && off <= 0x4160 && !(off & 3));
            assert(allowed == (bank == BCM2712_PHY_BRIDGE && widths[wi] == 4 && write < 2 &&
                               (rw || (ro && !write))));
            if (allowed) { if (write) writes++; else reads++; }
        }
    }
    assert(reads == 17 && writes == 13);
    puts("PCIE_QOS_POLICY_PASS READS=17 WRITES=13 NO_MMIO=1");
    return 0;
}
