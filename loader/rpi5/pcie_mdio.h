/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_MDIO_H
#define RPI5_PCIE_MDIO_H

#include "pcie_fdt.h"

/* BCM2712 PCIe2 SerDes MDIO port 0 only, not RP1's Ethernet PHY MDIO.
 * Provider owns an accessible Device mapping and exclusive bridge/MDIO/shared
 * clock-reset lifecycle. It must serialize all transactions, contain faults,
 * bound callbacks, order writes, and provide monotonic non-wrapping microseconds.
 * No callback may reenter; numeric results are aligned little-endian MMIO.
 * This helper touches only offsets 0x1100, 0x1104 and 0x1108. */
struct rpi5_pcie_mdio_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*read32)(void *, uint32_t offset, uint32_t *);
    int (*write32)(void *, uint32_t offset, uint32_t);
    int (*order)(void *);
    int (*now_us)(void *, uint64_t *);
    int (*delay_us)(void *, uint32_t);
};
enum rpi5_pcie_mdio_state {
    RPI5_PCIE_MDIO_EMPTY, RPI5_PCIE_MDIO_READY,
    RPI5_PCIE_MDIO_BUSY, RPI5_PCIE_MDIO_QUARANTINED
};
enum rpi5_pcie_mdio_result {
    RPI5_PCIE_MDIO_OK = 0, RPI5_PCIE_MDIO_ARGUMENT = -1,
    RPI5_PCIE_MDIO_STATE = -2, RPI5_PCIE_MDIO_IO = -3,
    RPI5_PCIE_MDIO_READBACK = -4, RPI5_PCIE_MDIO_TIMEOUT = -5,
    RPI5_PCIE_MDIO_CLOCK = -6, RPI5_PCIE_MDIO_ALREADY_BUSY = -7
};
struct rpi5_pcie_mdio {
    struct rpi5_pcie_mdio_io io;
    enum rpi5_pcie_mdio_state state;
    uint32_t completed_callbacks; /* per-transaction, successful callbacks only */
};
struct rpi5_pcie_mdio_observation {
    uint32_t command, address_readback, idle_write_data, final_data;
    uint32_t payload, poll_reads;
    uint64_t poll_elapsed_us;
};

/* Pure init for a zero-initialized, disjoint, stable session. Requires exact
 * decoded PCIe2 resource; this does not prove power, clock or accessibility.
 * A used session cannot be reinitialized, including a quarantined one. */
int rpi5_pcie_mdio_init(struct rpi5_pcie_mdio *, const struct rpi5_pcie_fdt *,
    const struct rpi5_pcie_mdio_io *);

/* Registers 0..31, port 0. Read returns the raw 31-bit payload in observation;
 * write issues a 16-bit value, and completion only acknowledges the interface,
 * not the SerDes register's retained value or electrical behavior.
 * Read DONE is bit31 SET; write DONE is bit31 CLEAR. Both are independently
 * bounded to 100 us and 11 reads, with at least 10-us polling waits. An existing
 * busy write is not ours to overwrite. Address readback flushes the posted
 * command like the reference implementation, not an exact-value guarantee.
 * No edge claim, SSC, config selector, PERST, link or DMA access occurs.
 * Success permits the next serialized transaction. Any callback/readback/
 * clock/deadline failure quarantines permanently, stops without cleanup, and
 * leaves out unchanged. A failed write may already have taken effect.
 * This component has no boot/MMIO integration yet. */
int rpi5_pcie_mdio_read(struct rpi5_pcie_mdio *, uint8_t reg,
    struct rpi5_pcie_mdio_observation *out);
int rpi5_pcie_mdio_write(struct rpi5_pcie_mdio *, uint8_t reg, uint16_t value,
    struct rpi5_pcie_mdio_observation *out);

#endif
