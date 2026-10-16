/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_ALLOCATE_ADAPTER_H
#define RPI5_DISPLAY_ALLOCATE_ADAPTER_H
#include "display_query_adapter.h"
#include "display_allocate_transaction.h"
struct rpi5_display_allocate_candidate {
    uint64_t bus_address,cpu_address,allocation_bytes,reservation_start,reservation_end;
    uint32_t width,height,stride,depth,pixel_order,alpha_mode;
};
struct rpi5_display_allocate_report {
    struct rpi5_display_mailbox_fdt binding;
    struct rpi5_display_mailbox_session session;
    struct rpi5_display_allocate_reply replies[4];
    struct rpi5_display_allocate_candidate candidate;
    uint64_t buffer_address[4],counter_start;
    uint32_t admission,cache_operations,mmio_reads,mmio_writes,decoded_replies,candidate_valid;
    int result;
};
/* Exact standalone successor: four linked isolated BSS pages, same soleARM
 * reset-lineage ownership as GET predecessor, fresh originalFDT. Firmware
 * allocation/selection/mode tags are authored; no framebuffer CPU access,
 * drawing, release, recovery transaction, cache maintenance on FB or XNU.
 * Before any SET require fresh1920x1080x32/pitch7680 preboot settings. Returned
 * alias conversion is the Pi5 EDK2 profile, NOT arbitrary bus translation.
 * Retain entire image and any possible allocation until reset on all exits.
 * Candidate is descriptive admission evidence, not handoff/mapping authority. */
int rpi5_display_allocate_run(const void *,size_t,struct rpi5_range,void *,uint64_t,
    struct rpi5_display_allocate_result *,struct rpi5_display_allocate_report *);
#endif
