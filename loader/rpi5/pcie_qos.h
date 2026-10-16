/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_QOS_H
#define RPI5_PCIE_QOS_H
#include "pcie_profile.h"
#include "pcie_ubus.h"
enum rpi5_pcie_qos_state {
    RPI5_PCIE_QOS_EMPTY, RPI5_PCIE_QOS_READY, RPI5_PCIE_QOS_BUSY,
    RPI5_PCIE_QOS_COMPLETE, RPI5_PCIE_QOS_QUARANTINED
};
enum rpi5_pcie_qos_result {
    RPI5_PCIE_QOS_OK = 0, RPI5_PCIE_QOS_ARGUMENT = -1, RPI5_PCIE_QOS_STATE = -2,
    RPI5_PCIE_QOS_DEPENDENCY = -3, RPI5_PCIE_QOS_IO = -4,
    RPI5_PCIE_QOS_READBACK = -5, RPI5_PCIE_QOS_NOT_QUIESCENT = -6
};
struct rpi5_pcie_qos {
    struct rpi5_pcie_ubus *ubus;
    struct rpi5_pcie_profile profile;
    int (*check_owner)(void *);
    enum rpi5_pcie_qos_state state;
    uint32_t completed_callbacks;
};
struct rpi5_pcie_qos_observation {
    uint32_t kind, word, registers_programmed, final_control, completed_callbacks;
};
/* Same actual completed UBUS/reset/SerDes/calibration owner and mapping.
 * One-shot, zero-initialized stable disjoint session; init is pure. Independent
 * accessible Device/power/clocks/shared lifecycle, IRQ/endpoint/DMA quiescence,
 * bounded callbacks/fault containment and autonomous recovery remain required.
 * check_owner is ownership/watchdog only, not proof of those conditions. */
int rpi5_pcie_qos_init(struct rpi5_pcie_qos *, struct rpi5_pcie_ubus *,
    const struct rpi5_pcie_profile *, int (*check_owner)(void *));
/* Apply a validated FIFO or VDM map after actual UBUS fixups. Before each
 * write and final publication require RC/link-down/PERST asserted, no L23,
 * IDDQ released, AXI fix bits and disabled/enabled-as-expected VDM reception.
 * Maps/readbacks first, VDM reception enable LAST. FIFO upper bits preserved.
 * Independent final target-field pass. No-map does no writes. <=256 callbacks,
 * no polls/delays/new mapping/claim, no RC/windows/link/IRQ/DMA operation.
 * No-op COMPLETE is not a default priority/electrical/QoS performance claim.
 * Failure quarantines session/UBUS/SerDes/MDIO, leaves output unchanged,
 * stops without cleanup, retry or rollback. Already-issued writes may persist.
 * Finite callback count does not contain hung/aborting MMIO. */
int rpi5_pcie_qos_configure(struct rpi5_pcie_qos *, struct rpi5_pcie_qos_observation *);
#endif
