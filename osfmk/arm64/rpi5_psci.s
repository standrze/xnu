/* SPDX-License-Identifier: BSD-2-Clause
 * PSCI CPU_ON64 call for the BCM2712 DEVELOPMENT port.
 *
 * uint64_t rpi5_psci_cpu_on(uint64_t affinity, uint64_t entry_pa,
 *     uint64_t context_id);
 * The caller must validate the affinity and publish the physical handoff
 * before invoking this routine. The return value is the raw PSCI result.
 */
#include <pexpert/arm64/board_config.h>
#include <arm64/asm.h>
#include <machine/asm.h>

#if !defined(ARM64_BOARD_CONFIG_BCM2712) || !DEVELOPMENT
#error This PSCI call is restricted to BCM2712 DEVELOPMENT
#endif

#define RPI5_PSCI_CPU_ON64 0xc4000003

	.text
	.p2align 2
	.globl EXT(rpi5_psci_cpu_on)
LEXT(rpi5_psci_cpu_on)
	ARM64_PROLOG
	mov x3, x2
	mov x2, x1
	mov x1, x0
	movz x0, #(RPI5_PSCI_CPU_ON64 & 0xffff)
	movk x0, #((RPI5_PSCI_CPU_ON64 >> 16) & 0xffff), lsl #16
	smc #0
	ret
