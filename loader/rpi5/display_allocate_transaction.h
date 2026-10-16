/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_ALLOCATE_TRANSACTION_H
#define RPI5_DISPLAY_ALLOCATE_TRANSACTION_H
#include "display_mailbox_transaction.h"
#include "display_allocate_wire.h"
struct rpi5_display_allocate_result { struct rpi5_display_allocate_reply reply[4]; };
/* Actual successor uses the same fresh-owner callback contract and register,
 * cache, PEEK-before-POP,4096-callback/512-poll/1s bounds as the frozen GET
 * core. Exactly four NEVER-reused page-isolated buffers. Quarantine mask15.
 * Sequence: live32-bit PREFLIGHT, SELECT0, one fixed SET+ALLOCATE, all-GET
 * verification. If preflight is16-bit, zero stateful requests are sent.
 * State changes/possible allocation are NOT rolled back, freed or retried:
 * even complete failure retains all buffers and any firmware-owned allocation
 * until watchdog reset. Core cannot establish allocation-address authority;
 * caller must separately validate freshFDT and full returned extent before
 * even publishing a candidate descriptor. No drawing/cache work on FB itself.
 * Ordinary final output is atomic; diagnostic caller may inspect ONLY wire
 * slots marked completed by this session, never uncertain firmware writes. */
int rpi5_display_allocate_exchange(struct rpi5_display_mailbox_session *,
    const struct rpi5_display_mailbox_fdt *,const struct rpi5_display_mailbox_buffer[4],
    const struct rpi5_display_mailbox_ops *,uint64_t owner,uint32_t duration_us,
    struct rpi5_display_allocate_result *);
#endif
