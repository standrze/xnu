/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_TREE_HANDOFF_H
#define RPI5_TREE_HANDOFF_H
#include "handoff.h"
#include "seed_tree.h"
#include "fdt.h"
#include "memory_type.h"
/* Plan against the exact seeded-tree length without collecting or encoding a
 * seed. input.tree_length must be zero; wrapper derives it. All handoff-plan
 * ownership/aliasing prerequisites still apply. No physical memory writes. */
int rpi5_tree_handoff_plan(const void *image, size_t size,
    const struct rpi5_handoff_input *input, const struct rpi5_adt_node *tree,
    size_t tree_capacity, const struct rpi5_range *live, size_t live_count,
    const char *command, size_t command_length, struct rpi5_handoff_plan *out);
/* Select the mapping extent from the resolver's reservation_free view.
 * input.usable must be zero; no independent caller-selected extent accepted.
 * Caller must supply a successful, unmodified resolver result from the same
 * complete firmware/live inventory. Proposed reservations are not committed
 * by this helper. The explicit memory-type map must cover both managed RAM
 * and the complete rounded bootstrap mapping as NORMAL. Reservation-free
 * does not imply normal memory. Caller supplies independently established
 * attribute provenance; this helper cannot infer it from the resolver.
 * No ownership discovery or physical writes. Output is atomic on failure. */
int rpi5_resolved_tree_handoff(const void *image, size_t size,
    const struct rpi5_handoff_input *input,
    const struct rpi5_resolved_reservations *resolved,
    const struct rpi5_memory_types *types,
    const struct rpi5_adt_node *tree, size_t tree_capacity,
    const struct rpi5_range *live, size_t live_count,
    const char *command, size_t command_length, struct rpi5_handoff_plan *out);
#endif
