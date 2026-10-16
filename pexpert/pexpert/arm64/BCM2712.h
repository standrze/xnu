/* SPDX-License-Identifier: APSL-2.0
 * Raspberry Pi downstream addition, 2026-09-04.
 * See APPLE_LICENSE at the repository root.
 * Experimental compile target; hardware bring-up is not yet implemented.
 */
#ifndef _PEXPERT_ARM64_BCM2712_H
#define _PEXPERT_ARM64_BCM2712_H

#if !DEVELOPMENT
#error BCM2712 requires the experimental DEVELOPMENT configuration
#endif

#define __ARM_ARCH__                 8
#define __ARM_VMSA__                 8
#define __ARM_VFP__                  4
#define __ARM_DEBUG__                7
#define __ARM_ENABLE_SWAP__          1
#define __ARM_16K_PG__               1
#define __ARM_PAN_AVAILABLE__        1
#define ARM_ARCH_TIMER               1
#define ARM_LARGE_MEMORY             1
#define ARM_PARAMETERIZED_PMAP       1
#define __ARM_MIXED_PAGE_SIZE__      1

/* CPU coherency does not establish DMA coherency for every peripheral. */
#define __ARM_COHERENT_CACHE__       1
#define __ARM_IC_NOALIAS_ICACHE__    1
#define MAX_L2_CLINE                 6
#define MAX_CPUS                     4
/* Preserve MPIDR Aff1 in reset lookup; these are not shared-cache domains. */
#define MAX_CPU_CLUSTERS             4
#define MAX_CPU_CLUSTER_PHY_ID       3
#define HAS_CLUSTER                 1
#define NO_CPU_OVRD                  1
#define NO_ECORE                     1
#define NO_MONITOR                   1
#define NO_XNU_PLATFORM_ERROR_HANDLER 1
#define BTI_ENFORCED                 0

/* proc_reg.h defaults to 40-bit PA absent Apple 42/44/48-bit selections. */
#ifndef ASSEMBLER
#define PL011_UART
#define PLATFORM_PANIC_LOG_DISABLED
#endif

#endif /* _PEXPERT_ARM64_BCM2712_H */
