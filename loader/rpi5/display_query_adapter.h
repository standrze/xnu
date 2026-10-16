/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_QUERY_ADAPTER_H
#define RPI5_DISPLAY_QUERY_ADAPTER_H
#include "display_mailbox_transaction.h"
#define RPI5_DISPLAY_QUERY_PAGE 4096u
#define RPI5_DISPLAY_QUERY_PAGES 3u
struct rpi5_display_query_registers {
    uint64_t el,sctlr,daif,mpidr,frequency,ctr,midr;
};
struct rpi5_display_query_report {
    struct rpi5_display_mailbox_fdt binding;
    struct rpi5_display_mailbox_session session;
    uint64_t buffer_address[3],counter_start;
    uint32_t admission,cache_operations,mmio_reads,mmio_writes;
    int result;
};
/* Actual standalone adapter. Caller is the pinned reset-to-BL31 image only:
 * exact normal firmware, fresh original x0 FDT, sole primary, DAIF masked,
 * no previous mailbox client, no kernel/allocator/CPU_ON. storage comprises
 * three complete page-isolated linked BSS pages inside image. Retain the
 * entire image (including timed-out buffers) until reset. Never hand it off.
 * This is not an API for a running OS or an arbitrary bootloader lineage.
 * Returns raw GET data, not framebuffer/scanout/address/format authority. */
int rpi5_display_query_run(const void *original,size_t bytes,
    struct rpi5_range image,void *storage,uint64_t primary_affinity,
    struct rpi5_display_mailbox_result *,struct rpi5_display_query_report *);
/* Architecture leaves: implemented in the distinct linked .S module, and
 * explicitly doubled by host tests. No portable fake hardware fallback. */
void rpi5_display_query_registers(struct rpi5_display_query_registers *);
uint64_t rpi5_display_query_identity(const void *);
uint64_t rpi5_display_query_counter(void);
uint32_t rpi5_display_query_read(uintptr_t);
void rpi5_display_query_write(uintptr_t,uint32_t);
void rpi5_display_query_clean(uintptr_t);
void rpi5_display_query_invalidate(uintptr_t);
#endif
