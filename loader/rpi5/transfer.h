/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_TRANSFER_H
#define RPI5_TRANSFER_H
#include <stdint.h>
/* Terminal primary-CPU entry, called only by the opt-in transfer build.
 * Caller must have validated/materialized the kernel and writable boot args/tree,
 * supplied qualified fresh entropy, completed ownership checks, and quiesced all
 * other CPUs/devices that could modify those buffers. Firmware must have made
 * its dirty cache state coherent before our cache-disabled entry. EL2 controls
 * must retain the established non-VHE EL1 contract. This routine does not turn
 * off a live MMU/cache, clean inherited dirty data, or prove any prerequisite.
 * Caller must also establish an explicit watchdog ownership/expiry policy:
 * the transfer build retains a 15-second full-reset observation watchdog.
 * Branching to XNU does not transfer servicing responsibility automatically.
 * Invalid local state/addresses and exceptions park silently until reset.
 */
__attribute__((noreturn)) void rpi5_transfer(uint64_t args_pa, uint64_t entry_pa);
#endif
