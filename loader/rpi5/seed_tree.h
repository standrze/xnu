/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_SEED_TREE_H
#define RPI5_SEED_TREE_H
#include "apple_dt.h"
#include "boot_seed.h"
/* Exact final encoded size, including the 256-byte seed property, without
 * collecting any seed. Same graph profile as encode; atomic length output. */
int rpi5_seed_tree_measure(const struct rpi5_adt_node *root,
    size_t capacity, size_t *written);
/* Input must have exactly one direct chosen child and no random-seed there.
 * Graph is stable throughout callbacks. Source/context, output, written and
 * graph storage must be mutually non-aliasing. Preflights before collection;
 * clears temporary seed after use. Caller clears encoded output if a later
 * handoff step fails. No hardware-source or other board-property validation. */
int rpi5_seed_tree_encode(const struct rpi5_adt_node *root,
    const struct rpi5_seed_source *source, uint64_t ticks, size_t polls,
    void *output, size_t capacity, size_t *written);
#endif
