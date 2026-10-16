/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_RELEASED_WINDOWS_H
#define RPI5_PCIE_RELEASED_WINDOWS_H
#include "pcie_windows.h"
#ifdef __cplusplus
extern "C" {
#endif
/* Independent provider callbacks, not the transport's guard (which itself
 * invokes the provider). Mapping/power/owner/firmware/recovery must already be
 * retained. Reads are real numeric little-endian, ordered Device accesses.
 * No write callback exists. These observations do not establish source IRQ,
 * endpoint bus-master/DMA quiescence or a full lifecycle admission provider. */
struct rpi5_pcie_released_windows_io {
    void *context;
    uint64_t physical_base, mapped_bytes;
    int (*check_owner)(void *);
    int (*read32)(void *, uint32_t, uint32_t *);
    int (*order)(void *);
};
enum rpi5_pcie_released_state {
    RPI5_PCIE_RELEASED_EMPTY, RPI5_PCIE_RELEASED_READY,
    RPI5_PCIE_RELEASED_BUSY, RPI5_PCIE_RELEASED_FAILED
};
struct rpi5_pcie_released_windows {
    const struct rpi5_pcie_windows *windows;
    struct rpi5_pcie_window_plan expected;
    struct rpi5_pcie_released_windows_io io;
    enum rpi5_pcie_released_state state;
    uint32_t checks, callbacks, reads;
};
struct rpi5_pcie_released_observation {
    uint32_t status, control, debug, successful_checks, reads, callbacks;
};
/* Pure init, after the actual programmer completed, captures the exact owned
 * encoding. No register access/permission follows from COMPLETE alone. Stable
 * disjoint storage and serialized non-reentrant owner are caller obligations. */
int rpi5_pcie_released_windows_init(struct rpi5_pcie_released_windows *,
    const struct rpi5_pcie_windows *, const struct rpi5_pcie_released_windows_io *);
/* 90 reads: two snapshots of RC state, every programmed field, seven unused
 * inbound slots and two unused outbound slots. Link-down/training/link-up and
 * PERST release transition are accepted; RC role, no L23 request/state, no
 * IDDQ/forced-reset, exact active translations and disabled unused slots are
 * required. Window fields must remain stable between snapshots. No polling,
 * cleanup, MMIO write or automatic retry. A failure latches FAILED and leaves
 * output unchanged. Repeat fresh checks only within the same external lease;
 * 65536 successes maximum. This is not proof of a trained link or DMA safety. */
int rpi5_pcie_released_windows_check(struct rpi5_pcie_released_windows *,
    struct rpi5_pcie_released_observation *);
#ifdef __cplusplus
}
#endif
#endif
