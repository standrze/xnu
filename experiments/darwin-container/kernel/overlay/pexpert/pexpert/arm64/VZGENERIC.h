/* SPDX-License-Identifier: APSL-2.0
 * Darwin container project downstream addition, 2026-10-12.
 * See APPLE_LICENSE at the source repository root.
 * Experimental single-vCPU generic Virtualization.framework EFI guest.
 */
#ifndef _PEXPERT_ARM64_VZGENERIC_H
#define _PEXPERT_ARM64_VZGENERIC_H

#if !DEVELOPMENT
#error VZGENERIC requires DEVELOPMENT
#endif
#define __ARM_ARCH__ 8
#define __ARM_VMSA__ 8
#define __ARM_VFP__ 4
#define __ARM_DEBUG__ 7
#define __ARM_ENABLE_SWAP__ 1
#define __ARM_16K_PG__ 1
#define __ARM_PAN_AVAILABLE__ 1
#define ARM_ARCH_TIMER 1
#define ARM_LARGE_MEMORY 1
#define ARM_PARAMETERIZED_PMAP 1
#define __ARM_MIXED_PAGE_SIZE__ 1
#define __ARM_COHERENT_CACHE__ 1
#define __ARM_IC_NOALIAS_ICACHE__ 1
#define MAX_L2_CLINE 6
#define MAX_CPUS 1
#define MAX_CPU_CLUSTERS 1
#define MAX_CPU_CLUSTER_PHY_ID 0
#define NO_CPU_OVRD 1
#define NO_ECORE 1
#define NO_MONITOR 1
#define NO_XNU_PLATFORM_ERROR_HANDLER 1
#define BTI_ENFORCED 0
/* GICv3 is handled as non-secure Group 1 IRQs by pe_vzgeneric.c, not the
 * Apple-platform HAS_GIC_V3 Group 0/FIQ implementation. */
#ifndef ASSEMBLER
#define PLATFORM_PANIC_LOG_DISABLED
#endif
#endif
