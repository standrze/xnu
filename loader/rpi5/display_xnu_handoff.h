/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_DISPLAY_XNU_HANDOFF_H
#define RPI5_DISPLAY_XNU_HANDOFF_H
#include "display_allocation_retained.h"
#include "display_xnu_record.h"
#include "handoff.h"
#include "board_tree.h"
struct rpi5_display_xnu_tree {
    struct rpi5_adt_property properties[5];
    uint8_t record[RPI5_DISPLAY_XNU_RECORD_BYTES];
};
/* Exact physical typing only: add the owned rounded framebuffer to Normal
 * backing, preserving every original type byte. Does not mutate FDT RAM,
 * reservation views or any managed span. Reject overlap/duplicates/overflow. */
int rpi5_display_xnu_types(const struct rpi5_display_retained *,
    const struct rpi5_memory_types *,struct rpi5_memory_types *);
/* Replace only Boot_Video's six ABI fields after the unchanged ownership
 * planner succeeded. The supplied base plan and managed geometry remain exact.
 * No physical writes, FB access, reservation release or kernel transfer. */
int rpi5_display_xnu_handoff(const struct rpi5_display_retained *,
    const struct rpi5_display_allocate_report *,uint64_t,size_t,
    struct rpi5_range,const struct rpi5_handoff_input *,const struct rpi5_handoff_plan *,
    struct rpi5_handoff_plan *,struct rpi5_display_xnu_record *);
/* Preserve existing chosen properties, including the retained original FDT.
 * Caller storage remains live until firmware_seed_tree finishes consumption. */
int rpi5_display_xnu_tree_attach(struct rpi5_board_tree *,const struct rpi5_display_xnu_record *,
    struct rpi5_display_xnu_tree *);
/* Reserve the exact fixed-size property before ADT measurement; commit only
 * after the unchanged resolved planner supplies topOfKernelData. A zero
 * placeholder is not a usable framebuffer record and must never be published. */
int rpi5_display_xnu_tree_reserve(struct rpi5_board_tree *,struct rpi5_display_xnu_tree *);
int rpi5_display_xnu_tree_commit(struct rpi5_board_tree *,const struct rpi5_display_xnu_record *,
    struct rpi5_display_xnu_tree *);
#endif
