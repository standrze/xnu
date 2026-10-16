/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_PROFILE_H
#define RPI5_PCIE_PROFILE_H
#include "pcie_fdt.h"
enum rpi5_pcie_qos_kind { RPI5_PCIE_QOS_NONE, RPI5_PCIE_QOS_FIFO, RPI5_PCIE_QOS_VDM };
enum rpi5_pcie_clkreq_kind {
    RPI5_PCIE_CLKREQ_ABSENT, RPI5_PCIE_CLKREQ_SAFE,
    RPI5_PCIE_CLKREQ_DEFAULT, RPI5_PCIE_CLKREQ_NO_L1SS
};
struct rpi5_pcie_profile {
    uint32_t generation, lanes, clkreq, aspm_no_l0s, qos_kind, qos_word;
};
enum rpi5_pcie_profile_result {
    RPI5_PCIE_PROFILE_OK = 0, RPI5_PCIE_PROFILE_ARGUMENT = -1,
    RPI5_PCIE_PROFILE_BINDING = -2, RPI5_PCIE_PROFILE_OPTION = -3,
    RPI5_PCIE_PROFILE_UNSUPPORTED = -4
};
/* Decode the FULL stable readable original FDT, not an already reduced binding.
 * First runs the real PCIe/RP1 decoder. Atomic, disjoint outputs, no MMIO.
 * Gen2/x4 only; reject any SSC request, nonzero Tperst extension, SCB sizing,
 * controller clocks/power domains/IOMMU options this backend cannot honor.
 * Validate optional CLKREQ strings, empty aspm-no-l0s and mutually exclusive
 * 4/8 BYTE QoS maps with priorities 0..15, never truncate invalid high bits.
 * Missing CLKREQ is represented as ABSENT, not inferred as a safe clock state.
 * CLKREQ/ASPM are retained declarations for later RC/link policy; decoding is
 * not programming, actual power/clock/quiescence/recovery admission or a NIC. */
int rpi5_pcie_profile_decode(const void *, size_t, struct rpi5_pcie_fdt *,
    struct rpi5_pcie_profile *);
#endif
