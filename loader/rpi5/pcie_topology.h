/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_TOPOLOGY_H
#define RPI5_PCIE_TOPOLOGY_H
#include <stddef.h>
#include <stdint.h>

/* Decode stable readable FDT memory and report declarations only. No PCIe
 * MMIO/config access, resource assignment, IRQ or DMA setup. The caller owns
 * safe FDT framing/memory and bounded console callbacks (nonzero = success).
 * Return 0 on complete output, -1 on unsupported FDT, -2 on logging failure.
 * A PASS line means topology decoding, never PCIe link/NIC acceptance. */
int rpi5_pcie_topology_log(const void *fdt, size_t size,
    int (*text)(const char *), int (*hex)(uint64_t));
#endif
