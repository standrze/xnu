/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_OBSERVE_H
#define RPI5_PCIE_OBSERVE_H

#include <stdint.h>

/* Provider owns an already accessible BCM2712 PCIe2 Device-memory mapping,
 * the bridge/link lifecycle, and exclusive access to its config selector.
 * Values are host-endian numeric results of aligned little-endian MMIO.
 * Callbacks return zero on success. There is intentionally no general write
 * callback: select_rp1 writes only 0x00100000 to EXT_CFG_INDEX (0x9000).
 * order must complete/order that write before selector readback/config reads.
 * Callback errors cannot make an inaccessible bridge or a CPU abort safe. */
struct rpi5_pcie_observe_io {
    void *context;
    uint64_t mapped_bytes;
    int (*read32)(void *context, uint32_t offset, uint32_t *value);
    int (*select_rp1)(void *context);
    int (*order)(void *context);
};

struct rpi5_pcie_observation {
    uint32_t status_before, status_after;
    uint32_t config[16]; /* Standard 64-byte header, numeric LE words. */
    uint32_t memory_decode_enabled, bus_master_enabled;
    uint64_t bar1_pci_base;
    /* No assigned flag, BAR size, translated CPU address or DMA permission.
     * Those cannot be established by reading a BAR, including a zero BAR. */
};

enum rpi5_pcie_observe_result {
    RPI5_PCIE_OBSERVE_OK = 0,
    RPI5_PCIE_OBSERVE_ARGUMENT = -1,
    RPI5_PCIE_OBSERVE_IO = -2,
    RPI5_PCIE_OBSERVE_LINK = -3,
    RPI5_PCIE_OBSERVE_SELECTOR = -4,
    RPI5_PCIE_OBSERVE_CHANGED = -5,
    RPI5_PCIE_OBSERVE_PROFILE = -6
};

/* Bounded observation of bus 1/device 0/function 0 only. Checks RC/link state
 * before selection, before every config read, and after two header passes.
 * Stable identity/class/header-type/command/BAR fields must agree. Status
 * bits need not agree. An asynchronous link loss can still fault an access:
 * checks are not a substitute for platform fault handling/lifecycle control.
 *
 * Does not train a link, reset, assign/size BARs, program windows, enable bus
 * mastering, access RP1 peripherals, or send packets. It changes the config
 * selector once, never restores/retries it, and performs no PCI config write.
 * Output is unchanged on failure; I/O already performed is NOT rolled back.
 * Caller provides disjoint, stable objects and serialized callbacks. This is
 * not wired into the boot loader or kernel until mapping safety is established. */
int rpi5_pcie_observe_rp1(const struct rpi5_pcie_observe_io *io,
    struct rpi5_pcie_observation *out);

#endif
